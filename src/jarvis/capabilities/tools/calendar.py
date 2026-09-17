# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx
from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.error_collector import collector  # jrv: autofix

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_CAL_BASE = "https://www.googleapis.com/calendar/v3"

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    _HAS_GOOGLE = True
except ImportError:
    collector.error("JRV-TOL-001", "JRV-TOL-001")
    _HAS_GOOGLE = False


def _load_creds(token_path: Path, credentials_path: Path) -> Credentials:
    """Charge et rafraîchit les credentials OAuth2 (bloquant — exécuté dans un thread)."""
    if not _HAS_GOOGLE:
        raise RuntimeError("google-api-python-client non installé.")

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                collector.error("JRV-TOL-001", "JRV-TOL-001")
                token_path.unlink(missing_ok=True)
                creds = None

        if not creds or not creds.valid:
            # Do not start an InstalledAppFlow here.  This method may run in a
            # background collector, where a browser prompt every cycle is both
            # surprising and impossible to complete reliably.
            raise RuntimeError(
                "Compte Google Calendar non connecté. "
                "Ouvre Intégrations, puis connecte Google Calendar."
            )

        token_path.write_text(creds.to_json())

    return creds


def _format_events_by_calendar(events_by_calendar: list[tuple[str, list[dict]]]) -> list[str]:
    """Sort events from every visible calendar and retain their source label."""
    rows: list[tuple[str, str]] = []
    for calendar_name, events in events_by_calendar:
        for event in events:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "?"))
            rows.append(
                (
                    start,
                    f"- {start} · [{calendar_name}] {event.get('summary', '(sans titre)')}",
                )
            )
    return [line for _, line in sorted(rows, key=lambda row: row[0])]


class CalendarListTool(Tool):
    """Liste les prochains événements de tous les calendriers Google visibles."""

    name = "list_calendar_events"
    description = (
        "Liste les prochains événements du Google Calendar de l'utilisateur. "
        "Utilise cet outil quand l'utilisateur demande son agenda, son planning ou ses rendez-vous."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "Nombre de jours à afficher (défaut : 7)",
            },
        },
        "required": [],
    }

    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        self._creds = credentials_path
        self._token = token_path

    async def execute(self, days_ahead: int = 7, **_: object) -> ToolResult:
        if not _HAS_GOOGLE:
            return ToolResult(content="google-api-python-client non installé.", is_error=True)

        try:
            creds = await asyncio.to_thread(_load_creds, self._token, self._creds)
        except RuntimeError as exc:
            # No OAuth grant yet is expected while the connector is being set
            # up.  The proactive collector will quietly skip Calendar.
            return ToolResult(content=str(exc), is_error=True)
        except Exception as e:
            collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
            return ToolResult(content=f"Erreur credentials : {e}", is_error=True)

        days_ahead = max(1, min(days_ahead, 365))
        now = datetime.now(UTC)
        params = {
            "timeMin": now.isoformat(),
            "timeMax": (now + timedelta(days=days_ahead)).isoformat(),
            "maxResults": days_ahead * 5,
            "singleEvents": "true",
            "orderBy": "startTime",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                calendar_list = await client.get(
                    f"{_CAL_BASE}/users/me/calendarList",
                    headers={"Authorization": f"Bearer {creds.token}"},
                )
                calendar_list.raise_for_status()
                calendars = [
                    (str(item.get("id", "")), str(item.get("summary", "Agenda")))
                    for item in calendar_list.json().get("items", [])
                    if item.get("id")
                    and not item.get("hidden", False)
                    and item.get("selected", True)
                ]

                async def fetch_events(
                    calendar_id: str, calendar_name: str
                ) -> tuple[str, list[dict]] | None:
                    try:
                        response = await client.get(
                            f"{_CAL_BASE}/calendars/{quote(calendar_id, safe='')}/events",
                            headers={"Authorization": f"Bearer {creds.token}"},
                            params=params,
                        )
                        response.raise_for_status()
                        return calendar_name, response.json().get("items", [])
                    except Exception as exc:  # noqa: BLE001 — isole un agenda inaccessible
                        collector.warning("JRV-TOL-001", "JRV-TOL-001", cause=exc)
                        logger.warning(
                            "Calendar skipped",
                            calendar=calendar_name,
                            error=str(exc),
                        )
                        return None

                calendar_results = await asyncio.gather(
                    *(fetch_events(calendar_id, name) for calendar_id, name in calendars)
                )
                events_by_calendar = [result for result in calendar_results if result is not None]

            lines = _format_events_by_calendar(list(events_by_calendar))
            if not lines:
                return ToolResult(content="Aucun événement prévu.")

            content = "\n".join(lines)
            logger.debug("Calendar events listed", count=len(lines))
            return ToolResult(content=content)

        except Exception as e:
            collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
            logger.error(f"Calendar list error: {type(e).__name__}: {e}")
            return ToolResult(content=f"Erreur Calendar : {e}", is_error=True)


class CalendarCreateTool(Tool):
    """Crée un événement dans Google Calendar."""

    name = "create_calendar_event"
    description = (
        "Crée un nouvel événement dans le Google Calendar de l'utilisateur. "
        "Utilise cet outil quand l'utilisateur veut ajouter un rendez-vous ou un rappel."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titre de l'événement"},
            "start": {
                "type": "string",
                "description": "Début ISO 8601 : 2024-01-15T14:00:00",
            },
            "end": {
                "type": "string",
                "description": "Fin ISO 8601 : 2024-01-15T15:00:00",
            },
            "description": {"type": "string", "description": "Description optionnelle"},
        },
        "required": ["title", "start", "end"],
    }

    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        self._creds = credentials_path
        self._token = token_path

    async def execute(
        self, title: str, start: str, end: str, description: str = "", **_: object
    ) -> ToolResult:
        if not _HAS_GOOGLE:
            return ToolResult(content="google-api-python-client non installé.", is_error=True)

        try:
            creds = await asyncio.to_thread(_load_creds, self._token, self._creds)
        except RuntimeError as exc:
            return ToolResult(content=str(exc), is_error=True)
        except Exception as e:
            collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
            return ToolResult(content=f"Erreur credentials : {e}", is_error=True)

        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start, "timeZone": "Europe/Paris"},
            "end": {"dateTime": end, "timeZone": "Europe/Paris"},
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{_CAL_BASE}/calendars/primary/events",
                    headers={
                        "Authorization": f"Bearer {creds.token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()

            created = resp.json()
            logger.info("Calendar event created", title=title, event_id=created.get("id"))
            return ToolResult(content=f"Événement créé : {created.get('htmlLink', title)}")

        except Exception as e:
            collector.error("JRV-TOL-001", "JRV-TOL-001", cause=e)
            logger.error(f"Calendar create error: {type(e).__name__}: {e}")
            return ToolResult(content=f"Erreur Calendar : {e}", is_error=True)
