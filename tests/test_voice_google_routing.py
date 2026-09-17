import pytest

from jarvis.interfaces.voice.agent import (
    _handle_voice_task_command,
    _is_live_calendar_request,
    _is_live_email_request,
    _load_voice_soul_context,
    _task_command,
    _voice_system_base,
)


def test_voice_instructions_prioritize_google_for_live_calendar_and_email() -> None:
    instructions = _voice_system_base("Denis")

    assert "list_calendar_events" in instructions
    assert "list_emails" in instructions
    assert "La mémoire ne contient que du contexte historique" in instructions


def test_voice_detects_live_google_intents() -> None:
    assert _is_live_calendar_request("Quels sont mes rendez-vous cette semaine ?")
    assert _is_live_calendar_request("Quel est mon agenda demain ?")
    assert not _is_live_calendar_request("Quel temps fera-t-il demain ?")
    assert _is_live_email_request("Est-ce que j'ai des e-mails non lus ?")
    assert not _is_live_calendar_request("Combien de CT dans Body ?")


class FakeSoulRecall:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def recall(self, query: str) -> str:
        self.queries.append(query)
        return "Body contient 15 conteneurs CT."


@pytest.mark.asyncio
async def test_voice_queries_soul_before_the_llm_turn() -> None:
    soul = FakeSoulRecall()

    context = await _load_voice_soul_context(soul, "Combien de CT dans Body ?")

    assert soul.queries == ["Combien de CT dans Body ?"]
    assert context == (
        "## MÉMOIRE CANONIQUE SOUL — recherche en direct\n"
        "Body contient 15 conteneurs CT."
    )


def test_voice_parses_direct_task_commands() -> None:
    assert _task_command("tu peux ajouter la tache : aller manger [voix]") == (
        "create",
        "aller manger",
    )
    assert _task_command("quelles sont mes tâches ?") == ("list", None)
    assert _task_command("marque la tâche aller manger comme terminée") == (
        "complete",
        "aller manger",
    )
    assert _task_command("supprime la tâche aller manger") == ("delete", "aller manger")


class FakeTaskTool:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, **kwargs: object) -> object:
        from jarvis.capabilities.tools.base import ToolResult

        self.calls.append(kwargs)
        if kwargs["action"] == "list":
            return ToolResult("- [ ] aller manger (id: task_123)")
        return ToolResult("Tâche ajoutée dans Soul : aller manger")


@pytest.mark.asyncio
async def test_voice_executes_task_create_without_llm_routing() -> None:
    tool = FakeTaskTool()

    result = await _handle_voice_task_command(tool, "ajoute la tâche : aller manger")

    assert result == "Tâche ajoutée dans Soul : aller manger"
    assert tool.calls == [{"action": "create", "text": "aller manger"}]


@pytest.mark.asyncio
async def test_voice_resolves_task_id_before_completion() -> None:
    tool = FakeTaskTool()

    await _handle_voice_task_command(tool, "marque la tâche aller manger comme terminée")

    assert tool.calls == [
        {"action": "list"},
        {"action": "update", "task_id": "task_123", "done": True},
    ]
