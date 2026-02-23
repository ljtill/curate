"""Tests for revision service — diff computation and revert logic."""

import copy
from unittest.mock import AsyncMock

import pytest

from curate_common.models.edition import Edition
from curate_common.models.revision import Revision, RevisionSource
from curate_web.services.revisions import compute_diffs, revert_to_revision

_EXPECTED_DIFF_COUNT = 2
_EXPECTED_REVERT_SEQUENCE = 3


class TestComputeDiffs:
    """Test the compute_diffs function."""

    def test_empty_revisions(self) -> None:
        """Verify empty list produces empty diffs."""
        assert compute_diffs([]) == []

    def test_single_revision_shows_added(self) -> None:
        """Verify first revision marks populated sections as added."""
        rev = Revision(
            id="r1",
            edition_id="ed-1",
            sequence=1,
            source=RevisionSource.DRAFT,
            content={"title": "Issue #1", "editors_note": "Hello"},
        )
        diffs = compute_diffs([rev])

        assert len(diffs) == 1
        assert diffs[0]["revision_id"] == "r1"
        assert diffs[0]["sections"]["title"] == "added"
        assert diffs[0]["sections"]["editors_note"] == "added"

    def test_two_revisions_detects_changes(self) -> None:
        """Verify diff between two revisions detects changes correctly."""
        r1 = Revision(
            id="r1",
            edition_id="ed-1",
            sequence=1,
            source=RevisionSource.DRAFT,
            content={"title": "V1", "editors_note": "Note"},
        )
        r2 = Revision(
            id="r2",
            edition_id="ed-1",
            sequence=2,
            source=RevisionSource.EDIT,
            content={
                "title": "V1",
                "editors_note": "Updated note",
                "signals": [{"headline": "New"}],
            },
        )
        diffs = compute_diffs([r1, r2])

        assert len(diffs) == _EXPECTED_DIFF_COUNT
        sections = diffs[1]["sections"]
        assert sections["title"] == "unchanged"
        assert sections["editors_note"] == "changed"
        assert sections["signals"] == "added"

    def test_removed_section(self) -> None:
        """Verify removed section is detected."""
        r1 = Revision(
            id="r1",
            edition_id="ed-1",
            sequence=1,
            source=RevisionSource.DRAFT,
            content={"title": "V1", "one_more_thing": "Bye"},
        )
        r2 = Revision(
            id="r2",
            edition_id="ed-1",
            sequence=2,
            source=RevisionSource.EDIT,
            content={"title": "V1"},
        )
        diffs = compute_diffs([r1, r2])

        assert diffs[1]["sections"]["one_more_thing"] == "removed"
        assert diffs[1]["sections"]["title"] == "unchanged"


class TestRevertToRevision:
    """Test the revert_to_revision function."""

    @pytest.fixture
    def mock_repos(self) -> tuple[AsyncMock, AsyncMock]:
        """Create mock repos."""
        return AsyncMock(), AsyncMock()

    async def test_revert_creates_new_revision(
        self, mock_repos: tuple[AsyncMock, AsyncMock]
    ) -> None:
        """Verify reverting creates a new revision with REVERT source."""
        editions_repo, revisions_repo = mock_repos
        old_content = {"title": "Old version", "editors_note": "Original"}
        target = Revision(
            id="r1",
            edition_id="ed-1",
            sequence=1,
            source=RevisionSource.DRAFT,
            content=copy.deepcopy(old_content),
        )
        edition = Edition(id="ed-1", content={"title": "Current"})
        revisions_repo.get.return_value = target
        revisions_repo.next_sequence.return_value = 3
        editions_repo.get.return_value = edition

        result = await revert_to_revision("r1", "ed-1", editions_repo, revisions_repo)

        assert result is not None
        assert result.source == RevisionSource.REVERT
        assert result.trigger_id == "r1"
        assert result.content == old_content
        assert result.sequence == _EXPECTED_REVERT_SEQUENCE
        editions_repo.update.assert_called_once()
        revisions_repo.create.assert_called_once()
        assert edition.content == old_content

    async def test_revert_returns_none_for_missing_revision(
        self, mock_repos: tuple[AsyncMock, AsyncMock]
    ) -> None:
        """Verify revert returns None when target revision not found."""
        editions_repo, revisions_repo = mock_repos
        revisions_repo.get.return_value = None

        result = await revert_to_revision(
            "missing", "ed-1", editions_repo, revisions_repo
        )

        assert result is None
        editions_repo.update.assert_not_called()

    async def test_revert_returns_none_for_missing_edition(
        self, mock_repos: tuple[AsyncMock, AsyncMock]
    ) -> None:
        """Verify revert returns None when edition not found."""
        editions_repo, revisions_repo = mock_repos
        revisions_repo.get.return_value = Revision(
            edition_id="ed-1", sequence=1, source=RevisionSource.DRAFT
        )
        editions_repo.get.return_value = None

        result = await revert_to_revision("r1", "ed-1", editions_repo, revisions_repo)

        assert result is None
        editions_repo.update.assert_not_called()
