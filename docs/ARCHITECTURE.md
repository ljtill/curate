# Architecture

This document provides a visual overview of The Agent Stack — an event-driven, agent-powered editorial pipeline for a newsletter about Agentic Engineering. Each section includes a diagram and a brief explanation of the components involved.

## System Overview

The platform has three main surfaces: an editorial dashboard where editors submit links and review content, an agent pipeline that autonomously processes links into newsletter editions, and a static site where published editions are served to readers. Cosmos DB sits at the centre as both the data store and the event backbone — its change feed is what drives the entire pipeline without any external message broker.

```mermaid
graph TB
    Editor([Editor])
    Reader([Reader])

    subgraph Azure["Azure"]
        Dashboard["Editorial Dashboard<br/>(FastAPI + HTMX)"]
        CosmosDB[("Cosmos DB<br/>(NoSQL API)")]
        ChangeFeed["Change Feed<br/>Processor"]
        Orchestrator["Pipeline<br/>Orchestrator"]
        Agents["Agent Pipeline<br/>(Fetch → Review → Draft → Edit → Publish)"]
        LLM["Microsoft Foundry<br/>(LLM Provider)"]
        LocalLLM["Foundry Local<br/>(On-Device, Optional)"]
        Storage["Azure Storage<br/>(Static Assets)"]
        StaticSite["Static Web Apps<br/>(Public Site)"]
    end

    Editor -->|submits links,<br/>reviews content| Dashboard
    Dashboard -->|reads/writes| CosmosDB
    CosmosDB -->|change feed| ChangeFeed
    ChangeFeed -->|delegates| Orchestrator
    Orchestrator -->|coordinates| Agents
    Agents -->|LLM calls| LLM
    Agents -.->|"LLM calls<br/>(FOUNDRY_PROVIDER=local)"| LocalLLM
    Agents -->|reads/writes| CosmosDB
    Agents -->|uploads HTML| Storage
    Storage -->|serves| StaticSite
    Reader -->|reads newsletter| StaticSite
    Dashboard -.->|SSE updates| Editor
```

## Azure Infrastructure

All infrastructure is defined as Bicep templates in `infra/`. A single managed identity provides passwordless authentication between services — Container Apps uses it to access Cosmos DB, Storage, Container Registry, and App Configuration. Application Insights and Log Analytics handle observability, while Static Web Apps serves the public newsletter from blob storage.

```mermaid
graph TB
    subgraph Identity["Identity"]
        MI["Managed Identity"]
    end

    subgraph Compute["Compute"]
        ACA["Container Apps<br/>(FastAPI App)"]
        ACR["Container Registry<br/>(Docker Images)"]
    end

    subgraph Data["Data"]
        Cosmos["Cosmos DB<br/>(NoSQL API)"]
        SA["Storage Account<br/>(Static Assets)"]
        AppConfig["App Configuration<br/>(Runtime Config)"]
    end

    subgraph Web["Web"]
        SWA["Static Web Apps<br/>(Public Site)"]
    end

    subgraph Observability["Observability"]
        AppInsights["Application Insights"]
        LAW["Log Analytics<br/>Workspace"]
    end

    MI -.->|authenticates| ACA
    MI -.->|authenticates| Cosmos
    MI -.->|authenticates| SA
    MI -.->|authenticates| ACR
    MI -.->|authenticates| AppConfig

    ACR -->|pulls image| ACA
    ACA -->|reads/writes| Cosmos
    ACA -->|uploads HTML| SA
    ACA -->|reads config| AppConfig
    SA -->|serves| SWA

    ACA -->|telemetry| AppInsights
    AppInsights -->|backed by| LAW
```

## Agent Pipeline

The pipeline is orchestrated by a central `PipelineOrchestrator` — itself an Agent Framework agent — that coordinates five specialised sub-agents via tool calls. When a link is submitted, it flows sequentially through Fetch (extract content), Review (evaluate relevance), and Draft (compose newsletter copy). The Edit stage runs when an editor provides feedback on an edition, and Publish renders the final HTML and uploads it to storage. Each sub-agent has its own system prompt, registered tools, and middleware (token tracking).

