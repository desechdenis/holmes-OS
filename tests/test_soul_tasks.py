from __future__ import annotations

import pytest

from jarvis.capabilities.tools.tasks import SoulTasksTool
from jarvis.providers.memory.soul import SoulTaskStore


class FakeSoulTaskClient:
    def __init__(self) -> None:
        self.note = ""
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> object:
        self.calls.append((name, arguments))
        if name == "read_note":
            return self.note
        if name == "write_note":
            self.note = arguments["content"]
            return {"permalink": "holmes/tasks"}
        raise AssertionError(name)


@pytest.mark.asyncio
async def test_soul_task_store_crud_roundtrip() -> None:
    client = FakeSoulTaskClient()
    store = SoulTaskStore(client, project="maison")

    created = await store.create_task("  Acheter   du lait  ")
    assert created.text == "Acheter du lait"
    assert created.done is False

    listed = await store.list_tasks()
    assert listed == [created]

    updated = await store.update_task(created.id, done=True, text="Acheter du pain")
    assert updated.text == "Acheter du pain"
    assert updated.done is True
    assert await store.list_tasks() == [updated]

    assert await store.delete_task(created.id) is True
    assert await store.list_tasks() == []
    assert await store.delete_task(created.id) is False

    writes = [args for name, args in client.calls if name == "write_note"]
    assert writes
    assert all(args["overwrite"] is True for args in writes)
    assert all(args["project"] == "maison" for args in writes)


@pytest.mark.asyncio
async def test_soul_tasks_tool_exposes_voice_create_and_list() -> None:
    store = SoulTaskStore(FakeSoulTaskClient(), project="maison")
    tool = SoulTasksTool(store)

    created = await tool.execute(action="create", text="Appeler le garage")
    listed = await tool.execute(action="list")

    assert created.is_error is False
    assert "Tâche ajoutée dans Soul" in created.content
    assert "Appeler le garage" in listed.content
    assert "task_" in listed.content


@pytest.mark.asyncio
async def test_soul_tasks_tool_rejects_empty_create() -> None:
    tool = SoulTasksTool(SoulTaskStore(FakeSoulTaskClient()))

    result = await tool.execute(action="create", text="   ")

    assert result.is_error is True
    assert "vide" in result.content
