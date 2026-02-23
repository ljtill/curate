"""Tests for edition route handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import BackgroundTasks

from curate_common.models.edition import Edition
from curate_web.routes.editions import (
    create_edition,
    delete_edition,
    edition_detail,
    list_editions,
    publish_edition,
)
from tests.web.routes.runtime_helpers import make_runtime

_EXPECTED_REDIRECT_STATUS = 303
_NEXT_ISSUE_NUMBER = 3


def _make_request(_app_state: object | None = None) -> MagicMock:
    """Create a mock request with app state."""
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.runtime = make_runtime(
        cosmos=request.app.state.cosmos,
        templates=request.app.state.templates,
    )
    return request


async def test_create_edition_auto_numbers() -> None:
    """Creating an edition auto-generates title and issue_number."""
    request = _make_request()
    created = Edition(
        id="ed-new",
        content={
            "title": f"Issue #{_NEXT_ISSUE_NUMBER}",
            "issue_number": _NEXT_ISSUE_NUMBER,
            "sections": [],
        },
    )

    with patch(
        "curate_web.routes.editions.edition_svc.create_edition",
        new_callable=AsyncMock,
    ) as mock_create:
        mock_create.return_value = created

        await create_edition(request)

        mock_create.assert_called_once()
        edition = mock_create.return_value
        assert edition.content["title"] == f"Issue #{_NEXT_ISSUE_NUMBER}"
        assert edition.content["issue_number"] == _NEXT_ISSUE_NUMBER
        assert edition.content["sections"] == []


async def test_delete_edition_soft_deletes() -> None:
    """POST delete soft-deletes the edition and redirects."""
    request = _make_request()

    with patch(
        "curate_web.routes.editions.edition_svc.delete_edition",
        new_callable=AsyncMock,
    ) as mock_delete:
        response = await delete_edition(request, edition_id="ed-1")

        mock_delete.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_edition_not_found() -> None:
    """POST delete on missing edition still redirects without error."""
    request = _make_request()

    with patch(
        "curate_web.routes.editions.edition_svc.delete_edition",
        new_callable=AsyncMock,
    ) as mock_delete:
        response = await delete_edition(request, edition_id="missing")

        mock_delete.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_list_editions_redirects_to_dashboard() -> None:
    """GET /editions/ redirects to dashboard."""
    request = _make_request()

    response = await list_editions(request)

    assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_edition_detail_renders_template() -> None:
    """GET /editions/{id} fetches workspace data and renders workspace template."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Issue #1", "sections": []})

    with patch(
        "curate_web.routes.editions.edition_svc.get_workspace_data",
        new_callable=AsyncMock,
    ) as mock_workspace:
        mock_workspace.return_value = {
            "edition": edition,
            "links": [],
            "unattached_links": [],
            "agent_runs": [],
            "feedback": [],
            "links_by_id": {},
        }

        await edition_detail(request, edition_id="ed-1")

        mock_workspace.assert_called_once()
        request.app.state.templates.TemplateResponse.assert_called_once()
        call_args = request.app.state.templates.TemplateResponse.call_args
        assert call_args[0][0] == "workspace.html"


async def test_publish_edition_schedules_background_publish() -> None:
    """POST /editions/{id}/publish schedules publish and redirects."""
    request = _make_request()
    background_tasks = BackgroundTasks()
    event_publisher = MagicMock()
    request.app.state.runtime.event_publisher = event_publisher

    with patch(
        "curate_web.routes.editions.edition_svc.publish_edition",
        new_callable=AsyncMock,
    ) as mock_publish:
        response = await publish_edition(
            request,
            edition_id="ed-1",
            background_tasks=background_tasks,
        )
        await background_tasks()

    assert response.status_code == _EXPECTED_REDIRECT_STATUS
    assert len(background_tasks.tasks) == 1
    mock_publish.assert_awaited_once_with("ed-1", event_publisher)


async def test_publish_edition_redirects() -> None:
    """POST /editions/{id}/publish redirects to the edition detail page."""
    request = _make_request()
    background_tasks = BackgroundTasks()
    request.app.state.runtime.event_publisher = MagicMock()

    response = await publish_edition(
        request,
        edition_id="ed-1",
        background_tasks=background_tasks,
    )

    assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_publish_edition_skips_when_pipeline_unavailable() -> None:
    """POST /editions/{id}/publish safely redirects when pipeline is unavailable."""
    request = _make_request()
    background_tasks = BackgroundTasks()
    request.app.state.runtime.event_publisher = None

    response = await publish_edition(
        request,
        edition_id="ed-1",
        background_tasks=background_tasks,
    )

    assert response.status_code == _EXPECTED_REDIRECT_STATUS
    assert background_tasks.tasks == []
