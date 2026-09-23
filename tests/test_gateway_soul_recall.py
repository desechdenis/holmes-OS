from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from jarvis.engine.background.notifications import NotificationQueue
from jarvis.engine.background.worker import BackgroundWorker
from jarvis.engine.gateway import Gateway
from jarvis.engine.session import SessionManager


class FakeAgent:
    def __init__(self) -> None:
        self.contexts: list[str | None] = []

    def start_routing_stream(self, **kwargs: object) -> tuple[AsyncIterator[str], None]:
        summary = kwargs.get("recall_summary")
        self.contexts.append(summary if isinstance(summary, str) else None)
        return _response_stream(), None


async def _response_stream() -> AsyncIterator[str]:
    yield "[I] Réponse"


class FakeSoulRecall:
    always_recall = True

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def recall(self, query: str, k: int = 8) -> str:
        self.queries.append(query)
        return f"Soul: {query}"


class DirectSoulRecall(FakeSoulRecall):
    def direct_answer(self, query: str, recall_summary: str) -> str:
        return "Il y a 15 conteneurs CT dans Body."


class FakeHomeState:
    async def ambient_context(self) -> str:
        return "## Contexte ambiant\n- Mode maison : présent"

    async def lookup(self, query: str, limit: int = 6) -> str:
        return "## État Home Assistant en direct\n- Température Salon : 21 °C"


class FakeCalendar:
    async def execute(self, days_ahead: int = 7, **kwargs: object):  # noqa: ANN201
        assert days_ahead == 7
        return type(
            "CalendarResult",
            (),
            {
                "is_error": False,
                "content": "- 2026-09-17 · [Famille] réunion de rentrée",
            },
        )()


class FakeTaskTool:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs: object):  # noqa: ANN201
        from jarvis.capabilities.tools.base import ToolResult

        self.calls.append(kwargs)
        if self.fail:
            return ToolResult("Soul indisponible", is_error=True)
        return ToolResult("Tâche ajoutée dans Soul : aller dormir (id: task_test)")


class FakeMissionOrchestrator:
    def __init__(self) -> None:
        self.prepared: list[str] = []
        self.started: list[str] = []

    async def create_plan(self, mission: str):  # noqa: ANN201
        self.prepared.append(mission)
        return type(
            "Project",
            (),
            {"id": "mission_test", "title": "Audit Holmes OS", "steps": [1, 2, 3]},
        )()

    def start_project(self, project_id: str):  # noqa: ANN201
        self.started.append(project_id)
        return type("Project", (), {"id": project_id, "title": "Audit Holmes OS"})()


@pytest.mark.asyncio
async def test_gateway_queries_soul_for_each_message_in_a_session() -> None:
    agent = FakeAgent()
    soul = FakeSoulRecall()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=agent,  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        recall=soul,  # type: ignore[arg-type]
    )

    session, _, response = await gateway.handle("maison", stream=False)
    assert isinstance(response, str)
    await gateway.handle("body", session_id=str(session.id), stream=False)

    assert soul.queries == ["maison", "body"]
    assert agent.contexts == [
        "## Mémoire Soul\nSoul: maison",
        "## Mémoire Soul\nSoul: body",
    ]


@pytest.mark.asyncio
async def test_gateway_returns_a_deterministic_soul_fact_without_calling_the_llm() -> None:
    agent = FakeAgent()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=agent,  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        recall=DirectSoulRecall(),  # type: ignore[arg-type]
    )

    session, route, response = await gateway.handle("combien de CT il y a dans Body ?")

    assert route.value == "I"
    assert response == "Il y a 15 conteneurs CT dans Body."
    assert agent.contexts == []
    assert session.messages == [
        {"role": "user", "content": "combien de CT il y a dans Body ?"},
        {"role": "assistant", "content": "Il y a 15 conteneurs CT dans Body."},
    ]


@pytest.mark.asyncio
async def test_gateway_injects_read_only_home_assistant_state() -> None:
    agent = FakeAgent()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=agent,  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        recall=FakeSoulRecall(),  # type: ignore[arg-type]
        home_state=FakeHomeState(),  # type: ignore[arg-type]
    )

    await gateway.handle("Quelle est la température du salon ?")

    assert agent.contexts == [
        "## Mémoire Soul\nSoul: Quelle est la température du salon ?\n\n"
        "## État Home Assistant en direct\n- Température Salon : 21 °C"
    ]


