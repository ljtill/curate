# The Agent Stack

An event-driven, agent-powered editorial pipeline for "The Agent Stack", a newsletter about Agentic Engineering. See [`docs/SPEC.md`](docs/SPEC.md) for the full project specification — architecture, data model, component design, and tech stack. For visual architecture diagrams, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Project Structure

```
src/agent_stack/
├── agents/          # Agent implementations, LLM client, middleware, prompt loader, registry
├── auth/            # Microsoft Entra ID authentication (MSAL)
├── database/
│   ├── client.py    # Cosmos DB client
│   └── repositories/  # Per-entity repository layer
├── events/          # SSE event manager for real-time updates
├── models/          # Pydantic data models
├── pipeline/        # Orchestrator and change feed processor
├── routes/          # FastAPI route handlers
├── services/        # Health checks and service-layer utilities
├── storage/         # Azure Blob Storage client and static site renderer
├── app.py           # FastAPI application factory
└── config.py        # Configuration from environment variables
prompts/             # Agent system prompts (Markdown)
templates/
├── *.html           # Dashboard views (Jinja2 + HTMX)
├── newsletter/      # Public newsletter templates (index + edition)
└── partials/        # HTMX partial fragments (agent activity, edition title)
infra/               # Bicep infrastructure modules
tests/               # Unit and integration tests
```

## Local Development

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker

### Setup

```bash
# Install dependencies
uv sync --all-groups --prerelease=allow

# Start the Cosmos DB and Azurite emulators
docker compose up -d

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run the application (with hot reload)
uv run uvicorn agent_stack.app:create_app --factory --reload --reload-dir src
```

### Tests

```bash
uv run pytest tests/ -v
```

### Linting, Formatting & Type Checking

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run ty check src/
```

## Pipelines

GitHub Actions with five workflows chained via `workflow_run` triggers. All Azure-facing workflows authenticate using OIDC federated credentials.

| Workflow | File | Trigger | Responsibility |
|---|---|---|---|
| **Check** | `check.yml` | Push / PR to `main` | Lint, format check, type check |
| **Test** | `test.yml` | Push / PR to `main` | Unit tests |
| **Build** | `build.yml` | Check + Test success on `main` | Docker build, push to ACR, Bicep validation |
| **Release** | `release.yml` | Build success on `main` | Bicep infrastructure deployment |
| **Deploy** | `deploy.yml` | Release success on `main` | Container App update |

### Manual Deployment

```bash
az deployment group create \
  --resource-group <rg-name> \
  --template-file infra/main.bicep \
  --parameters infra/params/prod.bicepparam
```