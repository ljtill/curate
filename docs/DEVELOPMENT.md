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

# Start the Cosmos DB and Azurite emulators
docker compose up -d

# Configure environment
cp .env.example .env
# Edit .env with your credentials (see below for local vs cloud options)

# Run the application (with hot reload)
uv run uvicorn agent_stack.app:create_app --factory --reload --reload-dir src
```

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
uv run uvicorn agent_stack.app:create_app --factory --reload --reload-dir src
```
