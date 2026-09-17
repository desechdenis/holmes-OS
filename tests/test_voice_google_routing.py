import pytest

from jarvis.interfaces.voice.agent import (
    _is_live_calendar_request,
    _is_live_email_request,
    _load_voice_soul_context,
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
