# The Agent Stack

An event-driven, agent-powered editorial pipeline for a newsletter about Agentic Engineering.

## Architecture

The system comprises four components:

1. **Link Ingestion** — submit URLs via the editorial dashboard; stored in Cosmos DB, triggering the agent pipeline via change feed
2. **Agent Pipeline** — five-stage pipeline (Fetch → Review → Draft → Edit → Publish) powered by the [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
3. **Editorial Dashboard** — FastAPI + Jinja2 + HTMX admin UI with Microsoft Entra ID authentication
4. **Public Newsletter Site** — agent-generated static pages served via Azure Static Web Apps

## Tech Stack

- **Language**: Python 3.13 (managed with [uv](https://docs.astral.sh/uv/))
- **Agent Orchestration**: [Microsoft Agent Framework](https://pypi.org/project/agent-framework/) `1.0.0rc1`
- **LLM Provider**: [Microsoft Foundry](https://foundry.microsoft.com/) via Azure OpenAI
- **Web Framework**: FastAPI + Jinja2 + HTMX
- **Database**: Azure Cosmos DB (NoSQL API) — change feed as event backbone
- **Infrastructure**: Bicep modules for Azure Container Apps, Cosmos DB, Storage, Static Web Apps

## Project Structure

```
src/agent_stack/
├── agents/          # Agent implementations (Fetch, Review, Draft, Edit, Publish)
├── auth/            # Microsoft Entra ID authentication (MSAL)
├── database/        # Cosmos DB client and repository layer
├── events/          # SSE event manager for real-time updates
├── models/          # Pydantic data models
├── pipeline/        # Orchestrator and change feed processor
├── routes/          # FastAPI route handlers
├── storage/         # Azure Blob Storage client and static site renderer
├── app.py           # FastAPI application factory
└── config.py        # Configuration from environment variables
prompts/             # Agent system prompts (Markdown)
templates/           # Jinja2 templates (dashboard + newsletter)
infra/               # Bicep infrastructure modules
tests/               # Unit and integration tests
```

## Local Development

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (for Cosmos DB emulator)

### Setup

```bash
# Clone and install dependencies
git clone <repo-url> && cd agent-stack
uv sync --all-groups --prerelease=allow

# Start the Cosmos DB emulator
docker compose up -d

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run the application
uv run python -m agent_stack.app
```

### Running Tests

```bash
uv run pytest tests/ -v
```

### Linting & Formatting

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

### Type Checking

```bash
uv run ty check src/
```

## Deployment

Infrastructure is managed with Bicep. Deploy with:

```bash
az deployment group create \
  --resource-group <rg-name> \
  --template-file infra/main.bicep \
  --parameters infra/params/prod.bicepparam
```

CI/CD is handled by GitHub Actions — see `.github/workflows/ci.yml` and `.github/workflows/cd.yml`.