@pytest.mark.asyncio
async def test_voice_gateway_injects_ambient_home_context_on_every_turn() -> None:
    agent = FakeAgent()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=agent,  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        home_state=FakeHomeState(),  # type: ignore[arg-type]
    )

    await gateway.handle("Bonjour [voix]")

    assert agent.contexts
    assert "## Contexte ambiant\n- Mode maison : présent" in (agent.contexts[0] or "")


@pytest.mark.asyncio
async def test_gateway_reads_live_calendar_before_using_memory_or_llm() -> None:
    agent = FakeAgent()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=agent,  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        recall=FakeSoulRecall(),  # type: ignore[arg-type]
        calendar=FakeCalendar(),  # type: ignore[arg-type]
    )

    session, route, response = await gateway.handle("Quels sont mes prochains rdv ?")

    assert route.value == "I"
    assert response == (
        "Voici tes prochains événements Google Calendar :\n"
        "- 2026-09-17 · [Famille] réunion de rentrée"
    )
    assert session.messages[-1] == {"role": "assistant", "content": response}
    assert agent.contexts == []


@pytest.mark.asyncio
async def test_gateway_does_not_route_weather_tomorrow_to_calendar() -> None:
    agent = FakeAgent()
    calendar = FakeCalendar()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=agent,  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        recall=FakeSoulRecall(),  # type: ignore[arg-type]
        calendar=calendar,  # type: ignore[arg-type]
    )

    await gateway.handle("Quel temps fera-t-il demain ?")

    assert agent.contexts == ["## Mémoire Soul\nSoul: Quel temps fera-t-il demain ?"]


@pytest.mark.asyncio
async def test_gateway_executes_task_before_the_llm() -> None:
    agent = FakeAgent()
    tasks = FakeTaskTool()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=agent,  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        recall=FakeSoulRecall(),  # type: ignore[arg-type]
        tasks=tasks,
    )

    session, route, response = await gateway.handle("ajoute aller dormir")

    assert route.value == "I"
    assert response == "Tâche ajoutée dans Soul : aller dormir (id: task_test)"
    assert tasks.calls == [{"action": "create", "text": "aller dormir"}]
    assert agent.contexts == []
    assert session.messages[-1] == {"role": "assistant", "content": response}


@pytest.mark.asyncio
async def test_gateway_never_confirms_a_failed_task_write() -> None:
    tasks = FakeTaskTool(fail=True)
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=FakeAgent(),  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        tasks=tasks,
    )

    _, _, response = await gateway.handle("ajoute aller dormir")

    assert response == "Je n'ai pas modifié la liste. Soul indisponible"


@pytest.mark.asyncio
async def test_gateway_prepares_then_starts_voice_mission_without_soul_or_llm() -> None:
    agent = FakeAgent()
    soul = FakeSoulRecall()
    orchestrator = FakeMissionOrchestrator()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=agent,  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        recall=soul,  # type: ignore[arg-type]
        orchestrator=orchestrator,
    )

    session, route, response = await gateway.handle(
        "« Prépare une mission pour analyser l’état de Holmes OS. » [voix]"
    )

    assert route.value == "I"
    assert orchestrator.prepared == ["analyser l’état de Holmes OS"]
    assert "Plan prêt : Audit Holmes OS, 3 étapes" in str(response)
    assert "Je ne l'ai pas lancé" in str(response)
    assert soul.queries == []
    assert agent.contexts == []

    _, route, response = await gateway.handle("Lancer le plan [voix]", session_id=str(session.id))

    assert route.value == "I"
    assert response == "Mission lancée : Audit Holmes OS."
    assert orchestrator.started == ["mission_test"]


@pytest.mark.asyncio
async def test_gateway_refuses_ambiguous_start_without_pending_plan() -> None:
    orchestrator = FakeMissionOrchestrator()
    gateway = Gateway(
        session_manager=SessionManager(),
        agent=FakeAgent(),  # type: ignore[arg-type]
        notifications=NotificationQueue(),
        worker=BackgroundWorker(llm=object(), notifications=NotificationQueue()),  # type: ignore[arg-type]
        orchestrator=orchestrator,
    )

    _, _, response = await gateway.handle("fais le [voix]")

    assert response == "Aucun plan n'attend de validation dans cette conversation."
    assert orchestrator.started == []
