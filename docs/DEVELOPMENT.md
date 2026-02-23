# Local Development

This guide covers setting up the application for local development, including fully local (no Azure subscription) and cloud-connected options.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) (for cloud Foundry authentication)
- Docker
- [Microsoft Foundry Local](https://foundrylocal.ai/) (optional — for fully local development without Azure)

## Setup

```bash
# Install dependencies
uv sync --all-groups --prerelease=allow

# Start the emulators (Cosmos DB, Azurite, Service Bus)
docker compose up -d

# Configure environment
cp .env.example .env
# Edit .env — set MSSQL_SA_PASSWORD and optionally configure cloud credentials
# Service Bus entity names are centrally managed project configuration
# (pipeline-commands / pipeline-events with worker-consumer / web-consumer).

# Run the web dashboard (with hot reload)
uv run python -m curate_web.app

# Run the worker (in a separate terminal)
uv run python -m curate_worker.app
```

The web service runs the editorial dashboard (FastAPI + HTMX) and the worker runs the agent pipeline (change feed processor + orchestrator). Both connect to the same Cosmos DB and communicate via Azure Service Bus for real-time SSE updates.

When `APP_ENV=development`, dashboard authentication is bypassed automatically for local use, so Microsoft Entra credentials are optional during local iteration.

## Emulators

The project uses three local emulators via Docker Compose:

| Emulator | Image | Ports | Purpose |
|----------|-------|-------|---------|
| Cosmos DB | `mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-preview` | 8081, 1234 | NoSQL data store + change feed |
| Azurite | `mcr.microsoft.com/azure-storage/azurite` | 10000–10002 | Blob storage for static site |
| Service Bus | `mcr.microsoft.com/azure-messaging/servicebus-emulator` | 5672 | Event bridge between web and worker |

The Service Bus emulator requires an Azure SQL Edge container as its backend. Both are configured in `docker-compose.yml` and use `MSSQL_SA_PASSWORD` from `.env`. The emulator is pre-configured with `pipeline-commands` and `pipeline-events` topics plus the `worker-consumer` and `web-consumer` subscriptions via `servicebus-config.json`. These names are fixed project configuration, not user-overridable `.env` values.

### Service Bus routing in local dev

- The **web service** publishes `publish-request` commands to the `pipeline-commands` topic.
- The **worker service** consumes commands from `worker-consumer`.
- The **worker service** publishes pipeline progress events to the `pipeline-events` topic.
- The **web service** consumes pipeline events from `web-consumer` on `pipeline-events` and forwards them to SSE clients.

## Fully Local Development (Foundry Local)

To run entirely locally without an Azure subscription, install [Foundry Local](https://foundrylocal.ai/) and set `FOUNDRY_PROVIDER=local` in your `.env`:

```bash
# macOS
brew install microsoft/foundrylocal/foundrylocal

# Windows
winget install Microsoft.FoundryLocal
```

Then in your `.env`:
```
FOUNDRY_PROVIDER=local
FOUNDRY_LOCAL_MODEL=phi-4-mini
```

The application will automatically start the Foundry Local service, download the model on first run, and use on-device inference. No `az login` or Azure credentials required for the LLM pipeline. Foundry Memory is automatically disabled when using Foundry Local.

## Cloud Development (Microsoft Foundry)

For cloud-based inference, authenticate with Azure and set the Foundry project endpoint:

```bash
az login
```

Then in your `.env`:
```
FOUNDRY_PROVIDER=cloud
FOUNDRY_PROJECT_ENDPOINT=https://{resource-name}.services.ai.azure.com/api/projects/{project-name}
FOUNDRY_MODEL=your-model-deployment
```

## Diagnostics

For intermittent UI lock-up diagnostics in local development, run with verbose timing logs:

```bash
LOG_LEVEL=DEBUG APP_SLOW_REQUEST_MS=400 APP_SLOW_REPOSITORY_MS=150 \
uv run python -m curate_web.app
```

## Tests

```bash
uv run pytest tests/ -v
```

## Linting, Formatting & Type Checking

```bash
uv run ruff check packages/ tests/
uv run ruff format packages/ tests/
uv run ty check packages/
```

## Pipelines

GitHub Actions with five workflows. Check and Test run in parallel on push / PR to `main`; Build, Release, and Deploy chain sequentially via `workflow_run` triggers. All Azure-facing workflows authenticate using OIDC federated credentials.

| Workflow | File | Trigger | Responsibility |
|---|---|---|---|
| **Check** | `check.yml` | Push / PR to `main` | Lint, format check, type check |
| **Test** | `test.yml` | Push / PR to `main` | Unit tests |
| **Build** | `build.yml` | Check + Test success on `main` | Docker build, push to ACR, Bicep validation |
| **Release** | `release.yml` | Build success on `main` | Bicep infrastructure deployment |
| **Deploy** | `deploy.yml` | Release success on `main` | Container App update |

## Manual Deployment

```bash
az deployment group create \
  --resource-group <rg-name> \
  --template-file infra/main.bicep \
  --parameters infra/params/prod.bicepparam
```
