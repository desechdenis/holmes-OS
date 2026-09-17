from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from jarvis.interfaces.api.websocket import _authenticate_websocket
from jarvis.kernel.settings import settings


@pytest.mark.asyncio
async def test_websocket_accepts_matching_first_auth_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", SecretStr("secret-test"))
    websocket = AsyncMock()
    websocket.receive_json.return_value = {"type": "auth", "token": "secret-test"}

    assert await _authenticate_websocket(websocket) is True

    websocket.accept.assert_awaited_once()
    websocket.send_json.assert_awaited_once_with({"type": "auth_ok"})
    websocket.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_websocket_rejects_invalid_first_auth_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", SecretStr("secret-test"))
    websocket = AsyncMock()
    websocket.receive_json.return_value = {"type": "auth", "token": "mauvais"}

    assert await _authenticate_websocket(websocket) is False

    websocket.close.assert_awaited_once_with(code=4401, reason="Token invalide")
    websocket.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_websocket_without_api_auth_needs_no_auth_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", False)
    websocket = AsyncMock()

    assert await _authenticate_websocket(websocket) is True

    websocket.accept.assert_awaited_once()
    websocket.receive_json.assert_not_awaited()


def test_all_internal_websocket_clients_send_auth_first() -> None:
    paths = (
        "src/jarvis/interfaces/ui/static/home.js",
        "src/jarvis/interfaces/ui/static/command.html",
        "src/jarvis/interfaces/ui/static/index.html",
    )
    for path in paths:
        content = Path(path).read_text(encoding="utf-8")
        assert "JARVIS_API_TOKEN" in content
        assert "type: \"auth\"" in content or "type: 'auth'" in content
