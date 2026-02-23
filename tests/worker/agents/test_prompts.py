"""Tests for the prompt loader."""

from curate_worker.agents.prompts import PROMPTS_DIR, load_prompt

_MIN_PROMPT_LENGTH = 50


def test_prompts_dir_exists() -> None:
    """Verify prompts dir exists."""
    assert PROMPTS_DIR.exists()


def test_load_fetch_prompt() -> None:
    """Verify load fetch prompt."""
    prompt = load_prompt("fetch")
    assert "Fetch" in prompt
    assert len(prompt) > 0


def test_load_all_prompts() -> None:
    """Verify load all prompts."""
    stages = ["fetch", "review", "draft", "edit", "publish"]
    for stage in stages:
        prompt = load_prompt(stage)
        assert isinstance(prompt, str)
        assert len(prompt) > _MIN_PROMPT_LENGTH, f"Prompt for {stage} seems too short"


def test_prompt_files_exist() -> None:
    """Verify prompt files exist."""
    stages = ["fetch", "review", "draft", "edit", "publish"]
    for stage in stages:
        path = PROMPTS_DIR / f"{stage}.md"
        assert path.exists(), f"Missing prompt file: {path}"
