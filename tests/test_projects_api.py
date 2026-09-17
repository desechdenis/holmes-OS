from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.interfaces.api.projects import ProjectCreateBody, create_project


@pytest.mark.asyncio
async def test_create_project_endpoint_launches_orchestrator() -> None:
    project = MagicMock(id="proj_api", status="running")
    orchestrator = MagicMock()
    orchestrator.create_and_run = AsyncMock(return_value=project)
    request = MagicMock()
    request.app.state.orchestrator = orchestrator

    result = await create_project(
        ProjectCreateBody(mission="Construire un rapport vérifié", timeout_minutes=45),
        request,
    )

    orchestrator.create_and_run.assert_awaited_once_with(
        "Construire un rapport vérifié", timeout_minutes=45
    )
    assert result == {"ok": True, "project_id": "proj_api", "status": "running"}
