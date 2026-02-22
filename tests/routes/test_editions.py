"""Tests for edition route handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from agent_stack.models.edition import Edition
from agent_stack.routes.editions import (
    cancel_title_edit,
    create_edition,
    delete_edition,
    edit_title_form,
    edition_detail,
    list_editions,
    publish_edition,
    update_title,
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

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.create.return_value = None
        repo.next_issue_number.return_value = _NEXT_ISSUE_NUMBER

        await create_edition(request)

        repo.create.assert_called_once()
        created_edition = repo.create.call_args[0][0]
        assert created_edition.content["title"] == f"Issue #{_NEXT_ISSUE_NUMBER}"
        assert created_edition.content["issue_number"] == _NEXT_ISSUE_NUMBER
        assert created_edition.content["sections"] == []


async def test_update_title() -> None:
    """PATCH title updates the edition content and persists."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Old Title", "sections": []})

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.get.return_value = edition
        repo.update.return_value = edition

        await update_title(request, edition_id="ed-1", title="New Title")

        repo.get.assert_called_once_with("ed-1", "ed-1")
        repo.update.assert_called_once_with(edition, "ed-1")
        assert edition.content["title"] == "New Title"


async def test_update_title_strips_whitespace() -> None:
    """PATCH title strips whitespace before saving."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "", "sections": []})

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.get.return_value = edition
        repo.update.return_value = edition

        await update_title(request, edition_id="ed-1", title="  Trimmed  ")

        assert edition.content["title"] == "Trimmed"


async def test_update_title_renders_display_partial() -> None:
    """PATCH title returns the display-mode partial."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Title", "sections": []})

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.get.return_value = edition
        repo.update.return_value = edition

        await update_title(request, edition_id="ed-1", title="Title")

        request.app.state.templates.TemplateResponse.assert_called_once_with(
            "partials/edition_title.html",
            {"request": request, "edition": edition, "editing": False},
        )


async def test_edit_title_form_renders_editing_partial() -> None:
    """GET title/edit returns the editing-mode partial."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Title", "sections": []})

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.get.return_value = edition

        await edit_title_form(request, edition_id="ed-1")

        request.app.state.templates.TemplateResponse.assert_called_once_with(
            "partials/edition_title.html",
            {"request": request, "edition": edition, "editing": True},
        )


async def test_cancel_title_edit_renders_display_partial() -> None:
    """GET title/cancel returns the display-mode partial."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Title", "sections": []})

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.get.return_value = edition

        await cancel_title_edit(request, edition_id="ed-1")

        request.app.state.templates.TemplateResponse.assert_called_once_with(
            "partials/edition_title.html",
            {"request": request, "edition": edition, "editing": False},
        )


async def test_delete_edition_soft_deletes() -> None:
    """POST delete soft-deletes the edition and redirects."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Title", "sections": []})

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.get.return_value = edition
        repo.soft_delete.return_value = edition

        response = await delete_edition(request, edition_id="ed-1")

        repo.get.assert_called_once_with("ed-1", "ed-1")
        repo.soft_delete.assert_called_once_with(edition, "ed-1")
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_edition_not_found() -> None:
    """POST delete on missing edition still redirects without error."""
    request = _make_request()

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.get.return_value = None

        response = await delete_edition(request, edition_id="missing")

        repo.soft_delete.assert_not_called()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_list_editions_renders_template() -> None:
    """GET /editions/ fetches all editions and renders the list template."""
    request = _make_request()
    editions = [Edition(id="ed-1", content={"title": "Issue #1", "sections": []})]

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
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

    with (
        patch("agent_stack.routes.editions.EditionRepository") as mock_ed_cls,
        patch("agent_stack.routes.editions.LinkRepository") as mock_link_cls,
        patch("agent_stack.routes.editions.AgentRunRepository") as mock_run_cls,
    ):
        ed_repo = AsyncMock()
        mock_ed_cls.return_value = ed_repo
        ed_repo.get.return_value = edition

        link_repo = AsyncMock()
        mock_link_cls.return_value = link_repo
        link_repo.get_by_edition.return_value = []

        run_repo = AsyncMock()
        mock_run_cls.return_value = run_repo

        await edition_detail(request, edition_id="ed-1")

        ed_repo.get.assert_called_once_with("ed-1", "ed-1")
        link_repo.get_by_edition.assert_called_once_with("ed-1")
        request.app.state.templates.TemplateResponse.assert_called_once()


async def test_publish_edition_calls_orchestrator() -> None:
    """POST /editions/{id}/publish invokes the orchestrator and redirects."""
    request = _make_request()
    orchestrator = MagicMock()
    orchestrator.handle_publish = AsyncMock()
    request.app.state.processor.orchestrator = orchestrator

    response = await publish_edition(request, edition_id="ed-1")

    assert response.status_code == _EXPECTED_REDIRECT_STATUS
    # Background task was created for the orchestrator
    assert len(request.app.state.setdefault.call_args_list) > 0


async def test_publish_edition_redirects() -> None:
    """POST /editions/{id}/publish redirects to the edition detail page."""
    request = _make_request()
    orchestrator = MagicMock()
    orchestrator.handle_publish = AsyncMock()
    request.app.state.processor.orchestrator = orchestrator

    response = await publish_edition(request, edition_id="ed-1")

    assert response.status_code == _EXPECTED_REDIRECT_STATUS
