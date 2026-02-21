"""Tests for feedback route handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.routes.feedback import submit_feedback

_EXPECTED_REDIRECT_STATUS = 303


def _make_request() -> None:
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    return request


@pytest.mark.asyncio
async def test_submit_feedback_creates_feedback() -> None:
    """Verify submit feedback creates feedback."""
    request = _make_request()

    with patch("agent_stack.routes.feedback.FeedbackRepository") as mock_repo_cls:
        repo = AsyncMock()
        mock_repo_cls.return_value = repo

        response = await submit_feedback(
            request, edition_id="ed-1", section="intro", comment="Needs work"
        )

        repo.create.assert_called_once()
        created = repo.create.call_args[0][0]
        assert created.edition_id == "ed-1"
        assert created.section == "intro"
        assert created.comment == "Needs work"
        assert created.resolved is False
        assert response.status_code == _EXPECTED_REDIRECT_STATUS
