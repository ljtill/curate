"""Tests for feedback route handler."""

from unittest.mock import AsyncMock, MagicMock, patch

from agent_stack.routes.feedback import submit_feedback

_EXPECTED_REDIRECT_STATUS = 303


def _make_request() -> None:
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    return request


async def test_submit_feedback_creates_feedback() -> None:
    """Verify submit feedback creates feedback."""
    request = _make_request()

    with patch(
        "agent_stack.routes.feedback.feedback_svc.submit_feedback",
        new_callable=AsyncMock,
    ) as mock_submit:
        fb = MagicMock()
        fb.edition_id = "ed-1"
        fb.section = "intro"
        fb.comment = "Needs work"
        fb.resolved = False
        mock_submit.return_value = fb

        response = await submit_feedback(
            request, edition_id="ed-1", section="intro", comment="Needs work"
        )

        mock_submit.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS
