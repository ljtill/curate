"""Static site renderer — generates HTML from edition content using newsletter templates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from agent_stack.database.repositories.editions import EditionRepository
    from agent_stack.models.edition import Edition
    from agent_stack.storage.blob import BlobStorageClient

logger = logging.getLogger(__name__)

NEWSLETTER_TEMPLATES = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "newsletter"


class StaticSiteRenderer:
    """Renders newsletter editions as static HTML and uploads to Azure Storage."""

    def __init__(self, editions_repo: EditionRepository, storage: BlobStorageClient) -> None:
        """Initialize the renderer with edition repository and storage client."""
        self.editions_repo = editions_repo
        self.storage = storage
        self._env = Environment(loader=FileSystemLoader(str(NEWSLETTER_TEMPLATES)), autoescape=True)

    async def render_edition(self, edition: Edition) -> str:
        """Render a single edition to HTML."""
        template = self._env.get_template("edition.html")
        return template.render(edition=edition)

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

        # Render and upload the edition page
        edition_html = await self.render_edition(edition)
        await self.storage.upload_html(f"editions/{edition_id}.html", edition_html)

        # Render and upload the updated index page
        published = await self.editions_repo.list_published()
        index_html = await self.render_index(published)
        await self.storage.upload_html("index.html", index_html)

        logger.info("Published edition %s to static site", edition_id)
