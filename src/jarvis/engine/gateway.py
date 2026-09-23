# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from loguru import logger

from jarvis.engine.agent import Agent
from jarvis.engine.background.notifications import NotificationQueue
from jarvis.engine.background.worker import BackgroundWorker
from jarvis.engine.intent_router import DeterministicIntentRouter
from jarvis.engine.llm_errors import friendly_llm_error
from jarvis.engine.router import RouteEnum, SpeedRouter
from jarvis.engine.session import Session, SessionManager
from jarvis.kernel.contracts import CalendarReadTool, CrossSessionRecall, HomeStateLookup
from jarvis.kernel.error_collector import collector  # jrv: autofix
from jarvis.kernel.intents import IntentChannel, IntentRequest


def _fallback(exc: BaseException | None = None) -> str:
    if exc is not None:
        return friendly_llm_error(exc)
    return friendly_llm_error(RuntimeError("unknown"))


class Gateway:
    """Point d'entrée unique. Gère session, notifications, routing et agent.

    Phase C : le constructeur Gateway était DÉJÀ bien injecté en pré-C
    (5 dépendances reçues par paramètres typés). Le singleton historique
    `_tool_registry_instance` a été supprimé à l'étape 2 (b) — les call-sites
    (preset, http_skills) reçoivent maintenant le ToolRegistry via constructeur
    ou `request.app.state.container.tool_registry`.

    Flux double-passe pour les outils (CF) :
    1. Premier appel LLM streamé : détection du tag + ack text + capture tool_use.
    2. Exécution parallèle des outils (overlap avec TTS de l'ack).
    3. Second appel LLM (synthesize) : résultats injectés dans le contexte,
       LLM produit une réponse naturelle — pas de dump brut.
    L'utilisateur reçoit : ack streamé → synthèse streamée dans la même bulle.
    [BG] : le worker est soumis par le WebSocket après "done".
    """

    def __init__(
        self,
        session_manager: SessionManager,
        agent: Agent,
        notifications: NotificationQueue,
        worker: BackgroundWorker,
        recall: CrossSessionRecall | None = None,
        home_state: HomeStateLookup | None = None,
        calendar: CalendarReadTool | None = None,
        tasks: object | None = None,
        orchestrator: object | None = None,
        intent_router: DeterministicIntentRouter | None = None,
    ) -> None:
        self._sessions = session_manager
        self._agent = agent
        self._notifications = notifications
        self._worker = worker
        # Construction interne conservée pour les call-sites historiques et les
        # tests unitaires. Le composition root injecte une instance partagée.
        self._intent_router = intent_router or DeterministicIntentRouter(
            recall=recall,
            home_state=home_state,
            calendar=calendar,
            tasks=tasks,
            orchestrator=orchestrator,  # type: ignore[arg-type]
        )

    async def handle(
        self,
        message: str,
        session_id: str | None = None,
        stream: bool = True,
    ) -> tuple[Session, RouteEnum, str | AsyncIterator[str]]:
        session = self._sessions.get_or_create(session_id)
        request = IntentRequest(
            text=message,
            session_id=str(session.id),
            channel=(
                IntentChannel.VOICE_HTTP if "[voix]" in message.lower() else IntentChannel.TEXT
            ),
            metadata={"allow_recall": not session.messages},
        )
        logger.info(
            "Gateway handle",
            session_id=str(session.id),
            trace_id=request.trace_id,
            channel=request.channel.value,
        )

        pending = self._notifications.drain()
        notif_texts = [n.content for n in pending] if pending else None
        if notif_texts:
            logger.info("Injecting notifications", count=len(notif_texts))

        intent_result = await self._intent_router.resolve(request)
        if intent_result.handled:
            answer = intent_result.content or ""
            session.add_message("user", message)
            session.add_message("assistant", answer)
            logger.info(
                "Deterministic intent handled",
                intent=intent_result.intent.value,
                status=intent_result.status.value,
                trace_id=intent_result.trace_id,
            )
            return session, RouteEnum.INSTANT, answer

        try:
            raw_stream, tool_capture = self._agent.start_routing_stream(
                session=session,
                user_message=message,
                notifications=notif_texts,
                recall_summary=intent_result.context(),
            )

            route, text_stream = await SpeedRouter.extract_route(raw_stream)
            if route is RouteEnum.PROJECT:
                # La création d'une mission est une mutation persistante. Elle
                # n'est autorisée que par la commande déterministe explicite
                # traitée plus haut, jamais par un tag inventé par le LLM.
                logger.warning(
                    "LLM mission route ignored; explicit deterministic command required",
                    trace_id=request.trace_id,
                )
                route = RouteEnum.INSTANT
            logger.debug("Route detected", route=route.value)

            agent = self._agent
            notifications = self._notifications

            async def _pipe() -> AsyncIterator[str]:
                tool_task: asyncio.Task | None = None
                # Pour un provider capable d'appeler des outils, le premier texte
                # reste interne tant qu'on ne sait pas si une action sera demandée.
                # Holmes ne peut ainsi jamais annoncer un succès avant le résultat.
                ack_text = ""

                async for chunk in text_stream:
                    ack_text += chunk
                    if tool_capture is None:
                        yield chunk
                    # Dès que _stream_capturing peuple capture (content_block_stop tool_use),
                    # on démarre la task outil — elle tourne pendant que la voice WS fait du TTS.
                    if tool_task is None and tool_capture is not None and tool_capture.calls:
                        tool_task = asyncio.create_task(
                            agent.execute_captured_tools(tool_capture),
                            name="cf-tools",
                        )

                # Fallback : LLM sans préambule texte
                if tool_task is None and tool_capture is not None and tool_capture.calls:
                    tool_task = asyncio.create_task(
                        agent.execute_captured_tools(tool_capture),
                        name="cf-tools",
                    )

                # Second appel LLM pour synthétiser les résultats — avant "done"
                if tool_task is not None:
                    try:
                        results = await tool_task
                        logger.debug("CF tools done", names=[n for _, n, _ in tool_capture.calls])
                        synth_stream = agent.synthesize(session, ack_text, tool_capture, results)
                        _, clean_synth = await SpeedRouter.extract_route(synth_stream)
                        async for chunk in clean_synth:
                            yield chunk
                    except Exception as e:
                        collector.error("JRV-GWY-001", "JRV-GWY-001", cause=e)
                        logger.opt(exception=True).error(
                            "CF tool or synthesize error",
                            error=type(e).__name__,
                            detail=str(e),
                        )
                        notifications.add(f"Outil échoué : {e}")
                        yield friendly_llm_error(e)
                elif tool_capture is not None and ack_text:
                    # Aucun outil finalement demandé : restitue la réponse initiale.
                    yield ack_text

            return await self._finalize(session, route, _pipe(), stream)

        except Exception as e:
            collector.error("JRV-GWY-001", "JRV-GWY-001", cause=e)
            logger.opt(exception=True).error(
                "Gateway error", error=type(e).__name__, detail=str(e), session_id=str(session.id)
            )
            return session, RouteEnum.INSTANT, _fallback(e)

    async def _finalize(
        self,
        session: Session,
        route: RouteEnum,
        response: str | AsyncIterator[str],
        stream: bool,
    ) -> tuple[Session, RouteEnum, str | AsyncIterator[str]]:
        """Si stream=False : draine la réponse, ajoute l'assistant en session."""
        if stream:
            return session, route, response
        if isinstance(response, str):
            text = response
        else:
            text = "".join([chunk async for chunk in response])
        session.add_message("assistant", text)
        return session, route, text
