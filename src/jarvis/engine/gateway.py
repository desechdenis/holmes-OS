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
from jarvis.engine.llm_errors import friendly_llm_error
from jarvis.engine.router import RouteEnum, SpeedRouter
from jarvis.engine.session import Session, SessionManager
from jarvis.kernel.contracts import CalendarReadTool, CrossSessionRecall, HomeStateLookup
from jarvis.kernel.error_collector import collector  # jrv: autofix


def _fallback(exc: BaseException | None = None) -> str:
    if exc is not None:
        return friendly_llm_error(exc)
    return friendly_llm_error(RuntimeError("unknown"))


def _is_live_calendar_request(message: str) -> bool:
    lowered = message.lower()
    return any(
        term in lowered
        for term in (
            "agenda",
            "calendrier",
            "calendar",
            "rendez-vous",
            "rendez vous",
            "rdv",
            "événement",
            "evenement",
            "planning",
        )
    )


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
    ) -> None:
        self._sessions = session_manager
        self._agent = agent
        self._notifications = notifications
        self._worker = worker
        self._recall = recall
        self._home_state = home_state
        self._calendar = calendar

    async def handle(
        self,
        message: str,
        session_id: str | None = None,
        stream: bool = True,
    ) -> tuple[Session, RouteEnum, str | AsyncIterator[str]]:
        session = self._sessions.get_or_create(session_id)
        logger.info("Gateway handle", session_id=str(session.id))

        pending = self._notifications.drain()
        notif_texts = [n.content for n in pending] if pending else None
        if notif_texts:
            logger.info("Injecting notifications", count=len(notif_texts))

        # L'agenda est une source vivante : la mémoire historique ne doit pas
        # répondre à sa place, même lorsqu'un petit modèle n'appelle pas l'outil.
        if self._calendar is not None and _is_live_calendar_request(message):
            try:
                calendar_result = await self._calendar.execute(days_ahead=7)
                if not calendar_result.is_error:
                    answer = (
                        "Voici tes prochains événements Google Calendar :\n"
                        + calendar_result.content
                    )
                    session.add_message("user", message)
                    session.add_message("assistant", answer)
                    return session, RouteEnum.INSTANT, answer
            except Exception as exc:
                collector.warning("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                logger.warning("Live Calendar lookup failed", error=str(exc))

        # Soul est la mémoire canonique : chaque question y est recherchée.
        # Le recall historique reste limité au premier message de session.
        recall_summary: str | None = None
        recall_each_turn = bool(getattr(self._recall, "always_recall", False))
        if self._recall is not None and (not session.messages or recall_each_turn):
            try:
                recall_summary = await self._recall.recall(message)
                if recall_summary:
                    logger.debug("CrossSessionRecall injected", chars=len(recall_summary))
            except Exception as e:
                collector.error("JRV-GWY-001", "JRV-GWY-001", cause=e)
                logger.warning("CrossSessionRecall failed", error=str(e))

        home_context: str | None = None
        if self._home_state is not None:
            try:
                home_context = await self._home_state.lookup(message)
            except Exception as e:
                collector.warning("JRV-GWY-001", "JRV-GWY-001", cause=e)
                logger.warning("Home Assistant lookup failed", error=str(e))

        # Les faits numériques dérivés d'un inventaire Soul sont déterministes.
        # Ne les délègue pas au LLM local, qui peut ajouter une réserve inutile.
        direct_answer = getattr(self._recall, "direct_answer", None)
        if recall_summary and callable(direct_answer):
            answer = direct_answer(message, recall_summary)
            if isinstance(answer, str) and answer.strip():
                session.add_message("user", message)
                answer = answer.strip()
                session.add_message("assistant", answer)
                return session, RouteEnum.INSTANT, answer

        try:
            if home_context:
                recall_summary = "\n\n".join(
                    part for part in (recall_summary, home_context) if part
                )
            raw_stream, tool_capture = self._agent.start_routing_stream(
                session=session,
                user_message=message,
                notifications=notif_texts,
                recall_summary=recall_summary,
            )

            route, text_stream = await SpeedRouter.extract_route(raw_stream)
            logger.debug("Route detected", route=route.value)

            agent = self._agent
            notifications = self._notifications

            async def _pipe() -> AsyncIterator[str]:
                tool_task: asyncio.Task | None = None
                ack_text = ""  # Accumule le texte streamé avant les outils

                async for chunk in text_stream:
                    ack_text += chunk
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
                        if ack_text.strip():
                            yield " "
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
