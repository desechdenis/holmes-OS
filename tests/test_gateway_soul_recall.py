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

    def start_routing_stream(
        self, **kwargs: object
    ) -> tuple[AsyncIterator[str], None]:
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
    assert agent.contexts == ["Soul: maison", "Soul: body"]


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
        "Soul: Quelle est la température du salon ?\n\n"
        "## État Home Assistant en direct\n- Température Salon : 21 °C"
    ]


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

    assert agent.contexts == ["Soul: Quel temps fera-t-il demain ?"]
