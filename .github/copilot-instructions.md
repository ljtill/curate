# Copilot Instructions

The full project specification lives in `docs/SPECIFICATION.md` — always consult it for architecture, data model, component design, and tech stack details. For visual diagrams, see `docs/ARCHITECTURE.md`. These instructions cover **operational guidance** that is not in the spec.

## Build, Test & Lint

```bash
# Install dependencies (prerelease flag required for agent-framework-core)
uv sync --all-groups --prerelease=allow

# Run all tests
uv run pytest tests/ -v

# Run a single test file or test function
uv run pytest tests/worker/agents/test_fetch.py -v
uv run pytest tests/worker/agents/test_fetch.py::test_fetch_agent_returns_content -v

# Lint and format
uv run ruff check packages/ tests/
uv run ruff format packages/ tests/

# Type checking
uv run ty check packages/

# Run the web dashboard locally (requires docker compose up -d first)
uv run uvicorn curate_web.app:create_app --factory --reload --reload-dir packages

# Run the worker locally (in a separate terminal)
uv run python -m curate_worker.app
```

Always run `ruff check`, `ruff format --check`, `ty check`, and `pytest` before committing. All four must pass cleanly.

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` and support markers `@pytest.mark.unit` and `@pytest.mark.integration`. Coverage must stay at or above 80% (`fail_under = 80` in `pyproject.toml`).

## Architecture

This is an event-driven editorial pipeline for a newsletter, split into three packages in a uv workspace monorepo:

- **`curate-common`** (`packages/curate-common/`) — shared library: config, models, database (Cosmos client + repositories), storage, logging, `EventPublisher` protocol, data-driven agent registry.
- **`curate-web`** (`packages/curate-web/`) — FastAPI + HTMX editorial dashboard: routes, services, auth (MSAL), SSE EventManager, Service Bus consumer.
- **`curate-worker`** (`packages/curate-worker/`) — agent pipeline: five agents (Fetch, Review, Draft, Edit, Publish), pipeline orchestrator, Cosmos DB change feed processor, Service Bus publisher.

**Process model**: Two independent processes — the web service (FastAPI) handles the dashboard and SSE, the worker runs the agent pipeline. Azure Service Bus bridges them for real-time event delivery (worker publishes pipeline events → Service Bus topic → web consumes from subscription → feeds SSE to browser).

**Event flow**: Editor submits link → Cosmos DB → change feed processor (worker) → pipeline orchestrator → sub-agents (Fetch → Review → Draft) → Cosmos DB updates → Service Bus → SSE to dashboard. Feedback and publish follow similar event-driven paths.

**Agent architecture**: Five specialized agents coordinated by a `PipelineOrchestrator` agent. Each agent class wraps a Microsoft Agent Framework `Agent` instance, exposes `@tool`-decorated methods as LLM-callable functions, and is registered on the orchestrator via `.as_tool()`. System instructions are loaded from `prompts/<agent>.md` via `load_prompt()`. Middleware (e.g., `TokenTrackingMiddleware`) stacks on each agent's inner `Agent` instance.

**Two-loop execution**: The orchestrator runs an outer LLM loop deciding which agent to invoke next. Each sub-agent runs its own inner LLM loop, iteratively calling tools until the task is done. The orchestrator treats each sub-agent as a tool call.

**Web app wiring**: `app.py` uses a lifespan context manager to initialize Cosmos client → repositories → storage, stashing everything in `app.state`. Routes access dependencies via `request.app.state`.

**Worker app wiring**: `app.py` initializes Cosmos client → LLM client → agents → orchestrator → change feed processor, then runs until terminated via signal.

**LLM provider**: Controlled by `FOUNDRY_PROVIDER` env var — `cloud` uses Microsoft Foundry, `local` uses Foundry Local for on-device inference (no Azure credentials needed). See `config.py` `FoundryConfig` for all related settings.

**Local emulators**: `docker compose up -d` starts the Cosmos DB emulator (ports 8081/1234), Azurite storage emulator (ports 10000–10002), and Azure Service Bus emulator (ports 5672/5300) with SQL Edge backend. Emulator credentials are loaded from `.env.emulators`.

## Key Conventions

- **Package management**: Use `uv` for everything — `uv run`, `uv add`, `uv sync`. The `agent-framework-core` package requires `--prerelease=allow`.
- **Workspace layout**: Three packages under `packages/`, each with its own `pyproject.toml` and `src/` layout. Both `web` and `worker` depend on `common`. Shared code (models, database, config, storage, logging) always goes in `common`.
- **Import paths**: Shared code uses `curate_common.*`, web-specific code uses `curate_web.*`, worker-specific code uses `curate_worker.*`. When patching in tests, use the consuming module's path (e.g., `patch("curate_worker.agents.fetch.Agent")`).
- **Database layer**: `BaseRepository[T]` provides generic async CRUD with automatic soft-delete filtering (`deleted_at` timestamp) and slow-operation warnings. Each entity (Link, Edition, Feedback, AgentRun) has its own repository subclass declaring `container_name` and `model_class`. All models extend `DocumentBase` (Pydantic) which generates `id`, `created_at`, `updated_at`, and `deleted_at` fields.
- **Agent structure**: Each agent is a wrapper class (e.g., `FetchAgent`) with an `agent` property exposing the inner framework `Agent`. Constructor takes a `BaseChatClient` and relevant repositories. Tools are instance methods decorated with `@tool` from `agent_framework`.
- **Agent prompts**: Stored as Markdown in `prompts/` (one per agent stage), loaded at runtime via `load_prompt("agent_name")`. The edition `content` dict follows a structured schema — see `prompts/draft.md` for the full specification.
- **Agent registry**: Data-driven static metadata in `curate_common.agents.registry` — no live introspection of agent instances. The web reads this for the Agents dashboard page.
- **Event bridge**: `EventPublisher` protocol in `common` defines the interface. Worker implements `ServiceBusPublisher`, web implements `ServiceBusConsumer` + local `EventManager` (SSE). The publisher degrades gracefully when `SERVICEBUS_CONNECTION_STRING` is not set.
- **Logging**: Shared `configure_logging()` in `curate_common.logging` — both services use it for consistent console + file output (`logs/web.log`, `logs/worker.log`).
- **Config**: Frozen dataclasses in `config.py` (common), composed into a `Settings` aggregate. Values come from environment variables (`.env` locally, Azure App Configuration in production). Use `_env()` helper for defaults.
- **Frontend**: Jinja2 templates + HTMX for the dashboard. Partials in `templates/partials/` return HTML fragments for in-place updates. SSE via `sse-starlette` for real-time events.
- **Test patterns**: `AsyncMock` fixtures for repositories, callable factory fixtures (`make_link()`, `make_edition()`, etc.) with sensible defaults in `tests/conftest.py`. Tests are organized into `tests/common/`, `tests/web/`, `tests/worker/`. Tool return values are JSON strings — use `json.loads()` in assertions.
- **Ruff config**: `select = ["ALL"]` — all rules enabled with minimal exceptions. Tests are exempted from `S101` (assert). See `pyproject.toml` for details.
- **Bicep**: Use the latest available API versions for all Azure resource definitions. Infrastructure modules live in `infra/` — separate modules for web and worker container apps, plus Service Bus.
- **Source control**: Imperative mood commit subjects (e.g., "Add …", "Update …"). Always review `README.md` at the end of major changes.
- **Dependencies**: Only add well-known, widely-adopted packages. Use the latest stable version from PyPI.
