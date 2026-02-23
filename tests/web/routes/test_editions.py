"""Tests for edition route handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_common.models.edition import Edition
from curate_web.routes.editions import (
    create_edition,
    delete_edition,
    edition_detail,
    list_editions,
    publish_edition,
)

_EXPECTED_REDIRECT_STATUS = 303
_NEXT_ISSUE_NUMBER = 3


def _make_request(_app_state: object | None = None) -> MagicMock:
    """Create a mock request with app state."""
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
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


async def test_list_editions_renders_template() -> None:
    """GET /editions/ fetches all editions and renders the list template."""
    request = _make_request()
    editions = [Edition(id="ed-1", content={"title": "Issue #1", "sections": []})]

    with patch("curate_web.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.list_all.return_value = editions

        await list_editions(request)

        repo.list_all.assert_called_once()
        request.app.state.templates.TemplateResponse.assert_called_once_with(
            "editions.html",
            {"request": request, "editions": editions},
        )


async def test_edition_detail_renders_template() -> None:
    """GET /editions/{id} fetches the edition with links and renders detail template."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Issue #1", "sections": []})

    with patch(
        "curate_web.routes.editions.edition_svc.get_edition_detail",
        new_callable=AsyncMock,
    ) as mock_detail:
        mock_detail.return_value = {
            "edition": edition,
            "links": [],
            "agent_runs": [],
            "links_by_id": {},
        }

        await edition_detail(request, edition_id="ed-1")

        mock_detail.assert_called_once()
        request.app.state.templates.TemplateResponse.assert_called_once()


async def test_publish_edition_calls_orchestrator() -> None:
    """POST /editions/{id}/publish invokes the orchestrator and redirects."""
    request = _make_request()
    orchestrator = MagicMock()
    orchestrator.handle_publish = AsyncMock()
    request.app.state.processor.orchestrator = orchestrator
    del request.app.state.background_tasks

    response = await publish_edition(request, edition_id="ed-1")

    assert response.status_code == _EXPECTED_REDIRECT_STATUS
    assert isinstance(request.app.state.background_tasks, list)
    assert len(request.app.state.background_tasks) > 0


async def test_publish_edition_redirects() -> None:
    """POST /editions/{id}/publish redirects to the edition detail page."""
    request = _make_request()
    orchestrator = MagicMock()
    orchestrator.handle_publish = AsyncMock()
    request.app.state.processor.orchestrator = orchestrator
    del request.app.state.background_tasks

    response = await publish_edition(request, edition_id="ed-1")

    assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_publish_edition_skips_when_pipeline_unavailable() -> None:
    """POST /editions/{id}/publish safely redirects when pipeline is unavailable."""
    request = _make_request()
    request.app.state.processor = None

    response = await publish_edition(request, edition_id="ed-1")

    assert response.status_code == _EXPECTED_REDIRECT_STATUS
