# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.

"""Point d'entrée conversationnel destiné à Home Assistant Assist."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter()

# Namespace stable, propre aux conversations Home Assistant de Holmes. Il évite
# toute collision avec un UUID dérivé du même identifiant par une autre application.
HOLMES_CONVERSATION_NAMESPACE = uuid5(NAMESPACE_URL, "https://holmes-os/conversations")


def holmes_session_id(external_conversation_id: str | None) -> str | None:
    """Traduire l'identifiant opaque de HA en UUID Holmes stable."""
    if external_conversation_id is None:
        return None
    try:
        # Conserve la compatibilité avec les clients qui réutilisent l'UUID
        # renvoyé par Holmes, contrairement à Home Assistant.
        return str(UUID(external_conversation_id))
    except ValueError:
        pass
    return str(uuid5(HOLMES_CONVERSATION_NAMESPACE, external_conversation_id))


class ConversationRequest(BaseModel):
    text: str = Field(min_length=1)
    conversation_id: str | None = None
    language: str = Field(default="fr", min_length=2, max_length=35)


class ConversationResponse(BaseModel):
    response: str
    conversation_id: str


@router.post("/api/conversation", response_model=ConversationResponse)
async def conversation(body: ConversationRequest, request: Request) -> ConversationResponse:
    """Répondre via le profil vocal, sans ajouter de capacité de pilotage domestique."""
    gateway = request.app.state.voice_gateway
    session, _route, response = await gateway.handle(
        message=f"{body.text.strip()}\n[voix]",
        session_id=holmes_session_id(body.conversation_id),
        stream=False,
    )
    if not isinstance(response, str):  # garde de type : stream=False doit toujours drainer
        raise RuntimeError("voice gateway returned a stream for a non-streaming request")
    return ConversationResponse(response=response, conversation_id=str(session.id))
