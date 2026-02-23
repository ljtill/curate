# Architecture

This document provides a visual overview of Curate — an event-driven, agent-powered editorial pipeline for a newsletter about Agentic Engineering. Each section includes a diagram and a brief explanation of the components involved.

## System Overview

The platform has three main surfaces: an editorial dashboard where editors submit links and review content, an agent pipeline that autonomously processes links into newsletter editions, and a static site where published editions are served to readers. The system runs as two independent processes — a web service (FastAPI dashboard) and a worker (agent pipeline) — connected by Azure Service Bus for real-time event delivery. Cosmos DB sits at the centre as both the data store and the event backbone — its change feed drives the worker pipeline without polling.

```mermaid
graph TB
    Editor([Editor])
    Reader([Reader])

    subgraph Azure["Azure"]
        subgraph WebService["Web Service"]
            Dashboard["Editorial Dashboard<br/>(FastAPI + HTMX)"]
            SSE["SSE<br/>Event Manager"]
        end

        CosmosDB[("Cosmos DB<br/>(NoSQL API)")]
        ServiceBus["Azure Service Bus<br/>(Event Bridge)"]

        subgraph WorkerService["Worker Service"]
            ChangeFeed["Change Feed<br/>Processor"]
            Orchestrator["Pipeline<br/>Orchestrator"]
            Agents["Agent Pipeline<br/>(Fetch → Review → Draft → Edit → Publish)"]
        end

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
    Orchestrator -->|pipeline events| ServiceBus
    ServiceBus -->|consumed by| SSE
    SSE -.->|real-time updates| Editor

    classDef outer fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef inner fill:#7c3aed,stroke:#6d28d9,color:#fff
    classDef infra fill:#d97706,stroke:#b45309,color:#fff
    classDef human fill:#059669,stroke:#047857,color:#fff

    class Orchestrator outer
    class Agents,LLM,LocalLLM inner
    class Dashboard,SSE,CosmosDB,ChangeFeed,Storage,StaticSite,ServiceBus infra
    class Editor,Reader human

    style Azure fill:#f1f5f9,stroke:#94a3b8,color:#334155
    style WebService fill:#e0f2fe,stroke:#38bdf8,color:#0c4a6e
    style WorkerService fill:#ede9fe,stroke:#a78bfa,color:#3b0764
```

## Azure Infrastructure

All infrastructure is defined as Bicep templates in `infra/`. A single managed identity provides passwordless authentication between services. The web and worker run as separate Container Apps — the web service handles HTTP traffic and SSE, while the worker runs the agent pipeline. Azure Service Bus connects them for real-time event delivery. Application Insights and Log Analytics handle observability, while Static Web Apps serves the public newsletter from blob storage.

```mermaid
graph TB
    subgraph Identity["Identity"]
        MI["Managed Identity"]
    end

    subgraph Compute["Compute"]
        ACA_Web["Container Apps<br/>(Web — FastAPI)"]
        ACA_Worker["Container Apps<br/>(Worker — Pipeline)"]
        ACR["Container Registry<br/>(Docker Images)"]
    end

    subgraph Messaging["Messaging"]
        SB["Service Bus<br/>(Event Bridge)"]
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

    MI -.->|authenticates| ACA_Web
    MI -.->|authenticates| ACA_Worker
    MI -.->|authenticates| Cosmos
    MI -.->|authenticates| SA
    MI -.->|authenticates| ACR
    MI -.->|authenticates| AppConfig
    MI -.->|authenticates| SB

    ACR -->|pulls image| ACA_Web
    ACR -->|pulls image| ACA_Worker
    ACA_Web -->|reads| Cosmos
    ACA_Worker -->|reads/writes| Cosmos
    ACA_Worker -->|uploads HTML| SA
    ACA_Web -->|reads config| AppConfig
    ACA_Worker -->|reads config| AppConfig
    ACA_Worker -->|publishes events| SB
    SB -->|delivers events| ACA_Web
    SA -->|serves| SWA

    ACA_Web -->|telemetry| AppInsights
    ACA_Worker -->|telemetry| AppInsights
    AppInsights -->|backed by| LAW

    classDef outer fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef inner fill:#7c3aed,stroke:#6d28d9,color:#fff
    classDef infra fill:#d97706,stroke:#b45309,color:#fff
    classDef human fill:#059669,stroke:#047857,color:#fff

    class ACA_Web,ACA_Worker,ACR outer
    class SWA inner
    class Cosmos,SA,AppConfig,SB infra
    class MI human
    class AppInsights,LAW inner

    style Identity fill:#f1f5f9,stroke:#94a3b8,color:#334155
    style Compute fill:#f1f5f9,stroke:#94a3b8,color:#334155
    style Messaging fill:#f1f5f9,stroke:#94a3b8,color:#334155
    style Data fill:#f1f5f9,stroke:#94a3b8,color:#334155
    style Web fill:#f1f5f9,stroke:#94a3b8,color:#334155
    style Observability fill:#f1f5f9,stroke:#94a3b8,color:#334155
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

    classDef outer fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef inner fill:#7c3aed,stroke:#6d28d9,color:#fff
    classDef infra fill:#d97706,stroke:#b45309,color:#fff

    class PO outer
    class Fetch,Review,Draft,Edit,Publish,TT,TL inner
    class CF,DB,Storage infra

    style Orchestrator fill:#f1f5f9,stroke:#94a3b8,color:#334155
    style Middleware fill:#f1f5f9,stroke:#94a3b8,color:#334155
```

