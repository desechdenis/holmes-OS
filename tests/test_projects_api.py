from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.interfaces.api.projects import (
    ProjectCreateBody,
    create_project,
    preview_mission,
    start_mission,
)


@pytest.mark.asyncio
async def test_create_project_endpoint_only_prepares_plan() -> None:
    project = MagicMock(id="proj_api", status="planning")
    orchestrator = MagicMock()
    orchestrator.create_plan = AsyncMock(return_value=project)
    request = MagicMock()
    request.app.state.orchestrator = orchestrator

    result = await create_project(
        ProjectCreateBody(mission="Construire un rapport vérifié", timeout_minutes=45),
        request,
    )

    orchestrator.create_plan.assert_awaited_once_with(
        "Construire un rapport vérifié", timeout_minutes=45
    )
    orchestrator.start_project.assert_not_called()
    assert result == {"ok": True, "project_id": "proj_api", "status": "planning"}


@pytest.mark.asyncio
async def test_preview_mission_does_not_start_worker() -> None:
    project = MagicMock(id="proj_plan", status="planning")
    orchestrator = MagicMock()
    orchestrator.create_plan = AsyncMock(return_value=project)
    orchestrator._project_summary.return_value = {"id": "proj_plan", "steps": []}
    request = MagicMock()
    request.app.state.orchestrator = orchestrator

    result = await preview_mission(ProjectCreateBody(mission="Préparer un dossier"), request)

    orchestrator.create_plan.assert_awaited_once()
    orchestrator.start_project.assert_not_called()
    assert result["mission"]["id"] == "proj_plan"


@pytest.mark.asyncio
async def test_start_mission_requires_explicit_endpoint() -> None:
    project = MagicMock(id="proj_plan", status="planning")
    orchestrator = MagicMock()
    orchestrator.start_project.return_value = project
    request = MagicMock()
    request.app.state.orchestrator = orchestrator

    result = await start_mission("proj_plan", request)

    orchestrator.start_project.assert_called_once_with("proj_plan")
    assert result["project_id"] == "proj_plan"
