# Curate

An event-driven, agent-powered editorial pipeline that transforms curated links into polished newsletter editions — entirely through LLM-driven agents. The pipeline is a general-purpose editorial automation engine that can be adapted for any newsletter or content curation workflow.

The system orchestrates five specialized agents — **Fetch**, **Review**, **Draft**, **Edit**, and **Publish** — coordinated by a pipeline orchestrator. An editor submits links through a private dashboard; the Cosmos DB change feed triggers the agent pipeline, which fetches and parses content, evaluates relevance, composes structured newsletter sections, refines tone and coherence, and renders the final edition as a static site. The dashboard provides real-time progress via SSE and supports per-section editorial feedback that agents incorporate in subsequent iterations.

Built on [Microsoft Agent Framework](https://github.com/microsoft/agent-framework), FastAPI, HTMX, and Azure Cosmos DB. See [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md) for the full project specification — architecture, data model, component design, and tech stack. For visual architecture diagrams, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Agentic Loop

The system implements a nested two-loop architecture — an **outer orchestrator loop** that coordinates agents as tool calls, and an **inner agentic loop** where each agent iterates with the LLM until its task is complete.

```mermaid
flowchart LR
    Editor([Editor]) -->|"submit link /<br/>feedback"| CFP["Change Feed<br/>Processor"]
    CFP --> ORC["Orchestrator<br/>LLM"]
    ORC -->|"invoke agent<br/>as tool call"| AGENT["Agent LLM<br/>Fetch · Review · Draft<br/>Edit · Publish"]
    AGENT -->|"tool call"| TOOLS["Tools<br/>DB · HTTP · Render"]
    TOOLS -->|"result"| AGENT
    AGENT -->|"task complete"| ORC
    ORC -->|"pipeline<br/>complete"| DB[(Cosmos DB)]
    DB -.->|"change feed"| CFP

    classDef outer fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef inner fill:#7c3aed,stroke:#6d28d9,color:#fff
    classDef infra fill:#d97706,stroke:#b45309,color:#fff
    classDef human fill:#059669,stroke:#047857,color:#fff

    class ORC outer
    class AGENT,TOOLS inner
    class CFP,DB infra
    class Editor human
```

> **Outer loop** — the orchestrator's LLM decides which agent to invoke next (Fetch → Review → Draft, or Edit/Publish), treating each sub-agent as a callable tool. After each agent returns, the orchestrator re-evaluates and either continues to the next stage or completes the pipeline.
>
> **Inner loop** — each sub-agent runs its own LLM session, iteratively calling tools (database reads/writes, HTTP fetches, HTML rendering) until the task is done. The LLM autonomously decides which tools to call and when to stop.
>
> **Human-in-the-loop** — editor feedback creates a new Cosmos DB change feed event, re-entering the outer loop through the Edit agent for content refinement.

## Project Structure

```
packages/
├── curate-common/      # Shared library (config, models, database, storage)
│   └── src/curate_common/
├── curate-web/         # FastAPI editorial dashboard
│   └── src/curate_web/
│       ├── auth/            # Microsoft Entra ID authentication (MSAL)
│       ├── events/          # SSE event manager + Service Bus consumer
│       ├── routes/          # FastAPI route handlers
│       ├── services/        # Domain services, health checks, status
│       ├── app.py           # FastAPI application factory
│       └── startup.py       # Web initialization helpers
└── curate-worker/      # Agent pipeline worker
    └── src/curate_worker/
        ├── agents/          # Agent implementations, LLM client, middleware, prompts
        ├── pipeline/        # Orchestrator, change feed processor, run manager
        ├── events.py        # Service Bus event publisher
        ├── app.py           # Worker entry point
        └── startup.py       # Worker initialization helpers
prompts/                     # Agent system prompts (Markdown)
templates/
├── *.html                   # Dashboard views (Jinja2 + HTMX)
├── newsletter/              # Public newsletter templates
└── partials/                # HTMX partial fragments
infra/                       # Bicep infrastructure modules
tests/
├── common/                  # Tests for curate_common
├── web/                     # Tests for curate_web
└── worker/                  # Tests for curate_worker
```

## Local Development

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for detailed setup instructions, including fully local development with [Foundry Local](https://github.com/microsoft/foundry-local) (no Azure subscription required) and cloud-connected options.

### Quick Start

```bash
uv sync --all-groups --prerelease=allow
docker compose up -d
cp .env.example .env
# Edit .env — set FOUNDRY_PROVIDER=local for fully local, or configure cloud credentials
# Run the web dashboard
uv run uvicorn curate_web.app:create_app --factory --reload --reload-dir packages
# Run the worker (in a separate terminal)
uv run python -m curate_worker.app
```

### Tests

```bash
uv run pytest tests/ -v
```

### Linting, Formatting & Type Checking

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

### Manual Deployment

```bash
az deployment group create \
  --resource-group <rg-name> \
  --template-file infra/main.bicep \
  --parameters infra/params/prod.bicepparam
```
