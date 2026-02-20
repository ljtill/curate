# The Agent Stack — Project Specification

> A platform for "The Agent Stack", a newsletter about Agentic Engineering. The system comprises an event-driven, agent-powered editorial pipeline with a private admin UI, and a statically generated public newsletter site.

## Table of Contents

- [Constraints \& Tech Stack](#constraints--tech-stack)
- [System Components](#system-components)
  - [Link Ingestion](#1-link-ingestion)
  - [Agent Pipeline](#2-agent-pipeline)
  - [Editorial Dashboard](#3-editorial-dashboard-private)
  - [Public Newsletter Site](#4-public-newsletter-site)
- [Data Model](#data-model)
- [Design Decisions](#design-decisions)
- [Future Scope](#future-scope)

---

## Constraints & Tech Stack

- **Language**: Python (primary), other languages as needed
- **Orchestration**: [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- **LLM Provider**: [Microsoft Foundry](https://foundry.microsoft.com/)
- **Hosting**: Microsoft Azure
  - **Azure Container Apps** — editorial service (FastAPI)
  - **Azure Cosmos DB** (NoSQL API) — data persistence, change feed as event source
  - **Azure Storage Account** — generated newsletter static assets
  - **Azure Static Web Apps** — public newsletter site
  - **Azure App Configuration** — runtime configuration
- **Auth**: Microsoft Entra ID for the editorial dashboard

---

## System Components

### 1. Link Ingestion

Links are submitted through the Editorial Dashboard (Links view). Submitting a link writes a document to Cosmos DB, which triggers the agent pipeline via the change feed.

### 2. Agent Pipeline

Event-driven and continuously iterating. Agents react to changes — new links, editor feedback — and refine the current edition. The pipeline is triggered via the Cosmos DB change feed, consumed by a dedicated change feed processor running within the Container App.

**Orchestration layer:** An explicit orchestrator handles agent-to-agent flow control. The change feed processor delegates incoming events to the orchestrator, which determines the appropriate agent stage based on document type and status, manages transitions between stages, and handles error/retry logic.

**Agent stages:**

| Stage       | Responsibility                                                                                   |
|-------------|--------------------------------------------------------------------------------------------------|
| **Fetch**   | Retrieve and parse submitted link content                                                        |
| **Review**  | Evaluate relevance, extract key insights, categorize                                             |
| **Draft**   | Compose or revise newsletter content from reviewed material                                      |
| **Edit**    | Refine tone, structure, and coherence across the full edition                                     |
| **Publish** | Render final edition content against the HTML template, generate static pages, deploy to Azure    |

**Pipeline characteristics:**

- The edition is a living document — agents continuously iterate as new links arrive and editor feedback is submitted.
- Agents work from a version-controlled HTML template (stored in the repository) for the newsletter layout and have autonomy to determine how best to structure content within that template.
- The publish agent uploads rendered static files to an Azure Storage Account; Azure Static Web Apps pulls from that storage for serving.

### 3. Editorial Dashboard (Private)

FastAPI + Jinja2 + HTMX server-rendered admin UI, authenticated via Microsoft Entra ID.

**Views:**

- **Dashboard** — overview of pipeline status, current edition, recent activity.
- **Links** — submit new links, view agent processing status per link (`submitted` → `fetching` → `reviewed` → `drafted`). HTMX updates status in-place.
- **Editions** — list of all editions with status (`created` → `drafting` → `in_review` → `published`).
- **Edition Detail** — review agent-generated content, per-section structured feedback interface for comments back to agents (bidirectional), publish action when ready.

**Edition model:** Single active edition — all submitted links feed into the current draft. The editor creates a new edition when ready to start the next one.

### 4. Public Newsletter Site

Agent-generated static pages served via Azure Static Web Apps. The publish agent renders the edition against the HTML template, outputs static files to an Azure Storage Account, and Azure Static Web Apps serves from that storage. Web-only distribution for now.

---

## Data Model

Cosmos DB (NoSQL API), leveraging the change feed as the event backbone for agent triggering. Each document type lives in its own container for clean separation.

### Containers & Partition Keys

| Container      | Partition Key   | Rationale                                                        |
|----------------|-----------------|------------------------------------------------------------------|
| `links`        | `/edition_id`   | Links are queried per edition; co-locates related links          |
| `editions`     | `/id`           | Each edition is accessed individually; single-document partition |
| `feedback`     | `/edition_id`   | Feedback is queried per edition alongside content review         |
| `agent_runs`   | `/trigger_id`   | Runs are queried by the document that triggered them             |

### Document Types

#### Links

Container: `links` · Partition key: `/edition_id`

Submitted URLs with metadata, agent processing status, and extracted content.

| Field              | Description                                              |
|--------------------|----------------------------------------------------------|
| `id`               | Unique identifier                                        |
| `url`              | Submitted URL                                            |
| `title`            | Page title (populated by Fetch agent)                    |
| `status`           | Processing status: `submitted` → `fetching` → `reviewed` → `drafted` |
| `content`          | Extracted/parsed content (populated by Fetch agent)      |
| `review`           | Agent review output — relevance, insights, category      |
| `edition_id`       | Associated edition (partition key)                       |
| `submitted_at`     | Submission timestamp                                     |
| `updated_at`       | Last update timestamp                                    |

#### Editions

Container: `editions` · Partition key: `/id`

Flexible content structure defined by agents, lifecycle status, and associated links.

| Field              | Description                                              |
|--------------------|----------------------------------------------------------|
| `id`               | Unique identifier (partition key)                        |
| `status`           | Lifecycle status: `created` → `drafting` → `in_review` → `published` |
| `content`          | Agent-generated edition content (flexible structure)     |
| `link_ids`         | Associated link document IDs                             |
| `published_at`     | Publish timestamp (when applicable)                      |
| `created_at`       | Creation timestamp                                       |
| `updated_at`       | Last update timestamp                                    |

#### Feedback

Container: `feedback` · Partition key: `/edition_id`

Structured per-section editor comments, linked to editions.

| Field              | Description                                              |
|--------------------|----------------------------------------------------------|
| `id`               | Unique identifier                                        |
| `edition_id`       | Associated edition (partition key)                       |
| `section`          | Target section identifier                                |
| `comment`          | Editor feedback text                                     |
| `resolved`         | Whether the feedback has been addressed by agents        |
| `created_at`       | Submission timestamp                                     |

#### Agent Runs

Container: `agent_runs` · Partition key: `/trigger_id`

Execution logs, decisions, and state per pipeline stage.

| Field              | Description                                              |
|--------------------|----------------------------------------------------------|
| `id`               | Unique identifier                                        |
| `stage`            | Pipeline stage (`fetch`, `review`, `draft`, `edit`, `publish`) |
| `trigger_id`       | ID of the document that triggered the run (partition key)|
| `status`           | Run status (`running`, `completed`, `failed`)            |
| `input`            | Input data/context for the agent                         |
| `output`           | Agent output/decisions                                   |
| `started_at`       | Start timestamp                                          |
| `completed_at`     | Completion timestamp                                     |

---

## Design Decisions

Resolved decisions that shape the implementation:

| Decision                        | Resolution                                                                                         |
|---------------------------------|----------------------------------------------------------------------------------------------------|
| **Change feed consumer**        | Dedicated change feed processor within the Container App (fewer services, simpler deployment).      |
| **Agent flow control**          | Explicit orchestration layer handles stage transitions, routing, and error/retry logic.              |
| **Cosmos DB container layout**  | Multiple containers (one per document type) for clean separation.                                    |
| **Cosmos DB partitioning**      | `links` and `feedback` by `edition_id`, `editions` by `id`, `agent_runs` by `trigger_id`.           |
| **LLM provider**                | Microsoft Foundry.                                                                                   |
| **Feedback granularity**        | Per-section — matches the natural editorial workflow.                                               |
| **HTML template management**    | Version controlled in the repository — simpler and auditable.                                       |
| **Static site deployment**      | Publish agent uploads to Azure Storage Account; Azure Static Web Apps pulls from storage (decoupled). |

---

## Future Scope

- Email distribution and subscriber management
- Multiple concurrent editions
- Additional link ingestion methods (API endpoint, browser extension, email forwarding)
- Manual link-to-edition curation
- Publishing cadence and scheduling