```mermaid
graph LR
    CF["Change Feed<br/>Processor"] -->|link change| PO
    CF -->|feedback change| PO

    subgraph Orchestrator["Pipeline Orchestrator (Agent)"]
        PO["Orchestrator<br/>Agent"]
    end

    PO -->|"status: submitted"| Fetch["Fetch Agent<br/><i>Extract content</i>"]
    Fetch -->|"status: fetching"| Review["Review Agent<br/><i>Evaluate & categorise</i>"]
    Review -->|"status: reviewed"| Draft["Draft Agent<br/><i>Compose edition</i>"]

    PO -->|"editor feedback"| Edit["Edit Agent<br/><i>Refine content</i>"]
    PO -->|"publish approved"| Publish["Publish Agent<br/><i>Render & upload</i>"]

    Fetch & Review & Draft -->|read/write| DB[("Cosmos DB")]
    Edit & Publish -->|read/write| DB

    Publish -->|upload HTML| Storage["Azure Storage"]

    subgraph Middleware["Shared Middleware"]
        TT["Token Tracking"]
        TL["Tool Logging"]
    end

    Fetch & Review & Draft & Edit & Publish -.-> Middleware
```

## Event-Driven Data Flow

The system is event-driven with no external message broker — Cosmos DB's change feed is the sole event source. When a document is created or updated, the change feed processor picks it up and delegates to the orchestrator, which invokes the appropriate agent stage. As agents progress, they update documents in Cosmos DB (which may trigger further processing) and publish SSE events so the editorial dashboard updates in real time.

```mermaid
sequenceDiagram
    actor Editor
    participant Dashboard as Editorial Dashboard
    participant Cosmos as Cosmos DB
    participant CFP as Change Feed Processor
    participant Orch as Pipeline Orchestrator
    participant Agents as Sub-Agents
    participant LLM as Microsoft Foundry
    participant Storage as Azure Storage

    Editor->>Dashboard: Submit link
    Dashboard->>Cosmos: Create link (status: submitted)
    Cosmos-->>CFP: Change feed event

    CFP->>Orch: handle_link_change()
    Orch->>Agents: Fetch → extract content
    Agents->>LLM: LLM call
    LLM-->>Agents: Response
    Agents->>Cosmos: Update link (status: fetching)

    Orch->>Agents: Review → evaluate relevance
    Agents->>LLM: LLM call
    Agents->>Cosmos: Update link (status: reviewed)

    Orch->>Agents: Draft → compose edition
    Agents->>LLM: LLM call
    Agents->>Cosmos: Update edition content

    Orch-->>Dashboard: SSE (link-update, agent-run events)
    Dashboard-->>Editor: Real-time status updates

    Note over Editor,Dashboard: Editor reviews and provides feedback

    Editor->>Dashboard: Submit feedback
    Dashboard->>Cosmos: Create feedback doc
    Cosmos-->>CFP: Change feed event
    CFP->>Orch: handle_feedback_change()
    Orch->>Agents: Edit → refine content
    Agents->>Cosmos: Update edition

    Note over Editor,Dashboard: Editor approves for publish

    Editor->>Dashboard: Approve publish
    Dashboard->>Orch: handle_publish()
    Orch->>Agents: Publish → render HTML
    Agents->>Storage: Upload static files
```

## CI/CD Pipeline

The CI/CD pipeline is a chain of five GitHub Actions workflows connected via `workflow_run` triggers. Check and Test run in parallel on every push or PR to `main`. Once both pass, Build creates the Docker image and validates the Bicep templates. Release deploys the infrastructure, and Deploy updates the Container App. All Azure-facing workflows authenticate using OIDC federated credentials — no stored secrets.

```mermaid
graph LR
    Push["Push / PR<br/>to main"] --> Check & Test

    subgraph Parallel["Parallel"]
        Check["Check<br/><i>Lint, format, type check</i>"]
        Test["Test<br/><i>Unit & integration tests</i>"]
    end

    Check & Test -->|workflow_run| Build["Build<br/><i>Docker image → ACR<br/>Bicep validation</i>"]
    Build -->|workflow_run| Release["Release<br/><i>Bicep deployment<br/>(infra)</i>"]
    Release -->|workflow_run| Deploy["Deploy<br/><i>Container App update</i>"]

```
