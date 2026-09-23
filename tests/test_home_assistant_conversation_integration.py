"""Network and failover policy tests without requiring a HA runtime."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import pytest

from integrations.home_assistant.custom_components.holmes_os.client import (
    ConversationReply,
    HolmesAuthenticationError,
    HolmesClient,
    HolmesConversationService,
    HolmesUnavailableError,
)

FINGERPRINT = "ab" * 32


class _Response:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload


class _Session:
    def __init__(self, result: object) -> None:
        self.result = result
        self.call: dict[str, Any] = {}

    def post(self, url: str, **kwargs: Any) -> _Response:  # noqa: ANN401
        self.call = {"url": url, **kwargs}
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result  # type: ignore[return-value]


def _client(result: object) -> tuple[HolmesClient, _Session]:
    session = _Session(result)
    return HolmesClient(session, "https://holmes.invalid", "secret", FINGERPRINT), session  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_nominal_request_uses_pinned_tls_and_timeouts() -> None:
    client, session = _client(
        _Response(200, {"response": "Bonjour.", "conversation_id": "session-1"})
    )
    result = await client.converse("Salut", None, "fr-FR")

    assert result == ConversationReply("Bonjour.", "session-1")
    assert session.call["headers"] == {"Authorization": "Bearer secret"}
    assert isinstance(session.call["ssl"], aiohttp.Fingerprint)
    assert session.call["timeout"].sock_connect == 2
    assert session.call["timeout"].total == 20


@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError("offline"), TimeoutError()])
@pytest.mark.asyncio
async def test_unreachable_or_timed_out_holmes_uses_fallback(
    error: BaseException, caplog: pytest.LogCaptureFixture
) -> None:
    client, _session = _client(error)

    async def fallback(
        text: str, conversation_id: str | None, language: str, context: object
    ) -> ConversationReply:
        return ConversationReply("Réponse locale.", conversation_id)

    result = await HolmesConversationService(client, fallback).process(
        "Salut", "session-1", "fr", object()
    )
    assert result == ConversationReply("Holmes est indisponible. Réponse locale.", "session-1")
    assert "Holmes injoignable ou hors délai" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.asyncio
async def test_rejected_token_fallback_logs_without_disclosing_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _session = _client(_Response(401, {}))

    async def fallback(
        text: str, conversation_id: str | None, language: str, context: object
    ) -> ConversationReply:
        return ConversationReply("Réponse locale.", conversation_id)

    with caplog.at_level(logging.WARNING):
        result = await HolmesConversationService(client, fallback).process(
            "Salut", "session-1", "fr", object()
        )

    assert result.text.startswith("Holmes est indisponible.")
    assert "jeton Holmes refusé" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.asyncio
async def test_rejected_token_is_distinguished_by_client() -> None:
    client, _session = _client(_Response(401, {}))
    with pytest.raises(HolmesAuthenticationError):
        await client.converse("Salut", None, "fr")


@pytest.mark.asyncio
async def test_invalid_server_response_is_unavailable() -> None:
    client, _session = _client(_Response(200, {"unexpected": True}))
    with pytest.raises(HolmesUnavailableError):
        await client.converse("Salut", None, "fr")
