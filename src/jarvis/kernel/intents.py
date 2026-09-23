# Copyright (C) 2026 Barthélémy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Contrats purs du routage d'intentions Holmes.

Ces enveloppes circulent entre les adaptateurs de canal et le moteur sans
dépendre de FastAPI, LiveKit, d'un provider LLM ou d'un outil concret.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class IntentChannel(StrEnum):
    TEXT = "text"
    VOICE_HTTP = "voice_http"
    VOICE_LIVEKIT = "voice_livekit"
    MESSAGING = "messaging"
    VISION = "vision"
    UNKNOWN = "unknown"


class IntentKind(StrEnum):
    MISSION_PREPARE = "mission_prepare"
    MISSION_START = "mission_start"
    TASK_COMMAND = "task_command"
    CALENDAR_READ = "calendar_read"
    SOUL_FACT = "soul_fact"
    HOME_STATE = "home_state"
    CONVERSATION = "conversation"


class ActionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PASSTHROUGH = "passthrough"


@dataclass(frozen=True)
class IntentRequest:
    text: str
    session_id: str
    channel: IntentChannel = IntentChannel.UNKNOWN
    trace_id: str = field(default_factory=lambda: f"int_{uuid.uuid4().hex}")
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    source: str
    content: str
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    authoritative: bool = False


@dataclass(frozen=True)
class ActionResult:
    trace_id: str
    intent: IntentKind
    status: ActionStatus
    content: str | None = None
    evidence: tuple[Evidence, ...] = ()

    @property
    def handled(self) -> bool:
        return self.status is not ActionStatus.PASSTHROUGH and self.content is not None

    def context(self) -> str | None:
        parts = [item.content.strip() for item in self.evidence if item.content.strip()]
        return "\n\n".join(parts) or None
