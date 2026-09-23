# Copyright (C) 2026 Barthélémy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Routage déterministe des intentions qui ont une source d'autorité."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Protocol

from loguru import logger

from jarvis.capabilities.tools.tasks import execute_task_command
from jarvis.engine.conversation_metrics import metric_stage
from jarvis.kernel.contracts import CalendarReadTool, CrossSessionRecall, HomeStateLookup
from jarvis.kernel.error_collector import collector
from jarvis.kernel.intents import (
    ActionResult,
    ActionStatus,
    Evidence,
    IntentChannel,
    IntentKind,
    IntentRequest,
)


class _MissionProject(Protocol):
    id: object
    title: object
    steps: object


class _MissionOrchestrator(Protocol):
    async def create_plan(self, mission: str) -> _MissionProject: ...

    def start_project(self, project_id: str) -> object: ...


def clean_spoken_command(message: str) -> str:
    clean = re.sub(r"\s*\[voix\]\s*$", "", message, flags=re.IGNORECASE).strip()
    clean = clean.strip(' \t\r\n"“”«»')
    return re.sub(r"[.!?…]+\s*[" + re.escape('"“”«»') + r"]?\s*$", "", clean).strip()


def parse_mission_command(message: str) -> tuple[str, str | None] | None:
    clean = clean_spoken_command(message)
    prepare = re.fullmatch(
        r"(?:prépare|prepare|crée|cree|planifie)\s+(?:une\s+)?mission\s+(?:pour\s+)?(.+)",
        clean,
        flags=re.IGNORECASE,
    )
    if prepare:
        return "prepare", prepare.group(1).strip(' ."“”«»')
    if re.fullmatch(
        r"(?:lance|lancer|démarre|demarre)\s+(?:le\s+)?plan|fais[- ]?(?:le|ça|ca)",
        clean,
        flags=re.IGNORECASE,
    ):
        return "start", None
    return None


def is_live_calendar_request(message: str) -> bool:
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


def is_live_weather_request(message: str) -> bool:
    lowered = message.lower()
    return any(term in lowered for term in ("météo", "meteo", "prévision", "temps fera"))


