# Multi-Tenant Conversational Sales Agent

## Overview
This project provides a full-stack, multi-tenant sales assistant that can ingest tenant knowledge, answer questions with retrieval-augmented generation (RAG), capture and manage leads, and book appointments on shared Google Calendars. Everything is scoped by JWT claims (`org_id`, `branch_id`, `user_id`) so multiple organisations and branches can safely share the same deployment.

Key components now include:
- Tenant-aware RAG chat powered by Gemini + Pinecone.
- Intent detection and lead persistence with booking/purchase tracking.
- Calendar automation for booking, rescheduling, cancelling meetings, and emailing confirmations.
- A Streamlit “Operator Console” for document ingestion, live chats, lead management, outreach email drafting, and natural-language lead search.
- Observability via structured logs and pytest coverage for critical flows.

## Feature Highlights
- **Tenant-Isolated RAG Chat**  
  Gemini 2.5 Flash answers user questions using Pinecone retrieval with tenant filters. Chosen embeddings: `text-embedding-004`.

- **Intent-Aware Lead Capture**  
  LangGraph + Gemini classify each message (`book_appointment`, `purchase`, `none`). Leads are stored in MongoDB with confidence, rationale, appointment metadata, and timestamps.

- **Calendar Automation**  
  Chat flows create, update, and delete Google Calendar events (OAuth-based). Appointments sync back to leads to keep status in lockstep, and confirmation emails are sent automatically when meetings are booked or rescheduled.

- **Natural-Language Lead Search (New)**  
  `GET /api/leads/search` translates plain English or JSON filters into safe MongoDB queries. Gemini produces both the filter and a narrative summary of the top results, with deterministic fallbacks if the LLM is unavailable.

- **Lead Outreach Emails (New)**  
  Operators can generate AI-assisted follow-up drafts for open leads, edit them directly in Streamlit, and send via the configured SMTP provider—no CLI required.

- **Operator Streamlit Console**  
  Upload PDFs for ingestion, monitor conversations, review leads/appointments, manage outreach emails (draft/edit/send), and run NL lead searches. When Gemini summaries are enabled, the Lead Search tab shows the LLM narrative plus the executed filter and raw hits.

- **Reliability & Observability**  
  Structured logging (including Gemini health checks, query metadata, and summary sources), pytest coverage with mocked Pinecone/Gemini/Google services, and guardrails on tenant filters, allowed fields, and result limits.

## Architecture & Tech Stack
- **Backend**: FastAPI, Poetry, Pydantic v2, LangChain, LangGraph.
- **AI Services**: Gemini (`gemini-2.5-flash` for chat/analysis, `text-embedding-004` for embeddings).
- **Vector Store**: Pinecone.
- **Database**: MongoDB.
- **Calendar Integration**: Google Calendar OAuth (per-tenant offline tokens).
- **Frontend**: Streamlit app under `frontend/`.

## Prerequisites
- Python 3.10+
- MongoDB instance (local or hosted)
- Pinecone index (`dimension=768`, `metric=cosine`)
- Gemini API key with access to chat + embedding models
- Google OAuth 2.0 Web Client with redirect `http://localhost:8000/oauth/google/callback`
- SMTP credentials (SendGrid, SES, or SMTP) for appointment confirmations and outreach emails

## Installation & Setup
1. **Clone and install dependencies**
   ```bash
   git clone <repo-url>
   cd <repo>
   poetry install
   ```

2. **Configure environment variables**
   - Copy `.env.example` to `.env`.
   - Populate secrets for JWT, MongoDB, Pinecone, Gemini, Google OAuth, SMTP, etc.
   - The settings module (`app/settings.py`) lists every required knob.

3. **Run the FastAPI backend**
   ```bash
   poetry run uvicorn app.main:app --reload --port 8000
   ```

4. **Launch the Streamlit operator console (optional)**
   ```bash
   poetry run streamlit run frontend/streamlit_app.py --server.port 8001
   ```
   - Sidebar: configure API base URL, bearer token (e.g. from `/auth/token/dev`), and conversation ID.
   - Tabs cover document ingestion, chat console, leads & appointments, and lead search.

## Core Workflows
### Document Ingestion
1. Upload a PDF via Streamlit or call `POST /api/ingest`.
2. The service parses pages, chunks text with tiktoken, generates embeddings, and upserts into Pinecone with `org_id` / `branch_id` in the namespace.

