# Copilot Instructions

The full project specification lives in `docs/SPECIFICATION.md` — always consult it for architecture, data model, component design, and tech stack details. For visual diagrams, see `docs/ARCHITECTURE.md`. These instructions cover **operational guidance** that is not in the spec.

## Build, Test & Lint

```bash
# Install dependencies (prerelease flag required for agent-framework-core)
uv sync --all-groups --prerelease=allow

# Run all tests
uv run pytest tests/ -v

# Run a single test file or test function
uv run pytest tests/agents/test_fetch.py -v
uv run pytest tests/agents/test_fetch.py::test_fetch_agent_returns_content -v

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type checking
uv run ty check src/

# Run the app locally (requires docker compose up -d first)
uv run uvicorn agent_stack.app:create_app --factory --reload --reload-dir src
```

Always run `ruff check`, `ruff format --check`, `ty check`, and `pytest` before committing. All four must pass cleanly.

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` and support markers `@pytest.mark.unit` and `@pytest.mark.integration`. Coverage must stay at or above 80% (`fail_under = 80` in `pyproject.toml`).

## Architecture

This is an event-driven editorial pipeline for a newsletter. The system has three surfaces: a FastAPI + HTMX dashboard (private), a multi-agent LLM pipeline, and a statically generated public newsletter site.

**Event flow**: Editor submits link → Cosmos DB → change feed processor → pipeline orchestrator → sub-agents (Fetch → Review → Draft) → Cosmos DB updates → SSE to dashboard. Feedback and publish follow similar event-driven paths. No external message broker — Cosmos DB's change feed is the sole event source.

**Agent architecture**: Five specialized agents (Fetch, Review, Draft, Edit, Publish) are coordinated by a `PipelineOrchestrator` agent. Each agent class wraps a Microsoft Agent Framework `Agent` instance, exposes `@tool`-decorated methods as LLM-callable functions, and is registered on the orchestrator via `.as_tool()`. System instructions are loaded from `prompts/<agent>.md` via `load_prompt()`. Middleware (e.g., `TokenTrackingMiddleware`) stacks on each agent's inner `Agent` instance.

**Two-loop execution**: The orchestrator runs an outer LLM loop deciding which agent to invoke next. Each sub-agent runs its own inner LLM loop, iteratively calling tools until the task is done. The orchestrator treats each sub-agent as a tool call.

**App wiring**: `app.py` uses a lifespan context manager to initialize Cosmos client → repositories → agents → orchestrator → change feed processor, stashing everything in `app.state`. Routes access dependencies via `request.app.state`.

**LLM provider**: Controlled by `FOUNDRY_PROVIDER` env var — `cloud` uses Microsoft Foundry, `local` uses Foundry Local for on-device inference (no Azure credentials needed). See `config.py` `FoundryConfig` for all related settings.

**Local emulators**: `docker compose up -d` starts the Cosmos DB emulator (ports 8081/1234) and Azurite storage emulator (ports 10000–10002).

## Key Conventions

- **Package management**: Use `uv` for everything — `uv run`, `uv add`, `uv sync`. The `agent-framework-core` package requires `--prerelease=allow`.
- **Database layer**: `BaseRepository[T]` provides generic async CRUD with automatic soft-delete filtering (`deleted_at` timestamp) and slow-operation warnings. Each entity (Link, Edition, Feedback, AgentRun) has its own repository subclass declaring `container_name` and `model_class`. All models extend `DocumentBase` (Pydantic) which generates `id`, `created_at`, `updated_at`, and `deleted_at` fields.
- **Agent structure**: Each agent is a wrapper class (e.g., `FetchAgent`) with an `agent` property exposing the inner framework `Agent`. Constructor takes a `BaseChatClient` and relevant repositories. Tools are instance methods decorated with `@tool` from `agent_framework`.
- **Agent prompts**: Stored as Markdown in `prompts/` (one per agent stage), loaded at runtime via `load_prompt("agent_name")`. The edition `content` dict follows a structured schema — see `prompts/draft.md` for the full specification.
- **Config**: Frozen dataclasses in `config.py`, composed into a `Settings` aggregate. Values come from environment variables (`.env` locally, Azure App Configuration in production). Use `_env()` helper for defaults.
- **Frontend**: Jinja2 templates + HTMX for the dashboard. Partials in `templates/partials/` return HTML fragments for in-place updates. SSE via `sse-starlette` for real-time events.
- **Test patterns**: `AsyncMock` fixtures for repositories, callable factory fixtures (`make_link()`, `make_edition()`, etc.) with sensible defaults in `tests/conftest.py`. Patch agent framework imports at the module level (e.g., `patch("agent_stack.agents.fetch.Agent")`). Tool return values are JSON strings — use `json.loads()` in assertions.
- **Ruff config**: `select = ["ALL"]` — all rules enabled with minimal exceptions. Tests are exempted from `S101` (assert). See `pyproject.toml` for details.
- **Bicep**: Use the latest available API versions for all Azure resource definitions. Infrastructure modules live in `infra/`.
- **Source control**: Imperative mood commit subjects (e.g., "Add …", "Update …"). Always review `README.md` at the end of major changes.
- **Dependencies**: Only add well-known, widely-adopted packages. Use the latest stable version from PyPI.
