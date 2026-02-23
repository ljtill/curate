"""Link business logic — submit, retry, delete with edition regeneration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from curate_common.models.edition import EditionStatus
from curate_common.models.link import Link, LinkStatus

if TYPE_CHECKING:
    from curate_common.database.repositories.editions import EditionRepository
    from curate_common.database.repositories.links import LinkRepository
    from curate_common.models.edition import Edition


async def submit_link(
    url: str,
    edition_id: str,
    links_repo: LinkRepository,
    editions_repo: EditionRepository,
) -> Link | None:
    """Create a link for an unpublished edition. Returns None if rejected."""
    edition = await editions_repo.get(edition_id, edition_id)
    if not edition or edition.status == EditionStatus.PUBLISHED:
        return None

    link = Link(url=url, edition_id=edition.id)
    await links_repo.create(link)
    return link


async def retry_link(
    link_id: str,
    edition_id: str,
    links_repo: LinkRepository,
) -> bool:
    """Reset a failed link to submitted. Returns True if reset succeeded."""
    link = await links_repo.get(link_id, edition_id)
    if not link or link.status != LinkStatus.FAILED:
        return False

    link.status = LinkStatus.SUBMITTED
    link.title = None
    link.content = None
    await links_repo.update(link, edition_id)
    return True


async def delete_link(
    link_id: str,
    edition_id: str,
    links_repo: LinkRepository,
    editions_repo: EditionRepository,
) -> Edition | None:
    """Soft-delete a link and regenerate edition if needed.

    Returns the edition if the operation proceeded, None if rejected.
    """
    edition = await editions_repo.get(edition_id, edition_id)
    if not edition or edition.status == EditionStatus.PUBLISHED:
        return None

    link = await links_repo.get(link_id, edition_id)
    if not link:
        return edition

    await links_repo.soft_delete(link, edition_id)

    if link_id in edition.link_ids:
        edition.link_ids.remove(link_id)
        edition.content = {}
        await editions_repo.update(edition, edition_id)

        remaining = await links_repo.get_by_status(edition_id, LinkStatus.DRAFTED)
        for remaining_link in remaining:
            remaining_link.status = LinkStatus.REVIEWED
            await links_repo.update(remaining_link, edition_id)

    return edition