### Chat & Lead Capture
1. Clients call `POST /api/chat` with user messages and JWT auth.
2. Intent detection runs first to avoid wasting tokens on RAG when a booking or purchase flow is needed.
3. Leads are stored/updated for every booking or purchase intent; chat responses cite relevant knowledge and prompt for missing details.
4. Calendar events are created/updated/deleted as the conversation progresses.

### Lead Outreach & Email Workflows (New)
1. Open the **Lead Outreach** tab in Streamlit.
2. Refresh open leads, select a conversation, and review the transcript.
3. Generate an editable sales email draft grounded in RAG snippets.
4. Adjust the subject/body, then send directly via the configured SMTP provider.
5. Appointment bookings and reschedules also trigger automated confirmation emails with calendar links.

### Natural-Language Lead Search
1. Call `GET /api/leads/search?q=Show open leads without a calendar event&summarize=true`.
2. Gemini (via LangChain) generates a MongoDB filter/limit JSON. Guardrails enforce tenant filters, allowed fields/operators, and result caps.
3. Results return with:
   - `query` (executed filter/projection/limit)
   - `results` (sanitised documents)
   - `summary` (Gemini narrative or deterministic fallback)
   - `elapsed_ms`, `count`, etc.
4. Streamlit’s Lead Search tab mirrors this flow and surfaces both the executed filter and narrative.

## API Reference Snapshot
| Endpoint | Description |
| --- | --- |
| `POST /auth/token` | Issue a JWT with specific tenant claims. |
| `GET /auth/token/dev` | Fast dev token (honours `settings.DEV_TOKEN_*`). |
| `POST /api/ingest` | Multipart PDF ingestion with tenant scoping. |
| `POST /api/chat` | Tenant-aware chat, lead capture, and scheduling. |
| `GET /api/leads` | Retrieve all leads for the tenant branch. |
| `GET /api/leads/search` | Natural-language or JSON-lead search with optional Gemini summary. |
| `POST /api/outreach/email/draft` | Generate an outreach email draft from conversation context. |
| `POST /api/outreach/email/send` | Deliver the edited outreach email via SMTP. |
| `GET /api/outreach/open-leads` | List open leads with conversations ready for follow-up. |
| `GET /api/outreach/conversations/{id}` | Fetch recent messages for a conversation. |
| `GET /oauth/google/init` | Start OAuth flow for the current tenant. |
| `GET /oauth/google/status` | Confirm calendar connectivity. |

## Logs & Observability
- All structured logs are written to `logs/app.log` (see `app/logging_config.py`). Nothing is printed to stdout except uvicorn access logs.
- Lead search logging includes the intent label, generated filter, projection, limit, result count, response time, and whether the Gemini summary or fallback was returned.
- Warnings highlight LLM failures, missing providers, or health check issues.

## Testing
- Set `TESTING=1` in the environment to route external dependencies through lightweight test doubles (`configure_test_dependencies`).
- Run the focused suite:
  ```bash
  poetry run pytest tests/test_lead_search.py
  ```
  (More suites can be added under `tests/` as features grow.)
- Tests currently cover:
  - LLM query translation and sanitisation.
  - Lead search execution + field redaction.
  - Gemini summary success, structured output parsing, fallback behaviour, and metadata filtering.
  - Streamlit helper summaries (pure functions).

## Troubleshooting
- **`Gemini unavailable: Models.list()` error**: remove old `page_size` parameter from health checks (already fixed in `app/deps.py`).
- **`MAX_TOKENS` summary**: indicates Gemini hit output limits; retry or adjust the prompt if frequent.
- **OAuth scope mismatch**: ensure `.env` uses `https://www.googleapis.com/auth/calendar.events`, `calendar.events.readonly`, and `calendar.readonly`.
- **`email-validator` import error**: run `poetry install` after updating dependency lockfiles.
- **Missing Pinecone index**: create an index with 768 dimensions and cosine metric matching `settings.PINECONE_INDEX`.

## Roadmap
- Harden lead search with more analytics dashboards and paging.
- Extend purchase intent flow with CRM/webhook integrations.
- Layer additional analytics (metrics export, tracing).
- Production hardening (CI/CD, lint/format hooks, secrets management).

## Contributing
1. Fork and branch from `main` (`feature/<name>`).
2. Use Poetry to manage dependencies.
3. Update `.env.example` and documentation when adding configuration.
4. Run `poetry run pytest` before opening a PR.

The project aims to provide a production-ready foundation for multi-tenant, AI-assisted sales operations. Contributions, bug reports, and feature ideas are always welcome.
