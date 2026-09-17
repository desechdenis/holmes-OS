from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.capabilities.tools import calendar, gmail
from jarvis.engine.proactive.collectors import email
from jarvis.interfaces.api.google_oauth import _GOOGLE_AUTH_URI, _redirect_uri


def test_google_uses_the_current_oauth_v2_authorization_endpoint() -> None:
    assert _GOOGLE_AUTH_URI == "https://accounts.google.com/o/oauth2/v2/auth"


def test_google_callback_is_stable_on_the_google_supported_localhost_origin() -> None:
    # Google matches the redirect URI exactly, so it must not depend on the
    # hostname used by the browser to reach the local UI.
    assert _redirect_uri(None, "gmail") == "http://localhost:8000/api/google/callback/gmail"
    assert _redirect_uri(None, "calendar") == "http://localhost:8000/api/google/callback/calendar"


def test_gmail_missing_token_never_starts_a_local_oauth_server(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="non connecté"):
        gmail._load_gmail_creds(tmp_path / "credentials.json", tmp_path / "missing-token.json")


def test_calendar_missing_token_never_starts_a_local_oauth_server(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="non connecté"):
        calendar._load_creds(tmp_path / "missing-token.json", tmp_path / "credentials.json")


def test_email_collector_missing_token_stays_unattended(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="non connecté"):
        email._load_gmail_creds(tmp_path / "missing-token.json")


def test_calendar_events_are_sorted_and_keep_their_calendar_name() -> None:
    lines = calendar._format_events_by_calendar(
        [
            ("Famille", [{"start": {"date": "2026-10-02"}, "summary": "Anniversaire"}]),
            (
                "alice@example.invalid",
                [{"start": {"dateTime": "2026-10-01T12:00:00+02:00"}, "summary": "Rendez-vous"}],
            ),
        ]
    )

    assert lines == [
        "- 2026-10-01T12:00:00+02:00 · [alice@example.invalid] Rendez-vous",
        "- 2026-10-02 · [Famille] Anniversaire",
    ]


@pytest.mark.asyncio
async def test_calendar_applies_time_window_and_skips_one_broken_calendar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen_params: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict, *, broken: bool = False) -> None:
            self._payload = payload
            self._broken = broken

        def raise_for_status(self) -> None:
            if self._broken:
                raise RuntimeError("agenda inaccessible")

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self):  # noqa: ANN204
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str, **kwargs: object) -> FakeResponse:
            if url.endswith("/users/me/calendarList"):
                return FakeResponse(
                    {
                        "items": [
                            {"id": "family", "summary": "Famille", "selected": True},
                            {"id": "broken", "summary": "Cassé", "selected": True},
                        ]
                    }
                )
            seen_params.append(kwargs["params"])  # type: ignore[arg-type]
            if "/broken/" in url:
                return FakeResponse({}, broken=True)
            return FakeResponse(
                {"items": [{"start": {"date": "2026-09-18"}, "summary": "École"}]}
            )

    async def fake_load(*_: object) -> SimpleNamespace:
        return SimpleNamespace(token="google-token")

    monkeypatch.setattr(calendar.asyncio, "to_thread", fake_load)
    monkeypatch.setattr(calendar.httpx, "AsyncClient", FakeClient)
    tool = calendar.CalendarListTool(tmp_path / "credentials.json", tmp_path / "token.json")

    result = await tool.execute(days_ahead=3)

    assert result.is_error is False
    assert "[Famille] École" in result.content
    assert len(seen_params) == 2
    start = datetime.fromisoformat(str(seen_params[0]["timeMin"]))
    end = datetime.fromisoformat(str(seen_params[0]["timeMax"]))
    assert 2.99 < (end - start).total_seconds() / 86400 < 3.01
