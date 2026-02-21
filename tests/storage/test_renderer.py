"""Tests for the static site renderer."""

from datetime import UTC, datetime

import pytest
from jinja2 import Environment, FileSystemLoader

from agent_stack.models.edition import Edition, EditionStatus
from agent_stack.storage.renderer import NEWSLETTER_TEMPLATES


def _sample_content() -> None:
    return {
        "title": "Test Edition Title",
        "subtitle": "A subtitle for the test edition.",
        "issue_number": 1,
        "editors_note": (
            "Welcome to the <strong>first issue</strong> of the newsletter."
        ),
        "signals": [
            {
                "headline": "Signal One Headline",
                "body": "Signal one body text.",
                "url": "https://example.com/signal-1",
                "domain": "example.com",
                "company": "ExampleCo",
                "company_tag": "tag-lab",
                "category": "Protocol",
                "category_tag": "tag-protocol",
            },
            {
                "headline": "Signal Two Headline",
                "body": "Signal two body text.",
                "url": "https://example.com/signal-2",
                "domain": "example.com",
                "company": "AnotherCo",
                "company_tag": "tag-platform",
                "category": "Infra",
                "category_tag": "tag-pattern",
            },
        ],
        "deep_dive": {
            "title": "Deep Dive Title",
            "paragraphs": ["First paragraph.", "Second paragraph."],
            "callout": {
                "label": "Key Insight",
                "content": "Important callout content.",
            },
        },
        "toolkit": [
            {
                "name": "Tool One (v1.0)",
                "description": "A great tool for testing.",
                "url": "https://example.com/tool-1",
                "domain": "example.com",
            },
        ],
        "one_more_thing": "A closing thought for the <strong>reader</strong>.",
    }


def test_newsletter_templates_dir_exists() -> None:
    """Verify newsletter templates dir exists."""
    assert NEWSLETTER_TEMPLATES.exists()
    assert (NEWSLETTER_TEMPLATES / "edition.html").exists()
    assert (NEWSLETTER_TEMPLATES / "index.html").exists()


@pytest.mark.asyncio
async def test_render_edition_produces_html() -> None:
    """Test that edition rendering produces valid HTML with the new design."""
    env = Environment(
        loader=FileSystemLoader(str(NEWSLETTER_TEMPLATES)), autoescape=True
    )
    template = env.get_template("edition.html")

    edition = Edition(
        status=EditionStatus.PUBLISHED,
        content=_sample_content(),
        published_at=datetime(2026, 2, 20, tzinfo=UTC),
    )

    html = template.render(edition=edition)
    assert "<!DOCTYPE html>" in html
    # Header
    assert "Test Edition Title" in html
    assert "Issue #1" in html
    assert "Feb 20, 2026" in html
    # Editor's note
    assert "first issue" in html
    # Signals
    assert "Signal One Headline" in html
    assert "Signal Two Headline" in html
    assert "ExampleCo" in html
    assert "tag-lab" in html
    assert "tag-protocol" in html
    # Deep dive
    assert "Deep Dive Title" in html
    assert "First paragraph." in html
    assert "Key Insight" in html
    # Toolkit
    assert "Tool One (v1.0)" in html
    # One more thing
    assert "closing thought" in html
    # Design elements
    assert "IBM Plex" in html
    assert "DM Serif Display" in html
    assert "--signal-green" in html


@pytest.mark.asyncio
async def test_render_index_produces_html() -> None:
    """Test that index rendering produces valid HTML with the archive design."""
    env = Environment(
        loader=FileSystemLoader(str(NEWSLETTER_TEMPLATES)), autoescape=True
    )
    template = env.get_template("index.html")

    editions = [
        Edition(
            id="ed-1",
            status=EditionStatus.PUBLISHED,
            content=_sample_content(),
            published_at=datetime(2026, 2, 20, tzinfo=UTC),
        ),
    ]

    html = template.render(editions=editions)
    assert "<!DOCTYPE html>" in html
    assert "Archive" in html
    assert "Test Edition Title" in html
    assert "The Agent Stack" in html
    assert "2026" in html
    assert "Latest" in html
    assert "2 signals" in html
    assert "1 tools" in html
