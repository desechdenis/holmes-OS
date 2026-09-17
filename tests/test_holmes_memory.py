from __future__ import annotations

import asyncio

import pytest

from jarvis.kernel.contracts import CanonicalMemoryStore
from jarvis.kernel.holmes_memory import CanonicalMemoryEvent, MemorySource


def test_canonical_memory_event_preserves_source_and_metadata() -> None:
    metadata = {"entity_id": "binary_sensor.leak_kitchen"}
    event = CanonicalMemoryEvent(
        content="Fuite détectée dans la cuisine.",
        source=MemorySource.HOME_ASSISTANT,
        metadata=metadata,
    )

    metadata["entity_id"] = "changed"

    assert event.source is MemorySource.HOME_ASSISTANT
    assert event.metadata["entity_id"] == "binary_sensor.leak_kitchen"
    assert event.event_id.startswith("mem_")
    with pytest.raises(TypeError):
        event.metadata["entity_id"] = "changed"  # type: ignore[index]


def test_canonical_memory_event_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="ne peut pas être vide"):
        CanonicalMemoryEvent(content="   ", source=MemorySource.SYSTEM)


def test_canonical_memory_store_is_a_small_async_port() -> None:
    class FakeSoul:
        async def append_event(self, event: CanonicalMemoryEvent) -> str:
            return f"soul://{event.event_id}"

    store = FakeSoul()
    assert isinstance(store, CanonicalMemoryStore)
    result = asyncio.run(
        store.append_event(
            CanonicalMemoryEvent(content="Décision validée.", source=MemorySource.CONVERSATION)
        )
    )
    assert result.startswith("soul://mem_")
