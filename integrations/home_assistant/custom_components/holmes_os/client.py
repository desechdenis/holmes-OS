"""Pinned-TLS client and testable failover policy for Holmes OS."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp

CONNECT_TIMEOUT_SECONDS = 2
TOTAL_TIMEOUT_SECONDS = 20
UNAVAILABLE_PREFIX = "Holmes est indisponible."


class HolmesClientError(Exception):
    """Base error for a failed Holmes conversation."""


class HolmesAuthenticationError(HolmesClientError):
    """The Holmes API rejected its bearer token."""


class HolmesUnavailableError(HolmesClientError):
    """Holmes could not be reached or did not answer in time."""


@dataclass(frozen=True)
class ConversationReply:
    text: str
    conversation_id: str | None


def certificate_fingerprint(value: str) -> bytes:
    """Parse an explicit SHA-256 certificate fingerprint."""
    compact = re.sub(r"[:\s]", "", value)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", compact):
        raise ValueError("certificate fingerprint must be 64 hexadecimal characters")
    return bytes.fromhex(compact)


class HolmesClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        token: str,
        fingerprint: str,
    ) -> None:
        self._session = session
        self._url = f"{base_url.rstrip('/')}/api/conversation"
        self._token = token
        self._fingerprint = aiohttp.Fingerprint(certificate_fingerprint(fingerprint))
        self._timeout = aiohttp.ClientTimeout(
            total=TOTAL_TIMEOUT_SECONDS,
            sock_connect=CONNECT_TIMEOUT_SECONDS,
        )

    async def converse(
        self, text: str, conversation_id: str | None, language: str
    ) -> ConversationReply:
        try:
            async with self._session.post(
                self._url,
                json={
                    "text": text,
                    "conversation_id": conversation_id,
                    "language": language,
                },
                headers={"Authorization": f"Bearer {self._token}"},
                ssl=self._fingerprint,
                timeout=self._timeout,
            ) as response:
                if response.status in {401, 403}:
                    raise HolmesAuthenticationError("Holmes rejected the API token")
                if response.status >= 400:
                    raise HolmesUnavailableError(f"Holmes returned HTTP {response.status}")
                payload: dict[str, Any] = await response.json()
        except HolmesClientError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise HolmesUnavailableError("Holmes is unreachable") from exc

        answer = payload.get("response")
        returned_id = payload.get("conversation_id")
        if not isinstance(answer, str) or not isinstance(returned_id, str):
            raise HolmesUnavailableError("Holmes returned an invalid response")
        return ConversationReply(answer, returned_id)


Fallback = Callable[[str, str | None, str], Awaitable[ConversationReply]]


class HolmesConversationService:
    """Apply one failover policy for every HA conversation request."""

    def __init__(self, client: HolmesClient, fallback: Fallback) -> None:
        self._client = client
        self._fallback = fallback

    async def process(
        self, text: str, conversation_id: str | None, language: str
    ) -> ConversationReply:
        try:
            return await self._client.converse(text, conversation_id, language)
        except HolmesClientError:
            fallback = await self._fallback(text, conversation_id, language)
            suffix = f" {fallback.text}" if fallback.text else ""
            return ConversationReply(f"{UNAVAILABLE_PREFIX}{suffix}", fallback.conversation_id)
