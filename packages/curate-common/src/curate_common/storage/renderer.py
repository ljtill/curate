"""Static site renderer.

Generates HTML from edition content using newsletter templates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from curate_common.database.repositories.editions import EditionRepository
    from curate_common.models.edition import Edition
    from curate_common.storage.blob import BlobStorageClient

logger = logging.getLogger(__name__)


def _find_templates_dir() -> Path:
    """Locate the newsletter templates directory from the workspace root."""
    # Walk up from this file until we find the templates/ directory
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "templates" / "newsletter"
        if candidate.is_dir():
            return candidate
        current = current.parent
    # Fallback: assume CWD-relative
    return Path.cwd() / "templates" / "newsletter"


NEWSLETTER_TEMPLATES = _find_templates_dir()


class StaticSiteRenderer:
    """Render editions as static HTML and upload to Microsoft Azure Storage."""

    def __init__(
        self, editions_repo: EditionRepository, storage: BlobStorageClient
    ) -> None:
        """Initialize the renderer with edition repository and storage client."""
        self.editions_repo = editions_repo
        self.storage = storage
        self._env = Environment(
            loader=FileSystemLoader(str(NEWSLETTER_TEMPLATES)), autoescape=True
        )

    async def render_edition(
        self,
        edition: Edition,
        prev_edition: Edition | None = None,
        next_edition: Edition | None = None,
    ) -> str:
        """Render a single edition to HTML."""
        template = self._env.get_template("edition.html")
        return template.render(
            edition=edition,
            prev_edition=prev_edition,
            next_edition=next_edition,
        )

    async def render_index(self, editions: list[Edition]) -> str:
        """Render the index/archive page listing all published editions."""
        template = self._env.get_template("index.html")
        return template.render(editions=editions)

    async def publish_edition(self, edition_id: str) -> None:
        """Render and upload an edition and update the index page."""
        edition = await self.editions_repo.get(edition_id, edition_id)
        if not edition:
            logger.error("Edition %s not found", edition_id)
            return

        published = await self.editions_repo.list_published()
        edition_idx = next(
            (i for i, e in enumerate(published) if e.id == edition_id), None
        )

        prev_edition = (
            published[edition_idx - 1] if edition_idx and edition_idx > 0 else None
        )
        next_edition = (
            published[edition_idx + 1]
            if edition_idx is not None and edition_idx < len(published) - 1
            else None
        )

        edition_html = await self.render_edition(edition, prev_edition, next_edition)
        await self.storage.upload_html(f"editions/{edition_id}.html", edition_html)

        if prev_edition:
            prev_prev = (
                published[edition_idx - 2] if edition_idx and edition_idx > 1 else None
            )
            prev_html = await self.render_edition(prev_edition, prev_prev, edition)
            await self.storage.upload_html(
                f"editions/{prev_edition.id}.html", prev_html
            )

        if next_edition:
            next_next = (
                published[edition_idx + 2]
                if edition_idx is not None and edition_idx < len(published) - 2
                else None
            )
            next_html = await self.render_edition(next_edition, edition, next_next)
            await self.storage.upload_html(
                f"editions/{next_edition.id}.html", next_html
            )

        index_html = await self.render_index(published)
        await self.storage.upload_html("index.html", index_html)

        logger.info("Published edition %s to static site", edition_id)
