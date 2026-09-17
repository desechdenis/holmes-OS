from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.kernel.holmes_memory import CanonicalMemoryEvent
from jarvis.providers.memory.consolidation import ConsolidationAgent
from jarvis.providers.memory.index import MemoryIndex
from jarvis.providers.memory.topics import TopicStore


class _CanonicalStore:
    def __init__(self) -> None:
        self.events: list[CanonicalMemoryEvent] = []

    async def append_event(self, event: CanonicalMemoryEvent) -> str:
        self.events.append(event)
        return "soul://event"


@pytest.mark.asyncio
async def test_consolidation_writes_only_validated_updates_to_canonical_memory(
    tmp_path: Path,
) -> None:
    store = _CanonicalStore()
    agent = ConsolidationAgent(
        llm=object(),  # type: ignore[arg-type]
        memory_index=MemoryIndex(tmp_path),
        topic_store=TopicStore(tmp_path / "topics"),
        canonical_memory=store,
    )

    await agent._apply(
        json.dumps(
            {
                "updates": [
                    {
                        "file": "topics/infra.md",
                        "content": "# Infra\n\nSoul est la mémoire canonique.",
                        "section": "Infrastructure",
                        "key": "infra",
                        "pointer": "Décision mémoire",
                    }
                ]
            }
        )
    )

    assert len(store.events) == 1
    event = store.events[0]
    assert event.source.value == "conversation"
    assert "Soul est la mémoire canonique." in event.content
    assert event.metadata == {"file": "infra.md", "section": "Infrastructure", "key": "infra"}
