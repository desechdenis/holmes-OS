from __future__ import annotations

from datetime import datetime

import pytest

from jarvis.engine.proactive.collectors.home_assistant import HomeAssistantCollector
from jarvis.engine.proactive.schemas import ContextItem, ItemType, Priority


class FakeCanonicalMemory:
    def __init__(self) -> None:
        self.events = []

    async def append_event(self, event: object) -> str:
        self.events.append(event)
        return "soul://test"


@pytest.mark.asyncio
async def test_critical_home_assistant_event_is_written_once_to_canonical_memory() -> None:
    memory = FakeCanonicalMemory()
    collector = HomeAssistantCollector(canonical_memory=memory)
    item = ContextItem(
        type=ItemType.NEWS,
        title="⚠️ Fuite cuisine — MOISTURE",
        summary="Capteur **moisture** activé",
        raw="{}",
        source="home_assistant",
        timestamp=datetime.now(),
        priority=Priority.HIGH,
    )
    state = {
        "entity_id": "binary_sensor.leak_kitchen",
        "state": "on",
        "last_changed": "2026-09-16T12:00:00+00:00",
        "attributes": {"device_class": "moisture"},
    }

    await collector._record_critical_event(item, state)
    await collector._record_critical_event(item, state)

    assert len(memory.events) == 1
    event = memory.events[0]
    assert event.source.value == "home_assistant"
    assert event.metadata["entity_id"] == "binary_sensor.leak_kitchen"
