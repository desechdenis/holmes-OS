# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel

from jarvis.kernel.error_collector import collector  # jrv: autofix
from jarvis.kernel.http_errors import raise_api_error
from jarvis.kernel.settings import settings

router = APIRouter(prefix="/api")

# Compatibilité pour les consommateurs Notion historiques (briefings/plugins).
# Le tableau /api/tasks n'utilise plus ces constantes lorsque Soul est configuré.
_NOTION_VERSION = "2022-06-28"


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.notion_token.get_secret_value()}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }

# ── Models ────────────────────────────────────────────────────


class Task(BaseModel):
    id: str
    text: str
    done: bool


class TasksResponse(BaseModel):
    tasks: list[Task]


class TaskCreate(BaseModel):
    text: str


class TaskPatch(BaseModel):
    done: bool | None = None
    text: str | None = None


class CalEvent(BaseModel):
    time: str
    name: str
    subtitle: str


class EventsResponse(BaseModel):
    events: list[CalEvent]


# ── Tâches canoniques Soul ────────────────────────────────────


def _task_store(request: Request):  # noqa: ANN202
    store = getattr(request.app.state, "canonical_tasks", None)
    if store is None:
        raise_api_error("JRV-API-005", 503, "Liste de tâches Soul non configurée")
    return store


@router.get("/tasks", response_model=TasksResponse)
async def get_tasks(request: Request) -> TasksResponse:
    try:
        tasks = await _task_store(request).list_tasks()
    except Exception as e:
        collector.error("JRV-API-001", "JRV-API-001", cause=e)
        logger.error("Soul tasks widget error", error=str(e))
        raise_api_error("JRV-API-001", 502, "Lecture des tâches Soul impossible", cause=e)
    return TasksResponse(tasks=[Task(id=t.id, text=t.text, done=t.done) for t in tasks])


@router.post("/tasks", response_model=Task)
async def create_task(body: TaskCreate, request: Request) -> Task:
    task = await _task_store(request).create_task(body.text)
    return Task(id=task.id, text=task.text, done=task.done)


@router.patch("/tasks/{block_id}", response_model=Task)
async def update_task(block_id: str, body: TaskPatch, request: Request) -> Task:
    try:
        task = await _task_store(request).update_task(
            block_id, text=body.text, done=body.done
        )
    except KeyError as exc:
        raise_api_error("JRV-API-003", 404, "Tâche Soul introuvable", cause=exc)
    return Task(id=task.id, text=task.text, done=task.done)


@router.delete("/tasks/{block_id}")
async def delete_task(block_id: str, request: Request) -> dict:
    deleted = await _task_store(request).delete_task(block_id)
    if not deleted:
        raise_api_error("JRV-API-003", 404, "Tâche Soul introuvable")
    return {"ok": True}


# ── Google Calendar events ────────────────────────────────────

_cal_cache: list[CalEvent] = []
_cal_cache_ts: datetime | None = None
_cal_lock = asyncio.Lock()
_CAL_TTL = 300  # secondes


def _load_calendar_creds(token_path: Path):  # noqa: ANN202
    """Charge et rafraîchit les credentials Calendar OAuth2 (bloquant)."""
    from google.auth.transport.requests import Request as GRequest
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(
        str(token_path),
        ["https://www.googleapis.com/auth/calendar.readonly"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(GRequest())
    return creds


async def _fetch_today_events() -> list[CalEvent]:
    try:
        from google.oauth2.credentials import Credentials  # noqa: F401
    except ImportError:
        collector.error("JRV-API-001", "JRV-API-001")
        logger.warning("google-api-python-client non installé")
        return []

    token_path = Path(settings.google_token_path)
    if not token_path.exists():
        return []

    try:
        creds = await asyncio.to_thread(_load_calendar_creds, token_path)
    except Exception as e:
        collector.error("JRV-API-001", "JRV-API-001", cause=e)
        logger.error("Calendar widget creds error", error=str(e))
        return []

    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    params = {
        "timeMin": start_of_day.isoformat(),
        "timeMax": end_of_day.isoformat(),
        "maxResults": 15,
        "singleEvents": "true",
        "orderBy": "startTime",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {creds.token}"},
            params=params,
        )
        resp.raise_for_status()

    events: list[CalEvent] = []
    for item in resp.json().get("items", []):
        start = item["start"].get("dateTime", item["start"].get("date", ""))
        if "T" in start:
            dt = datetime.fromisoformat(start)
            time_str = dt.strftime("%H:%M")
        else:
            time_str = "Journée"

        name = item.get("summary", "(sans titre)")
        subtitle = (item.get("location") or "").strip()
        if not subtitle:
            desc = (item.get("description") or "").strip()
            subtitle = desc.split("\n")[0][:40] if desc else ""

        events.append(CalEvent(time=time_str, name=name, subtitle=subtitle))

    return events


@router.get("/events", response_model=EventsResponse)
async def get_events() -> EventsResponse:
    global _cal_cache, _cal_cache_ts

    # Servir le cache si < TTL — évite les appels concurrents à Google API
    now = datetime.now(UTC)
    if _cal_cache_ts and (now - _cal_cache_ts).total_seconds() < _CAL_TTL:
        return EventsResponse(events=_cal_cache)

    # Un seul appel API à la fois — les autres attendent et réutilisent le résultat
    async with _cal_lock:
        # Re-check après avoir acquis le lock (un autre a peut-être déjà rafraîchi)
        if _cal_cache_ts and (now - _cal_cache_ts).total_seconds() < _CAL_TTL:
            return EventsResponse(events=_cal_cache)
        try:
            events = await _fetch_today_events()
            _cal_cache = events
            _cal_cache_ts = datetime.now(UTC)
            return EventsResponse(events=events)
        except Exception as e:
            collector.error("JRV-API-001", "JRV-API-001", cause=e)
            logger.error("Calendar widget error", error=str(e))
            return EventsResponse(events=_cal_cache)  # retourne le cache périmé si erreur
