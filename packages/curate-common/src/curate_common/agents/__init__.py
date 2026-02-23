"""Agent registry — static metadata for the Agents dashboard page."""

from __future__ import annotations

from typing import Any

_AGENT_METADATA: list[dict[str, Any]] = [
    {
        "name": "orchestrator",
        "description": (
            "Coordinates the editorial pipeline — routes links through fetch, "
            "review, and draft stages; handles editor feedback and gated "
            "publishing."
        ),
        "tools": [
            {
                "name": "fetch",
                "description": "Fetch and extract content from a submitted URL",
            },
            {
                "name": "review",
                "description": (
                    "Evaluate relevance, extract insights, categorize content"
                ),
            },
            {
                "name": "draft",
                "description": (
                    "Compose or revise newsletter content from reviewed material"
                ),
            },
            {
                "name": "edit",
                "description": "Refine edition content and address editor feedback",
            },
            {"name": "publish", "description": "Render HTML and upload to storage"},
            {
                "name": "get_link_status",
                "description": "Get the current status of a link",
            },
            {
                "name": "get_edition_status",
                "description": "Get the current status of an edition",
            },
            {
                "name": "record_stage_start",
                "description": "Record the start of a pipeline stage",
            },
            {
                "name": "record_stage_complete",
                "description": "Record the completion of a pipeline stage",
            },
        ],
        "middleware": ["TokenTrackingMiddleware", "ToolLoggingMiddleware"],
        "prompt_file": "orchestrator",
    },
    {
        "name": "fetch",
        "description": "Retrieves and parses submitted link content from URLs.",
        "tools": [
            {
                "name": "fetch_url",
                "description": "Fetch and extract content from a URL",
            },
        ],
        "middleware": ["TokenTrackingMiddleware"],
        "prompt_file": "fetch",
    },
    {
        "name": "review",
        "description": (
            "Evaluates relevance, extracts key insights, and categorizes content."
        ),
        "tools": [
            {"name": "save_review", "description": "Save the review result for a link"},
        ],
        "middleware": ["TokenTrackingMiddleware"],
        "prompt_file": "review",
    },
    {
        "name": "draft",
        "description": "Composes or revises newsletter content from reviewed material.",
        "tools": [
            {"name": "save_draft", "description": "Save the drafted edition content"},
        ],
        "middleware": ["TokenTrackingMiddleware"],
        "prompt_file": "draft",
    },
    {
        "name": "edit",
        "description": (
            "Refines tone, structure, and coherence; processes editor feedback."
        ),
        "tools": [
            {"name": "save_edit", "description": "Save the edited edition content"},
        ],
        "middleware": ["TokenTrackingMiddleware"],
        "prompt_file": "edit",
    },
    {
        "name": "publish",
        "description": (
            "Renders final HTML against the newsletter template and deploys "
            "static pages."
        ),
        "tools": [
            {
                "name": "render_and_upload",
                "description": "Render HTML and upload static files",
            },
        ],
        "middleware": ["TokenTrackingMiddleware"],
        "prompt_file": "publish",
    },
]


def get_agent_metadata() -> list[dict[str, Any]]:
    """Return static metadata for all agents in the pipeline.

    Each entry contains: name, description, tools, middleware, prompt_file.
    Instructions preview can be added by loading the prompt file.
    """
    import copy  # noqa: PLC0415

    return copy.deepcopy(_AGENT_METADATA)