class DeterministicIntentRouter:
    """Exécute les intentions bornées avant tout appel conversationnel."""

    def __init__(
        self,
        *,
        recall: CrossSessionRecall | None = None,
        home_state: HomeStateLookup | None = None,
        calendar: CalendarReadTool | None = None,
        tasks: object | None = None,
        orchestrator: _MissionOrchestrator | None = None,
    ) -> None:
        self._recall = recall
        self._home_state = home_state
        self._calendar = calendar
        self._tasks = tasks
        self._orchestrator = orchestrator
        self._pending_missions: dict[str, str] = {}

    async def resolve(self, request: IntentRequest) -> ActionResult:
        mission = parse_mission_command(request.text)
        if mission is not None:
            return await self._resolve_mission(request, mission)

        task_outcome = await execute_task_command(self._tasks, request.text)
        if task_outcome is not None:
            answer = task_outcome.content
            status = ActionStatus.SUCCEEDED
            if not task_outcome.succeeded:
                answer = f"Je n'ai pas modifié la liste. {answer}"
                status = ActionStatus.FAILED
            logger.info(
                "Deterministic task command",
                succeeded=task_outcome.succeeded,
                trace_id=request.trace_id,
            )
            return ActionResult(
                trace_id=request.trace_id,
                intent=IntentKind.TASK_COMMAND,
                status=status,
                content=answer,
            )

        evidence: list[Evidence] = []
        weather_forecast = getattr(self._home_state, "weather_forecast", None)
        if callable(weather_forecast) and is_live_weather_request(request.text):
            try:
                forecast = await weather_forecast()
                if forecast:
                    return ActionResult(
                        trace_id=request.trace_id,
                        intent=IntentKind.WEATHER_READ,
                        status=ActionStatus.SUCCEEDED,
                        content="Voici les prévisions de Home Assistant :\n" + forecast,
                    )
                return ActionResult(
                    trace_id=request.trace_id,
                    intent=IntentKind.WEATHER_READ,
                    status=ActionStatus.FAILED,
                    content="Les prévisions Home Assistant ne sont pas disponibles.",
                )
            except Exception as exc:  # noqa: BLE001 — erreur rendue à l'utilisateur
                collector.warning("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                logger.warning("Home Assistant weather lookup failed", error=str(exc))
                return ActionResult(
                    trace_id=request.trace_id,
                    intent=IntentKind.WEATHER_READ,
                    status=ActionStatus.FAILED,
                    content="Home Assistant ne répond pas pour les prévisions.",
                )

        ha_calendar = getattr(self._home_state, "calendar_events", None)
        if callable(ha_calendar) and is_live_calendar_request(request.text):
            try:
                events = await ha_calendar(days_ahead=7)
                if events:
                    return ActionResult(
                        trace_id=request.trace_id,
                        intent=IntentKind.CALENDAR_READ,
                        status=ActionStatus.SUCCEEDED,
                        content="Voici les événements de Home Assistant :\n" + events,
                    )
                return ActionResult(
                    trace_id=request.trace_id,
                    intent=IntentKind.CALENDAR_READ,
                    status=ActionStatus.FAILED,
                    content="Les événements Home Assistant ne sont pas disponibles.",
                )
            except Exception as exc:  # noqa: BLE001 — erreur rendue à l'utilisateur
                collector.warning("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                logger.warning("Home Assistant calendar lookup failed", error=str(exc))
                return ActionResult(
                    trace_id=request.trace_id,
                    intent=IntentKind.CALENDAR_READ,
                    status=ActionStatus.FAILED,
                    content="Home Assistant ne répond pas pour l'agenda.",
                )

        if self._calendar is not None and is_live_calendar_request(request.text):
            try:
                calendar_result = await self._calendar.execute(days_ahead=7)
                if not calendar_result.is_error:
                    item = Evidence(
                        source="google_calendar",
                        content=calendar_result.content,
                        expires_at=datetime.now(UTC) + timedelta(minutes=5),
                        authoritative=True,
                    )
                    return ActionResult(
                        trace_id=request.trace_id,
                        intent=IntentKind.CALENDAR_READ,
                        status=ActionStatus.SUCCEEDED,
                        content="Voici tes prochains événements Google Calendar :\n" + item.content,
                        evidence=(item,),
                    )
                return ActionResult(
                    trace_id=request.trace_id,
                    intent=IntentKind.CALENDAR_READ,
                    status=ActionStatus.FAILED,
                    content=(f"Google Calendar est indisponible : {calendar_result.content}"),
                )
            except Exception as exc:  # noqa: BLE001 — repli conversationnel conservé
                collector.warning("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                logger.warning("Live Calendar lookup failed", error=str(exc))
                return ActionResult(
                    trace_id=request.trace_id,
                    intent=IntentKind.CALENDAR_READ,
                    status=ActionStatus.FAILED,
                    content="Google Calendar est indisponible pour le moment.",
                )

        recall_summary: str | None = None
        if self._home_state is not None and request.channel in {
            IntentChannel.VOICE_HTTP,
            IntentChannel.VOICE_LIVEKIT,
        }:
            ambient_context = getattr(self._home_state, "ambient_context", None)
            if callable(ambient_context):
                try:
                    with metric_stage("ha_context"):
                        ambient = await ambient_context()
                    if ambient:
                        evidence.append(
                            Evidence(
                                source="home_assistant_ambient",
                                content=ambient,
                                expires_at=datetime.now(UTC) + timedelta(seconds=30),
                                authoritative=True,
                            )
                        )
                except Exception as exc:  # noqa: BLE001 — HA ne coupe pas le dialogue
                    collector.warning("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                    logger.warning("Home Assistant ambient context failed", error=str(exc))

        allow_recall = bool(request.metadata.get("allow_recall", True))
        recall_each_turn = bool(getattr(self._recall, "always_recall", False))
        if self._recall is not None and (allow_recall or recall_each_turn):
            try:
                with metric_stage("soul"):
                    recall_summary = await self._recall.recall(request.text)
                if recall_summary:
                    evidence.append(
                        Evidence(
                            source="soul",
                            content=recall_summary,
                            authoritative=True,
                        )
                    )
            except Exception as exc:  # noqa: BLE001 — la mémoire ne coupe pas le dialogue
                collector.error("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                logger.warning("CrossSessionRecall failed", error=str(exc))

        if self._home_state is not None:
            try:
                with metric_stage("ha_context"):
                    home_context = await self._home_state.lookup(request.text)
                if home_context:
                    evidence.append(
                        Evidence(
                            source="home_assistant",
                            content=home_context,
                            expires_at=datetime.now(UTC) + timedelta(seconds=30),
                            authoritative=True,
                        )
                    )
            except Exception as exc:  # noqa: BLE001 — HA ne coupe pas le dialogue
                collector.warning("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                logger.warning("Home Assistant lookup failed", error=str(exc))

        direct_answer = getattr(self._recall, "direct_answer", None)
        if recall_summary and callable(direct_answer):
            answer = direct_answer(request.text, recall_summary)
            if isinstance(answer, str) and answer.strip():
                return ActionResult(
                    trace_id=request.trace_id,
                    intent=IntentKind.SOUL_FACT,
                    status=ActionStatus.SUCCEEDED,
                    content=answer.strip(),
                    evidence=tuple(evidence),
                )

        intent = (
            IntentKind.HOME_STATE
            if any(e.source == "home_assistant" for e in evidence)
            else IntentKind.CONVERSATION
        )
        return ActionResult(
            trace_id=request.trace_id,
            intent=intent,
            status=ActionStatus.PASSTHROUGH,
            evidence=tuple(evidence),
        )

    async def _resolve_mission(
        self,
        request: IntentRequest,
        command: tuple[str, str | None],
    ) -> ActionResult:
        action, instruction = command
        status = ActionStatus.SUCCEEDED
        intent = IntentKind.MISSION_PREPARE if action == "prepare" else IntentKind.MISSION_START
        if self._orchestrator is None:
            answer = "Le moteur de missions n'est pas disponible."
            status = ActionStatus.FAILED
        elif action == "prepare" and instruction:
            try:
                project = await self._orchestrator.create_plan(instruction)
                project_id = str(project.id)
                self._pending_missions[request.session_id] = project_id
                title = str(getattr(project, "title", instruction))
                steps = len(getattr(project, "steps", []))
                answer = (
                    f"Plan prêt : {title}, {steps} étape{'s' if steps != 1 else ''}. "
                    "Je ne l'ai pas lancé. Dis « lance le plan » après l'avoir vérifié."
                )
            except Exception as exc:  # noqa: BLE001 — erreur rendue à l'utilisateur
                collector.error("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                answer = f"Je n'ai pas pu préparer la mission : {exc}"
                status = ActionStatus.FAILED
        else:
            project_id = self._pending_missions.get(request.session_id)
            if not project_id:
                answer = "Aucun plan n'attend de validation dans cette conversation."
                status = ActionStatus.FAILED
            else:
                try:
                    project = self._orchestrator.start_project(project_id)
                    self._pending_missions.pop(request.session_id, None)
                    answer = f"Mission lancée : {getattr(project, 'title', project_id)}."
                except Exception as exc:  # noqa: BLE001 — erreur rendue à l'utilisateur
                    collector.error("JRV-GWY-001", "JRV-GWY-001", cause=exc)
                    answer = f"Je n'ai pas pu lancer le plan : {exc}"
                    status = ActionStatus.FAILED
        return ActionResult(
            trace_id=request.trace_id,
            intent=intent,
            status=status,
            content=answer,
        )
