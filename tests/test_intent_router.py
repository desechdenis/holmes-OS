from __future__ import annotations

from dataclasses import dataclass

import pytest

from jarvis.capabilities.tools.base import ToolResult
from jarvis.engine.intent_router import DeterministicIntentRouter
from jarvis.kernel.intents import (
    ActionStatus,
    IntentChannel,
    IntentKind,
    IntentRequest,
)


def _request(text: str, *, session_id: str = "session-a") -> IntentRequest:
    return IntentRequest(
        text=text,
        session_id=session_id,
        channel=IntentChannel.TEXT,
        trace_id="trace-test",
        metadata={"allow_recall": True},
    )


class _Calendar:
    def __init__(self, result: ToolResult) -> None:
        self.result = result
        self.calls = 0

    async def execute(self, **_: object) -> ToolResult:
        self.calls += 1
        return self.result


class _Recall:
    always_recall = True

    def __init__(self) -> None:
        self.calls = 0

    async def recall(self, _: str) -> str:
        self.calls += 1
        return "ancienne donnée mémoire"


@pytest.mark.asyncio
async def test_calendar_success_has_authoritative_fresh_evidence() -> None:
    calendar = _Calendar(ToolResult("Jeudi 14 h — dentiste"))
    router = DeterministicIntentRouter(calendar=calendar)

    result = await router.resolve(_request("Quels sont mes prochains rendez-vous ?"))

    assert result.status is ActionStatus.SUCCEEDED
    assert result.intent is IntentKind.CALENDAR_READ
    assert result.trace_id == "trace-test"
    assert result.evidence[0].source == "google_calendar"
    assert result.evidence[0].authoritative is True
    assert result.evidence[0].expires_at is not None


@pytest.mark.asyncio
async def test_calendar_failure_never_falls_back_to_historical_soul() -> None:
    calendar = _Calendar(ToolResult("OAuth expiré", is_error=True))
    recall = _Recall()
    router = DeterministicIntentRouter(calendar=calendar, recall=recall)

    result = await router.resolve(_request("Lis mon agenda de cette semaine"))

    assert result.status is ActionStatus.FAILED
    assert result.intent is IntentKind.CALENDAR_READ
    assert "indisponible" in (result.content or "")
    assert recall.calls == 0


@dataclass
class _Project:
    id: str = "mission-1"
    title: str = "Audit Holmes"
    steps: tuple[int, ...] = (1, 2)


class _BlockedOrchestrator:
    def __init__(self) -> None:
        self.started: list[str] = []

    async def create_plan(self, _: str) -> _Project:
        return _Project()

    def start_project(self, project_id: str) -> object:
        self.started.append(project_id)
        raise ValueError("Exécution locale des missions libres désactivée")


@pytest.mark.asyncio
async def test_mission_pending_plan_is_isolated_by_session_and_safe_gate_is_visible() -> None:
    orchestrator = _BlockedOrchestrator()
    router = DeterministicIntentRouter(orchestrator=orchestrator)

    prepared = await router.resolve(
        _request("Prépare une mission pour auditer Holmes", session_id="session-a")
    )
    other_session = await router.resolve(_request("Lance le plan", session_id="session-b"))
    blocked = await router.resolve(_request("Lance le plan", session_id="session-a"))

    assert prepared.status is ActionStatus.SUCCEEDED
    assert other_session.status is ActionStatus.FAILED
    assert "Aucun plan" in (other_session.content or "")
    assert blocked.status is ActionStatus.FAILED
    assert "désactivée" in (blocked.content or "")
    assert orchestrator.started == ["mission-1"]


@pytest.mark.asyncio
async def test_unknown_intent_is_passthrough_with_same_trace_id() -> None:
    router = DeterministicIntentRouter()

    result = await router.resolve(_request("Salut Holmes"))

    assert result.status is ActionStatus.PASSTHROUGH
    assert result.intent is IntentKind.CONVERSATION
    assert result.trace_id == "trace-test"
