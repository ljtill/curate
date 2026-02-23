# Curate

An event-driven, agent-powered editorial pipeline that transforms curated links into polished newsletter editions — entirely through LLM-driven agents. The pipeline is a general-purpose editorial automation engine that can be adapted for any newsletter or content curation workflow.

The system orchestrates five specialized agents — **Fetch**, **Review**, **Draft**, **Edit**, and **Publish** — coordinated by a pipeline orchestrator. An editor submits links through a private dashboard; the Cosmos DB change feed triggers the agent pipeline, which fetches and parses content, evaluates relevance, composes structured newsletter sections, refines tone and coherence, and renders the final edition as a static site. The dashboard provides real-time progress via SSE and supports per-section editorial feedback that agents incorporate in subsequent iterations.

Built on [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/), [FastAPI](https://fastapi.tiangolo.com/), [HTMX](https://htmx.org/), and [Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/). See [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md) for the full project specification — architecture, data model, component design, and tech stack. For visual architecture diagrams, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). For future ideas, see [`docs/ROADMAP.md`](docs/ROADMAP.md).

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
