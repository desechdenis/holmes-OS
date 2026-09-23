from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.kernel.holmes_memory import CanonicalMemoryEvent
from jarvis.providers.memory.consolidation import ConsolidationAgent
from jarvis.providers.memory.index import MemoryIndex
from jarvis.providers.memory.topics import TopicStore


def test_assistant_assertions_cannot_enter_consolidation_prompt() -> None:
    message = (
        "Le cluster Body possède 15 conteneurs. "
        "Tu veux que je mémorise cette information ?"
    )

    context = ConsolidationAgent._assistant_questions_only(message)

    assert "15 conteneurs" not in context
    assert context == "Tu veux que je mémorise cette information ?"


class _CanonicalStore:
    def __init__(self) -> None:
        self.events: list[CanonicalMemoryEvent] = []

    async def append_event(self, event: CanonicalMemoryEvent) -> str:
        self.events.append(event)
        return "soul://event"


@pytest.mark.asyncio
async def test_consolidation_keeps_llm_updates_local_pending_human_review(
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

    assert store.events == []
    assert (tmp_path / "topics" / "infra.md").read_text(encoding="utf-8") == (
        "# Infra\n\nSoul est la mémoire canonique."
    )
