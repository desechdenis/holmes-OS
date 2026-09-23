# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.

"""Point d'entrée conversationnel destiné à Home Assistant Assist."""

from __future__ import annotations

import json
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel, Field

from jarvis.engine.conversation_metrics import begin_metrics, end_metrics, metric_stage

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
    metrics, token = begin_metrics()
    try:
        gateway = request.app.state.voice_gateway
        session, _route, response = await gateway.handle(
            message=f"{body.text.strip()}\n[voix]",
            session_id=holmes_session_id(body.conversation_id),
            stream=False,
            allow_tools=False,
            ha_conversation=True,
        )
        with metric_stage("postprocess"):
            if not isinstance(response, str):
                raise RuntimeError("voice gateway returned a stream for a non-streaming request")
            result = ConversationResponse(response=response, conversation_id=str(session.id))
        total_ms = (perf_counter() - metrics.started_at) * 1000
        timing = {
            "event": "ha_conversation_timing",
            "conversation_id": str(session.id),
            "total_ms": round(total_ms, 2),
            "ha_context_ms": round(metrics.stages_ms.get("ha_context", 0.0), 2),
            "soul_ms": round(metrics.stages_ms.get("soul", 0.0), 2),
            "prompt_build_ms": round(metrics.stages_ms.get("prompt_build", 0.0), 2),
            "ollama_ms": round(metrics.stages_ms.get("ollama", 0.0), 2),
            "postprocess_ms": round(metrics.stages_ms.get("postprocess", 0.0), 2),
            "prompt_tokens": metrics.prompt_tokens,
            "response_tokens": metrics.response_tokens,
        }
        logger.info("HA_CONVERSATION_TIMING {}", json.dumps(timing, sort_keys=True))
        return result
    finally:
        end_metrics(token)
