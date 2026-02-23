"""Tests for feedback route handler."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_web.routes.feedback import submit_feedback
from tests.web.routes.runtime_helpers import make_runtime

_EXPECTED_REDIRECT_STATUS = 303


def _make_request() -> None:
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.runtime = make_runtime(cosmos=request.app.state.cosmos)
    return request


async def test_submit_feedback_creates_feedback() -> None:
    """Verify submit feedback creates feedback."""
    request = _make_request()

    with patch(
        "curate_web.routes.feedback.feedback_svc.submit_feedback",
        new_callable=AsyncMock,
    ) as mock_submit:
        fb = MagicMock()
        fb.edition_id = "ed-1"
        fb.section = "intro"
        fb.comment = "Needs work"
        fb.resolved = False
        fb.learn_from_feedback = True
        mock_submit.return_value = fb

        response = await submit_feedback(
            request, edition_id="ed-1", section="intro", comment="Needs work"
        )

        mock_submit.assert_called_once()
        call_args = mock_submit.call_args
        assert call_args[0][0] == "ed-1"
        assert call_args[0][1] == "intro"
        assert call_args[0][2] == "Needs work"
        assert call_args.kwargs["learn_from_feedback"] is False
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_submit_feedback_with_learn_enabled() -> None:
    """Verify submit feedback passes learn_from_feedback when checked."""
    request = _make_request()

    with patch(
        "curate_web.routes.feedback.feedback_svc.submit_feedback",
        new_callable=AsyncMock,
    ) as mock_submit:
        fb = MagicMock()
        mock_submit.return_value = fb

        response = await submit_feedback(
            request,
            edition_id="ed-1",
            section="intro",
            comment="Needs work",
            learn_from_feedback="true",
        )

        mock_submit.assert_called_once()
        call_kwargs = mock_submit.call_args
        assert call_kwargs.kwargs["learn_from_feedback"] is True
        assert response.status_code == _EXPECTED_REDIRECT_STATUS
