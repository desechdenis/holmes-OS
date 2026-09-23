# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from jarvis.engine.proactive.initiative_generator import InitiativeGenerator
from jarvis.engine.proactive.store import InitiativeStore
from jarvis.kernel.http_errors import raise_api_error

router = APIRouter()


class RectifyBody(BaseModel):
    correction: str


class ConfirmBody(BaseModel):
    draft_content: str | None = None


class MissionPreviewBody(BaseModel):
    timeout_minutes: int = 30


class SnoozeBody(BaseModel):
    minutes: int = 60


# ── Initiatives API ───────────────────────────────────────────────────────────


@router.get("/api/initiatives")
async def get_initiatives() -> list[dict]:
    """Initiatives en attente (mode VALIDATE).

    Réponse étendue PHASE 6 avec les 7 champs §10.1 (autonomy_level,
    permission_required, cost_max_usd, risk, deadline, next_action,
    requires_validation) — consommée par dashboard.js pour afficher le
    badge "NIVEAU 5 — VALIDATION FORCÉE" et le bloc gouvernance.
    Ajout rétro-compatible : aucun champ historique retiré.
    """

    store = InitiativeStore()
    initiatives = store.load_actionable(days=7, limit=3)
    return [
        {
            "id": i.id,
            "type": i.type,
            "title": i.title,
            "context": i.context,
            "reasoning": i.reasoning,
            "action": i.action,
            "priority": i.priority,
            "execution_mode": i.execution_mode,
            "draft_content": i.draft_content,
            "mission_description": i.mission_description,
            "project_id": i.project_id,
            "sources": i.sources,
            "status": i.status,
            "created_at": i.created_at.isoformat(),
            # ── PHASE 6 §10.1 — champs gouvernance ──
            "autonomy_level": int(i.autonomy_level),
            "permission_required": i.permission_required,
            "cost_max_usd": i.cost_max_usd,
            "risk": i.risk,
            "deadline": i.deadline.isoformat() if i.deadline else None,
            "due_at": i.due_at.isoformat() if i.due_at else None,
            "task_id": i.task_id,
            "next_action": i.next_action,
            "requires_validation": i.requires_validation,
            "available_actions": _available_actions(i.type),
        }
        for i in initiatives
    ]


def _available_actions(initiative_type: object) -> list[str]:
    value = str(initiative_type)
    if value == "reminder":
        return ["acknowledge", "snooze", "to_task", "dismiss"]
    if value == "auto_task":
        return ["preview_mission", "dismiss"]
    if value == "draft_response":
        return ["prepare_draft", "dismiss"]
    return ["acknowledge", "to_task", "dismiss"]


@router.post("/api/initiatives/{initiative_id}/acknowledge")
async def acknowledge_initiative(initiative_id: str) -> dict:
    store = InitiativeStore()
    if not store.get_by_id(initiative_id):
        raise_api_error("JRV-API-003", 404, "Initiative introuvable")
    store.update_status(initiative_id, "done")
    return {"status": "done"}


@router.post("/api/initiatives/{initiative_id}/snooze")
async def snooze_initiative(initiative_id: str, body: SnoozeBody) -> dict:
    store = InitiativeStore()
    if not store.get_by_id(initiative_id):
        raise_api_error("JRV-API-003", 404, "Initiative introuvable")
    due_at = datetime.now() + timedelta(minutes=min(max(body.minutes, 5), 10080))
    store.update_initiative(
        initiative_id, {"due_at": due_at.isoformat(), "status": "snoozed"}
    )
    return {"status": "snoozed", "due_at": due_at.isoformat()}


@router.post("/api/initiatives/{initiative_id}/to-task")
async def initiative_to_task(initiative_id: str, request: Request) -> dict:
    store = InitiativeStore()
    initiative = store.get_by_id(initiative_id)
    if not initiative:
        raise_api_error("JRV-API-003", 404, "Initiative introuvable")
    task_store = getattr(request.app.state.container, "canonical_tasks", None)
    if task_store is None:
        raise_api_error("JRV-API-005", 503, "Liste de tâches Soul indisponible")
    task = await task_store.create_task(initiative.action or initiative.title)
    store.update_initiative(
        initiative_id, {"task_id": task.id, "status": "converted_to_task"}
    )
    return {"status": "converted_to_task", "task_id": task.id, "text": task.text}


@router.post("/api/initiatives/{initiative_id}/approve")
async def approve_initiative(initiative_id: str, request: Request) -> dict:
    """Compatibilité UI historique, déléguée au seul exécuteur gouverné.

    Un brouillon d'e-mail passe donc à ``awaiting_confirm`` et ne peut plus être
    envoyé directement par cet ancien endpoint.
    """
    executor = getattr(request.app.state, "initiative_executor", None)
    if not executor:
        raise_api_error("JRV-API-005", 503, "InitiativeExecutor non disponible")
    return await executor.run(initiative_id)


@router.post("/api/initiatives/{initiative_id}/reject")
async def reject_initiative(initiative_id: str) -> dict:

    InitiativeStore().update_status(initiative_id, "rejected")
    return {"status": "rejected"}


