"""Contrat HTTP de la conversation Home Assistant."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Request

from jarvis.engine.router import RouteEnum
from jarvis.engine.session import Session, SessionManager
from jarvis.interfaces.api.conversation import ConversationRequest, conversation


def _request(gateway: object) -> Request:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(voice_gateway=gateway)))  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_conversation_nominal_response_uses_voice_profile() -> None:
    session_id = uuid4()
    gateway = SimpleNamespace(
        handle=AsyncMock(return_value=(SimpleNamespace(id=session_id), RouteEnum.INSTANT, "Bref."))
    )

    result = await conversation(
        ConversationRequest(text="Quelle heure est-il ?", language="fr-FR"), _request(gateway)
    )

    assert result.response == "Bref."
    assert result.conversation_id == str(session_id)
    gateway.handle.assert_awaited_once_with(
        message="Quelle heure est-il ?\n[voix]",
        session_id=None,
        stream=False,
        allow_tools=False,
        ha_conversation=True,
    )


@pytest.mark.asyncio
async def test_conversation_id_keeps_the_same_persistent_session() -> None:
    sessions = SessionManager()

    async def handle(
        message: str,
        session_id: str | None,
        stream: bool,
        **_: object,
    ) -> tuple[Session, RouteEnum, str]:
        session = sessions.get_or_create(session_id)
        session.add_message("user", message)
        session.add_message("assistant", "Réponse courte.")
        return session, RouteEnum.INSTANT, "Réponse courte."

    gateway = SimpleNamespace(handle=handle)
    first = await conversation(
        ConversationRequest(text="Premier échange", language="fr"), _request(gateway)
    )
    second = await conversation(
        ConversationRequest(
            text="Deuxième échange", conversation_id=first.conversation_id, language="fr"
        ),
        _request(gateway),
    )

    assert second.conversation_id == first.conversation_id
    assert len(sessions.get(first.conversation_id).messages) == 4  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_ha_ulid_maps_to_one_session_even_when_ha_ignores_holmes_id() -> None:
    sessions = SessionManager()
    histories_seen: list[list[str]] = []

    async def handle(
        message: str,
        session_id: str | None,
        stream: bool,
        **_: object,
    ) -> tuple[Session, RouteEnum, str]:
        session = sessions.get_or_create(session_id)
        histories_seen.append(
            [item["content"] for item in session.messages if item["role"] == "user"]
        )
        session.add_message("user", message)
        session.add_message("assistant", "Réponse courte.")
        return session, RouteEnum.INSTANT, "Réponse courte."

    gateway = SimpleNamespace(handle=handle)
    external_ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    returned_ids: list[str] = []
    for text in ("Premier", "Deuxième", "Troisième"):
        result = await conversation(
            ConversationRequest(
                text=text,
                conversation_id=external_ulid,
                language="fr",
            ),
            _request(gateway),
        )
        returned_ids.append(result.conversation_id)

    assert histories_seen[2] == ["Premier\n[voix]", "Deuxième\n[voix]"]
    assert len(set(returned_ids)) == 1
    assert returned_ids[0] != external_ulid
    assert sessions.list_ids() == [returned_ids[0]]
