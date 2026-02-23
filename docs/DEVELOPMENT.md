# Local Development

This guide covers setting up the application for local development, including fully local (no Azure subscription) and cloud-connected options.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) (for cloud Foundry authentication)
- Docker
- [Microsoft Foundry Local](https://github.com/microsoft/foundry-local) (optional — for fully local development without Azure)

## Setup

```bash
# Install dependencies
uv sync --all-groups --prerelease=allow

# Start the emulators (Cosmos DB, Azurite, Service Bus)
cp .env.emulators.example .env.emulators
# Edit .env.emulators — set MSSQL_SA_PASSWORD for the Service Bus emulator's SQL Edge backend
docker compose up -d

# Configure environment
cp .env.example .env
# Edit .env with your credentials (see below for local vs cloud options)

# Run the web dashboard (with hot reload)
uv run uvicorn curate_web.app:create_app --factory --reload --reload-dir packages

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

The Service Bus emulator requires an Azure SQL Edge container as its backend. Both are configured in `docker-compose.yml` and use credentials from `.env.emulators`. The emulator is pre-configured with a `pipeline-events` topic and `web-consumer` subscription via `servicebus-config.json`.

## Fully Local Development (Foundry Local)

To run entirely locally without an Azure subscription, install [Foundry Local](https://github.com/microsoft/foundry-local) and set `FOUNDRY_PROVIDER=local` in your `.env`:

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
uv run uvicorn curate_web.app:create_app --factory --reload --reload-dir packages
```