## Event-Driven Data Flow

The system is event-driven with two communication channels. Cosmos DB's change feed is the primary event source — when a document is created or updated, the change feed processor (in the worker) picks it up and delegates to the orchestrator. As agents progress, they update documents in Cosmos DB and publish SSE events via Azure Service Bus. The web service consumes these Service Bus messages and pushes them to connected dashboard clients via SSE.

```mermaid
sequenceDiagram
    actor Editor
    participant Dashboard as Web Service<br/>(Dashboard)
    participant ServiceBus as Azure<br/>Service Bus
    participant Cosmos as Cosmos DB
    participant Worker as Worker Service<br/>(Pipeline)
    participant Agents as Sub-Agents
    participant LLM as Microsoft Foundry
    participant Storage as Azure Storage

    Editor->>Dashboard: Submit link
    Dashboard->>Cosmos: Create link (status: submitted)
    Cosmos-->>Worker: Change feed event

    Worker->>Agents: Fetch → extract content
    Agents->>LLM: LLM call
    LLM-->>Agents: Response
    Agents->>Cosmos: Update link (status: fetching)

    Worker->>Agents: Review → evaluate relevance
    Agents->>LLM: LLM call
    Agents->>Cosmos: Update link (status: reviewed)

    Worker->>Agents: Draft → compose edition
    Agents->>LLM: LLM call
    Agents->>Cosmos: Update edition content

    Worker->>ServiceBus: Publish pipeline events
    ServiceBus-->>Dashboard: Deliver events
    Dashboard-->>Editor: SSE (real-time status updates)

    Note over Editor,Dashboard: Editor reviews and provides feedback

    Editor->>Dashboard: Submit feedback
    Dashboard->>Cosmos: Create feedback doc
    Cosmos-->>Worker: Change feed event
    Worker->>Agents: Edit → refine content
    Agents->>Cosmos: Update edition

    Note over Editor,Dashboard: Editor approves for publish

    Editor->>Dashboard: Approve publish
    Dashboard->>ServiceBus: Publish request
    ServiceBus-->>Worker: Consume request
    Worker->>Agents: Publish → render HTML
    Agents->>Storage: Upload static files
```

## CI/CD Pipeline

The CI/CD pipeline is a chain of five GitHub Actions workflows connected via `workflow_run` triggers. Check and Test run in parallel on every push or PR to `main`. Once both pass, Build creates Docker images for both the web and worker services and validates the Bicep templates. Release deploys the infrastructure, and Deploy updates both Container Apps. All Azure-facing workflows authenticate using OIDC federated credentials — no stored secrets.

```mermaid
graph LR
    Push["Push / PR<br/>to main"] --> Check & Test

    subgraph Parallel["Parallel"]
        Check["Check<br/><i>Lint, format, type check</i>"]
        Test["Test<br/><i>Unit & integration tests</i>"]
    end

    Check & Test -->|workflow_run| Build["Build<br/><i>Docker images (web + worker) → ACR<br/>Bicep validation</i>"]
    Build -->|workflow_run| Release["Release<br/><i>Bicep deployment<br/>(infra)</i>"]
    Release -->|workflow_run| Deploy["Deploy<br/><i>Container Apps update<br/>(web + worker)</i>"]

    classDef outer fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef inner fill:#7c3aed,stroke:#6d28d9,color:#fff
    classDef infra fill:#d97706,stroke:#b45309,color:#fff
    classDef human fill:#059669,stroke:#047857,color:#fff

    class Push human
    class Check,Test outer
    class Build inner
    class Release,Deploy infra

    style Parallel fill:#f1f5f9,stroke:#94a3b8,color:#334155
```
