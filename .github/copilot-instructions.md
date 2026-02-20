# Copilot Instructions

## Project Overview

Agent Stack is an event-driven, agent-powered editorial pipeline for a newsletter about Agentic Engineering. The system has four components:

1. **Link Ingestion** — links submitted via the editorial dashboard, stored in Cosmos DB, triggering the agent pipeline via change feed
2. **Agent Pipeline** — orchestrated multi-stage pipeline (Fetch → Review → Draft → Edit → Publish) reacting to Cosmos DB change feed events
3. **Editorial Dashboard** — FastAPI + Jinja2 + HTMX server-rendered admin UI, authenticated via Microsoft Entra ID
4. **Public Newsletter Site** — agent-generated static pages served via Azure Static Web Apps

## Tech Stack

- **Language**: Python 3.13 (managed with `uv`)
- **Agent Orchestration**: [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- **LLM Provider**: [Microsoft Foundry](https://foundry.microsoft.com/)
- **Web Framework**: FastAPI + Jinja2 + HTMX
- **Database**: Azure Cosmos DB (NoSQL API) — change feed as event backbone
- **Hosting**: Azure Container Apps, Azure Static Web Apps, Azure Storage Account
- **Config**: Azure App Configuration

## Architecture

The agent pipeline uses an explicit orchestrator for agent-to-agent flow control. The Cosmos DB change feed processor runs within the Container App and delegates events to the orchestrator, which determines the appropriate agent stage based on document type and status.

**Agent stages**: Fetch (retrieve/parse links) → Review (evaluate relevance, categorize) → Draft (compose content) → Edit (refine tone/structure) → Publish (render HTML template, deploy static pages)

**Data model** uses separate Cosmos DB containers per document type:
- `links` (partitioned by `/edition_id`) — submitted URLs with processing status
- `editions` (partitioned by `/id`) — living documents continuously refined by agents
- `feedback` (partitioned by `/edition_id`) — per-section editor comments
- `agent_runs` (partitioned by `/trigger_id`) — execution logs per pipeline stage

Single active edition model — all submitted links feed into the current draft.

## Key Conventions

- The full project spec lives in `docs/SPEC.md` — consult it for data model details, design decisions, and component specifications
- Newsletter HTML templates are version-controlled in the repository
- The publish agent uploads rendered static files to Azure Storage; Static Web Apps serves from that storage (decoupled)
- Feedback is per-section granularity, supporting bidirectional editor-agent communication
