"""Agent registry — introspects agent instances for metadata used by the Agents page."""

from __future__ import annotations

from typing import Any

from agent_stack.agents.draft import DraftAgent
from agent_stack.agents.edit import EditAgent
from agent_stack.agents.fetch import FetchAgent
from agent_stack.agents.publish import PublishAgent
from agent_stack.agents.review import ReviewAgent
from agent_stack.pipeline.orchestrator import PipelineOrchestrator


def _extract_tools(agent_obj) -> list[dict[str, str]]:
    """Extract tool names and descriptions from an Agent Framework agent."""
    inner = getattr(agent_obj, "_agent", None)
    if inner is None:
        return []
    tools = getattr(inner, "_tools", None) or getattr(inner, "tools", None) or []
    result = []
    for t in tools:
        if callable(t):
            name = getattr(t, "__name__", None) or getattr(t, "name", str(t))
            doc = getattr(t, "__doc__", None) or ""
            result.append({"name": name, "description": doc.strip().split("\n")[0] if doc else ""})
        elif hasattr(t, "name"):
            result.append({"name": t.name, "description": getattr(t, "description", "") or ""})
        else:
            result.append({"name": str(t), "description": ""})
    return result


def _extract_options(agent_obj) -> dict[str, Any]:
    """Extract default ChatOptions from an agent."""
    inner = getattr(agent_obj, "_agent", None)
    if inner is None:
        return {}
    opts = getattr(inner, "_default_options", None) or getattr(inner, "default_options", None)
    if opts is None:
        return {}
    result: dict[str, Any] = {}
    for attr in ("temperature", "max_tokens", "top_p", "response_format"):
        val = getattr(opts, attr, None)
        if val is not None:
            result[attr] = val
    return result


def _extract_middleware(agent_obj) -> list[str]:
    """Extract middleware class names from an agent."""
    inner = getattr(agent_obj, "_agent", None)
    if inner is None:
        return []
    mw = getattr(inner, "_middleware", None) or getattr(inner, "middleware", None) or []
    return [type(m).__name__ for m in mw]


def _extract_instructions(agent_obj, max_length: int = 200) -> dict[str, str]:
    """Extract system instructions (truncated preview + full text)."""
    inner = getattr(agent_obj, "_agent", None)
    if inner is None:
        return {"preview": "", "full": ""}
    instructions = getattr(inner, "_instructions", None) or getattr(inner, "instructions", None) or ""
    preview = instructions[:max_length] + ("…" if len(instructions) > max_length else "")
    return {"preview": preview, "full": instructions}


_AGENT_DESCRIPTIONS: dict[str, str] = {
    "fetch": "Retrieves and parses submitted link content from URLs.",
    "review": "Evaluates relevance, extracts key insights, and categorizes content.",
    "draft": "Composes or revises newsletter content from reviewed material.",
    "edit": "Refines tone, structure, and coherence; processes editor feedback.",
    "publish": "Renders final HTML against the newsletter template and deploys static pages.",
}

_AGENT_MAP: dict[str, type] = {
    "fetch": FetchAgent,
    "review": ReviewAgent,
    "draft": DraftAgent,
    "edit": EditAgent,
    "publish": PublishAgent,
}


def get_agent_metadata(orchestrator: PipelineOrchestrator) -> list[dict[str, Any]]:
    """Return metadata for all agents registered on the orchestrator.

    Each entry contains: name, description, tools, options, middleware, instructions.
    """
    agents: list[tuple[str, Any]] = [
        ("fetch", getattr(orchestrator, "_fetch", None)),
        ("review", getattr(orchestrator, "_review", None)),
        ("draft", getattr(orchestrator, "_draft", None)),
        ("edit", getattr(orchestrator, "_edit", None)),
        ("publish", getattr(orchestrator, "_publish", None)),
    ]

    result = []
    for name, agent_obj in agents:
        if agent_obj is None:
            continue
        result.append(
            {
                "name": name,
                "description": _AGENT_DESCRIPTIONS.get(name, ""),
                "tools": _extract_tools(agent_obj),
                "options": _extract_options(agent_obj),
                "middleware": _extract_middleware(agent_obj),
                "instructions": _extract_instructions(agent_obj),
            }
        )
    return result
