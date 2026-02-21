"""Tests for edition route handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.models.edition import Edition
from agent_stack.routes.editions import (
    cancel_title_edit,
    create_edition,
    delete_edition,
    edit_title_form,
    update_title,
)

_EXPECTED_REDIRECT_STATUS = 303


def _make_request(_app_state: object | None = None) -> None:
    """Create a mock request with app state."""
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    return request


@pytest.mark.asyncio
async def test_create_edition_with_title() -> None:
    """Creating an edition with a title stores it in content."""
    request = _make_request()

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.create.return_value = None

        await create_edition(request, title="Weekly Roundup #1")

        repo.create.assert_called_once()
        created_edition = repo.create.call_args[0][0]
        assert created_edition.content["title"] == "Weekly Roundup #1"
        assert created_edition.content["sections"] == []


@pytest.mark.asyncio
async def test_create_edition_with_empty_title() -> None:
    """Creating an edition without a title stores empty string."""
    request = _make_request()

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.create.return_value = None

        await create_edition(request, title="")

        created_edition = repo.create.call_args[0][0]
        assert created_edition.content["title"] == ""


@pytest.mark.asyncio
async def test_create_edition_strips_whitespace() -> None:
    """Title whitespace is stripped on creation."""
    request = _make_request()

    with patch("agent_stack.routes.editions.EditionRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo
        repo.create.return_value = None

        await create_edition(request, title="  Padded Title  ")

        created_edition = repo.create.call_args[0][0]
        assert created_edition.content["title"] == "Padded Title"


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
