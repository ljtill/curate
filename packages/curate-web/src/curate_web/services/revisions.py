"""Revision business logic — list, diff, and revert content snapshots."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from curate_common.models.revision import Revision, RevisionSource

if TYPE_CHECKING:
    from curate_common.database.repositories.editions import EditionRepository
    from curate_common.database.repositories.revisions import RevisionRepository

logger = logging.getLogger(__name__)

_CONTENT_SECTIONS = (
    "title",
    "subtitle",
    "editors_note",
    "signals",
    "deep_dive",
    "toolkit",
    "one_more_thing",
)


def _section_changed(old: object, new: object) -> bool:
    """Return True if a section value differs between two revisions."""
    return old != new


def compute_diffs(revisions: list[Revision]) -> list[dict[str, Any]]:
    """Compare adjacent revisions and produce a section-by-section diff list.

    Returns one diff entry per revision (the first has no previous, so its
    diff is empty).  Each entry maps section names to a status string:
    ``"added"``, ``"removed"``, ``"changed"``, or ``"unchanged"``.
    """
    diffs: list[dict[str, Any]] = []
    for i, rev in enumerate(revisions):
        if i == 0:
            section_diffs: dict[str, str] = {}
            for section in _CONTENT_SECTIONS:
                if rev.content.get(section):
                    section_diffs[section] = "added"
            diffs.append({"revision_id": rev.id, "sections": section_diffs})
            continue

        prev = revisions[i - 1]
        section_diffs = {}
        for section in _CONTENT_SECTIONS:
            old_val = prev.content.get(section)
            new_val = rev.content.get(section)
            if old_val is None and new_val is not None:
                section_diffs[section] = "added"
            elif old_val is not None and new_val is None:
                section_diffs[section] = "removed"
            elif _section_changed(old_val, new_val):
                section_diffs[section] = "changed"
            else:
                section_diffs[section] = "unchanged"
        diffs.append({"revision_id": rev.id, "sections": section_diffs})
    return diffs


async def list_revisions(
    edition_id: str,
    revisions_repo: RevisionRepository,
) -> list[Revision]:
    """Return all revisions for an edition in chronological order."""
    return await revisions_repo.list_by_edition(edition_id)


async def revert_to_revision(
    revision_id: str,
    edition_id: str,
    editions_repo: EditionRepository,
    revisions_repo: RevisionRepository,
) -> Revision | None:
    """Revert the edition content to a previous revision (Git-style).

    Creates a new revision entry with ``source=REVERT`` preserving full
    history.  Returns the new revision, or ``None`` if the target revision
    or edition is not found.
    """
    target = await revisions_repo.get(revision_id, edition_id)
    if target is None:
        logger.warning(
            "revert_to_revision: revision %s not found for edition %s",
            revision_id,
            edition_id,
        )
        return None

    edition = await editions_repo.get(edition_id, edition_id)
    if edition is None:
        logger.warning("revert_to_revision: edition %s not found", edition_id)
        return None

    edition.content = copy.deepcopy(target.content)
    await editions_repo.update(edition, edition_id)

    seq = await revisions_repo.next_sequence(edition_id)
    revert_rev = Revision(
        edition_id=edition_id,
        sequence=seq,
        source=RevisionSource.REVERT,
        trigger_id=revision_id,
        content=copy.deepcopy(target.content),
        summary=f"Reverted to revision #{target.sequence}",
    )
    await revisions_repo.create(revert_rev)
    logger.info(
        "Edition reverted — edition=%s to_revision=%s new_seq=%d",
        edition_id,
        revision_id,
        seq,
    )
    return revert_rev
