from __future__ import annotations

import pytest

from jarvis.kernel.holmes_memory import CanonicalMemoryEvent, MemorySource
from jarvis.providers.memory.soul import SoulMemoryStore, SoulRecall


class FakeSoulClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        return {"permalink": "holmes/events/mem_123"}


@pytest.mark.asyncio
async def test_soul_memory_store_writes_a_provenanced_immutable_note() -> None:
    client = FakeSoulClient()
    store = SoulMemoryStore(client, project="maison")
    event = CanonicalMemoryEvent(
        content="Fuite détectée dans la cuisine.",
        source=MemorySource.HOME_ASSISTANT,
        metadata={"entity_id": "binary_sensor.leak_kitchen"},
        event_id="mem_123",
    )

    reference = await store.append_event(event)

    assert reference == "holmes/events/mem_123"
    assert len(client.calls) == 1
    name, arguments = client.calls[0]
    assert name == "write_note"
    assert arguments["project"] == "maison"
    assert arguments["directory"] == "holmes/events"
    assert arguments["overwrite"] is False
    assert arguments["metadata"] == {
        "event_id": "mem_123",
        "source": "home_assistant",
        "occurred_at": event.occurred_at.isoformat(),
        "source_metadata": {"entity_id": "binary_sensor.leak_kitchen"},
    }
    assert "Fuite détectée dans la cuisine." in arguments["content"]


@pytest.mark.asyncio
async def test_soul_memory_store_returns_a_stable_fallback_reference() -> None:
    class EmptySoulClient:
        async def call_tool(self, name: str, arguments: dict) -> dict:
            return {}

    event = CanonicalMemoryEvent(
        content="Préférence confirmée.",
        source=MemorySource.CONVERSATION,
        event_id="mem_fallback",
    )

    reference = await SoulMemoryStore(EmptySoulClient()).append_event(event)

    assert reference == "soul://holmes/events/mem_fallback"


@pytest.mark.asyncio
async def test_soul_recall_searches_the_canonical_memory_each_turn() -> None:
    client = FakeSoulClient()
    client.call_tool = _search_notes  # type: ignore[method-assign]
    recall = SoulRecall(client, project="maison", max_chars=20)

    result = await recall.recall("maison", k=3)

    assert recall.always_recall is True
    assert result == "Contexte Soul pertin"


@pytest.mark.asyncio
async def test_soul_recall_searches_all_projects_when_no_project_is_pinned() -> None:
    client = FakeSoulClient()
    client.call_tool = _search_all_projects  # type: ignore[method-assign]

    result = await SoulRecall(client).recall("Body")

    assert result == "Body context"


@pytest.mark.asyncio
async def test_soul_recall_hydrates_a_named_reference_note() -> None:
    class ReferenceClient:
        async def call_tool(self, name: str, arguments: dict) -> str:
            if name == "search_notes" and arguments["query"] == "combien de CT il y a dans Body":
                return "Résultats de la question"
            if name == "search_notes" and arguments["query"] == "Body CT":
                return "### Body\n- permalink: maison/projets/body\n"
            if name == "read_note":
                assert arguments == {
                    "identifier": "maison/projets/body",
                    "output_format": "text",
                }
                return "# Body\n\n15 CT inventoriés."
            raise AssertionError((name, arguments))

    result = await SoulRecall(ReferenceClient()).recall("combien de CT il y a dans Body")

    assert result == (
        "## Note de référence Soul\n\n# Body\n\n15 CT inventoriés."
        "\n\n## Résultats Soul\n\nRésultats de la question"
    )


@pytest.mark.asyncio
async def test_soul_recall_ignores_the_voice_transport_marker() -> None:
    class VoiceClient:
        async def call_tool(self, name: str, arguments: dict) -> str:
            assert name == "search_notes"
            assert arguments["query"] == "Body"
            return "Résultat Soul"

    result = await SoulRecall(VoiceClient()).recall("Body [voix]")

    assert result == "Résultat Soul"


def test_soul_recall_derives_a_ct_total_from_an_inventory_note() -> None:
    note = (
        "## node-a\n\n"
        "- [lu] **CT 201 `service-alpha`** — rôle alpha.\n"
        "- [vu] **CT 202 `service-beta`** — rôle bêta.\n\n"
        "## node-b\n\n"
        "- [?] **CT 201 `service-gamma`** — rôle gamma.\n"
    )

    facts = SoulRecall._derive_facts(note)

    assert facts is not None
    assert "**3 conteneurs CT**" in facts


def test_soul_recall_answers_a_derived_ct_total_without_an_llm() -> None:
    summary = (
        "## Faits extraits de Soul\n\n- Total : **15 conteneurs CT** inventoriés.\n\n"
        "## Note de référence Soul\n\ntitle: Body\n"
    )

    answer = SoulRecall.direct_answer("combien de CT il y a dans Body ? [voix]", summary)

    assert answer == "Il y a 15 conteneurs CT dans Body."


async def _search_notes(name: str, arguments: dict) -> str:
    assert name == "search_notes"
    assert arguments == {
        "query": "maison",
        "page_size": 3,
        "output_format": "text",
        "project": "maison",
    }
    return "Contexte Soul pertinent pour Holmes"


async def _search_all_projects(name: str, arguments: dict) -> str:
    assert name == "search_notes"
    assert arguments == {
        "query": "Body",
        "page_size": 5,
        "output_format": "text",
        "search_all_projects": True,
    }
    return "Body context"