@router.post("/api/initiatives/{initiative_id}/rectify")
async def rectify_initiative(initiative_id: str, body: RectifyBody, request: Request) -> dict:

    store = InitiativeStore()
    init = store.get_by_id(initiative_id)
    if not init:
        raise_api_error("JRV-API-003", 404, "Initiative introuvable")

    _container = request.app.state.container
    generator = InitiativeGenerator(
        llm=_container.background_llm,
        user_firstname=_container.settings.display_name,
        user_profile=_container.settings.user_profile,
    )
    new_init = await generator.rectify(init, body.correction)
    if not new_init:
        raise_api_error("JRV-API-001", 500, "Régénération échouée")

    store.update_initiative(
        initiative_id,
        {
            "title": new_init.title,
            "context": new_init.context,
            "reasoning": new_init.reasoning,
            "action": new_init.action,
            "priority": new_init.priority,
            "execution_mode": new_init.execution_mode,
            "draft_content": new_init.draft_content,
            "mission_description": new_init.mission_description,
        },
    )

    return {
        "id": initiative_id,
        "type": new_init.type,
        "title": new_init.title,
        "context": new_init.context,
        "reasoning": new_init.reasoning,
        "action": new_init.action,
        "priority": new_init.priority,
        "execution_mode": new_init.execution_mode,
        "draft_content": new_init.draft_content,
        "mission_description": new_init.mission_description,
        "created_at": init.created_at.isoformat(),
    }


# ── Proactive initiatives v2 (executor) ──────────────────────────────────────


@router.get("/api/proactive/initiatives")
async def list_proactive_initiatives(
    days: int = Query(default=7, ge=1, le=30),
    status: str | None = Query(default=None),
) -> list[dict]:
    """Liste les initiatives récentes (multi-jours).

    status=pending|done|dismissed|… ou absent=tous.
    """

    store = InitiativeStore()
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    items = store.list_recent(days=days, statuses=statuses)
    return [
        {
            "id": i.id,
            "type": i.type,
            "title": i.title,
            "context": i.context,
            "reasoning": i.reasoning,
            "action": i.action,
            "priority": i.priority,
            "execution_mode": i.execution_mode,
            "draft_content": i.draft_content,
            "mission_description": i.mission_description,
            "status": i.status,
            "created_at": i.created_at.isoformat(),
        }
        for i in items
    ]


@router.post("/api/proactive/initiatives/{initiative_id}/run")
async def run_initiative(initiative_id: str, request: Request) -> dict:
    """Déclenche l'exécution pilotée d'une initiative (étape 1/2 pour les actions sensibles)."""
    executor = getattr(request.app.state, "initiative_executor", None)
    if not executor:
        raise_api_error("JRV-API-005", 503, "InitiativeExecutor non disponible")
    return await executor.run(initiative_id)


@router.post("/api/proactive/initiatives/{initiative_id}/mission-preview")
async def preview_initiative_mission(
    initiative_id: str, body: MissionPreviewBody, request: Request
) -> dict:
    """Transforme une initiative en plan, sans exécuter ce plan."""
    store = InitiativeStore()
    initiative = store.get_by_id(initiative_id)
    if not initiative:
        raise_api_error("JRV-API-003", 404, "Initiative introuvable")
    mission = (initiative.mission_description or initiative.action or initiative.title).strip()
    timeout = min(max(body.timeout_minutes, 1), 240)
    project = await request.app.state.orchestrator.create_plan(mission, timeout)
    store.update_initiative(
        initiative_id,
        {"project_id": project.id, "status": "awaiting_mission_confirm"},
    )
    summary = request.app.state.orchestrator._project_summary(project)
    return {"status": "plan_ready", "mission": summary}


@router.post("/api/proactive/initiatives/{initiative_id}/mission-confirm")
async def confirm_initiative_mission(initiative_id: str, request: Request) -> dict:
    """Lance le plan lié et conserve le lien Initiative → Mission."""
    store = InitiativeStore()
    initiative = store.get_by_id(initiative_id)
    if not initiative or not initiative.project_id:
        raise_api_error("JRV-API-003", 404, "Aucun plan lié à cette initiative")
    try:
        project = request.app.state.orchestrator.start_project(initiative.project_id)
    except ValueError as exc:
        raise_api_error("JRV-API-001", 409, str(exc), cause=exc)
    store.update_status(initiative_id, "in_progress")
    return {"status": "mission_started", "project_id": project.id}


@router.post("/api/proactive/initiatives/{initiative_id}/confirm")
async def confirm_initiative(initiative_id: str, body: ConfirmBody, request: Request) -> dict:
    """2e confirmation pour les actions sensibles (envoi mail après brouillon prêt)."""
    executor = getattr(request.app.state, "initiative_executor", None)
    if not executor:
        raise_api_error("JRV-API-005", 503, "InitiativeExecutor non disponible")
    return await executor.confirm(initiative_id, body.draft_content)


@router.post("/api/proactive/initiatives/{initiative_id}/dismiss")
async def dismiss_initiative(initiative_id: str) -> dict:
    """Marque l'initiative comme ignorée (dismissed)."""

    store = InitiativeStore()
    init = store.get_by_id(initiative_id)
    if not init:
        raise_api_error("JRV-API-003", 404, "Initiative introuvable")
    store.update_status(initiative_id, "dismissed")
    return {"status": "dismissed"}


# ── Proactive engine API ──────────────────────────────────────────────────────


@router.post("/api/proactive/run")
async def run_proactive_now(request: Request) -> dict:
    """Force un cycle proactif immédiat."""
    import asyncio

    engine = getattr(request.app.state, "proactive_engine", None)
    if not engine:
        raise_api_error("JRV-API-005", 503, "ProactiveEngine non disponible")
    asyncio.create_task(engine.run_now(), name="proactive-manual")
    return {"triggered": True}


@router.get("/api/proactive/status")
async def proactive_status(request: Request) -> dict:
    """Statut du moteur proactif (dernière exécution, prochaine)."""
    engine = getattr(request.app.state, "proactive_engine", None)
    if not engine:
        return {"running": False}
    last_run = engine._last_run.isoformat() if engine._last_run else None
    return {
        "running": engine._running,
        "interval_s": engine._interval,
        "last_run": last_run,
    }
