"""Contrat de la mémoire canonique de Holmes.

Soul est la destination canonique prévue. Les producteurs (conversation,
Home Assistant, missions et système) ne manipulent toutefois qu'un événement
normalisé : aucun d'eux ne dépend du protocole MCP de Soul.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import uuid4


class MemorySource(StrEnum):
    """Origine vérifiable d'une entrée de mémoire."""

    CONVERSATION = "conversation"
    HOME_ASSISTANT = "home_assistant"
    MISSION = "mission"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class CanonicalMemoryEvent:
    """Fait ou décision durable prêt à être écrit dans Soul.

    Les états éphémères Home Assistant ne doivent pas être émis ici. L'appelant
    les filtre avant création et indique l'entité ou l'automatisation source
    dans ``metadata``.
    """

    content: str
    source: MemorySource
    metadata: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"mem_{uuid4().hex}")
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("CanonicalMemoryEvent.content ne peut pas être vide")
        # L'enveloppe est immuable : une source ne peut pas altérer après coup
        # les métadonnées effectivement soumises à Soul.
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
