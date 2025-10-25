# Multi-tenant Conversational Sales Agent

## Overview
This project delivers a multi-tenant conversational sales assistant that ingests tenant knowledge, answers questions with retrieval-augmented generation (RAG), captures qualified leads, and books appointments in Google Calendar. It is designed for agencies, multi-branch organisations, and internal teams that need strict data isolation while sharing the same backend.

## Key Features
- **Tenant-isolated RAG chat** – Gemini + Pinecone retrieval scoped by JWT claims (`org_id`, `branch_id`, `user_id`).
- **Intent-aware lead capture** – LangGraph/Gemini classifier plus heuristics tag booking/purchase intent, persist leads, and track confidence/rationale.
- **Chat-driven scheduling** – Users can book, reschedule, or cancel meetings via chat; confirmed slots create/update Google Calendar events and update leads.
- **Operator visibility** – REST endpoints expose conversation, lead, and scheduling data for dashboards or automation.
- **Roadmap toward NL lead search** – Planning underway for natural-language queries over the leads collection with Gemini → Mongo translation.

## Tech Stack
- **Backend**: FastAPI, Poetry, Pydantic v2, LangChain, LangGraph
- **AI Services**: Gemini 2.5 Flash (chat), text-embedding-004 (retrieval)
- **Vector Store**: Pinecone
- **Database**: MongoDB
- **Scheduling**: Google Calendar OAuth (offline tokens per tenant)
- **Frontend (optional)**: Streamlit apps under `frontend/`

## Prerequisites
- Python 3.10+
- MongoDB instance (local or hosted)
- Pinecone index (`dimension=768`, `metric=cosine`)
- Gemini API key with access to chat + embedding models
- Google Cloud OAuth 2.0 client (web application) with redirect `http://localhost:8000/oauth/google/callback`
- (Optional) SMTP or SendGrid credentials if you intend to send emails

## Quick Start
1. **Clone & install**
   ```bash
   git clone <repo-url>
   cd <repo>
   poetry install
   ```
2. **Configure environment**
   - Copy `.env.example` to `.env` and populate secrets (JWT, Gemini, Pinecone, MongoDB, Google OAuth, etc.).
3. **Run the API**
   ```bash
   poetry run uvicorn app.main:app --reload --port 8000
   ```
4. **(Optional) Streamlit UI**
   ```bash
   poetry run streamlit run frontend/streamlit_app.py --server.port 8001
   ```
   - Upload PDFs for ingestion, drive chat conversations, inspect detected intents, and monitor leads/appointments directly from the console.

## Google OAuth Workflow
1. `GET /oauth/google/init` to obtain an authorisation URL (requires bearer token).
2. Visit the URL, consent in Google, and allow redirect back to `/oauth/google/callback`.
3. Verify with `GET /oauth/google/status` → `{ "connected": true }`.
4. The tenant can now create, reschedule, or cancel events via chat or REST.

## API Essentials
| Endpoint | Description |
| --- | --- |
| `POST /auth/token` | Issue a JWT for testing (pass org/branch/user). |
| `GET /auth/token/dev` | Convenience token for local development. |
| `POST /api/ingest` | Multipart PDF upload → chunk → embed → Pinecone upsert. |
| `POST /api/chat` | Tenant-scoped conversation, lead capture, and scheduling. |
| `GET /api/leads` | List leads for the current tenant branch. |
| `POST /api/appointments` | Create a Google Calendar event (requires OAuth). |
| `PATCH /api/appointments/{event_id}` | Update an existing event. |
| `DELETE /api/appointments/{event_id}` | Cancel an event. |
| `GET /logs/recent` | Fetch latest backend logs (JWT protected). |

### Typical Chat Flow
1. User authenticates and calls `POST /api/chat`.
2. Intent classifier runs first:
   - `book_appointment`: lead recorded, scheduling handler attempts to parse time.
   - `purchase`: lead recorded, no calendar action (extend as needed).
   - `none`: skip scheduling, run RAG.
3. Scheduler behaviour:
   - Vague request → assistant asks for specific date/time.
   - Concrete slot → create/update calendar event, confirm in reply.
   - “Cancel meeting” → delete event, free the lead.
4. Leads can be inspected via `GET /api/leads`; each carries appointment metadata.

## Running Tests
- Enable deterministic dependencies by setting `TESTING=1` (mocks external services via `app/deps.configure_test_dependencies`).
- Pytest entrypoint (placeholder for future suites):
  ```bash
  poetry run pytest
  ```

## Roadmap Snapshot
- **Phase 0** – Environment setup and secret management ✔️
- **Phase 1** – FastAPI skeleton, JWT, logging ✔️
- **Phase 2** – Document ingestion & embeddings ✔️
- **Phase 3** – Conversational RAG service ✔️
- **Phase 4** – Lead capture & intent handling ✔️
- **Phase 5** – Calendar automation & chat-driven scheduling ✔️
- **Phase 5.5 (Planned)** – Natural-language lead search (see below)
- **Phase 6** – Operator dashboard (Streamlit)
- **Phase 7** – Observability & reliability
- **Phase 8** – Testing, security review, deployment

## Troubleshooting
- **OAuth callback returns scope mismatch**: ensure `.env` scopes include `calendar.events`, `calendar.events.readonly`, and `calendar.readonly` (already set in `SCOPES` constant).
- **`email-validator` import error**: Poetry install now includes it; re-run `poetry install` if you upgrade environments.
- **Missing Pinecone index**: Create an index with `dimension=768`, `metric=cosine`, and name matching `PINECONE_INDEX` in `.env`.

## Contributing
- Fork and branch from `main` (`feature/<name>`).
- Use Poetry for dependency management.
- Provide `.env.example` updates when adding new configuration knobs.
- Run linting/tests before PRs (tooling TBD).

## NL Lead Search Plan (Upcoming Work)
1. **Schema surface**  
   - Lead fields exposed: intent, confidence, status, timestamps, latest message, appointment metadata.  
   - Enforce tenant filters (`org_id`, `branch_id`); redact sensitive fields.

2. **LLM → Query translation**  
   - Create `mongo_search` service with a Gemini prompt describing the leads schema and sample entries.  
   - Return constrained JSON (`collection`, `filter`, `projection`, `limit`), validated via Pydantic before execution.

3. **Execution guardrails**  
   - Read-only operations, whitelist of allowed fields/operators, hard caps on result count & payload size.  
   - Structured logging for intent label, translated query, results, and latency.

4. **API & chat integration**  
   - REST route `GET /api/leads/search?query=...` (JWT protected) returning raw hits + optional Gemini summary.  
   - Optional chat intent (`query_leads`) to route relevant NL requests through the search service.

5. **Streamlit UI support**  
   - Add a “Lead Search” tab: natural-language input, show generated filter JSON, render results table + summary.

6. **Testing**  
   - Mock Gemini in pytest to emit canned filters; cover invalid output, schema mismatch, tenant isolation, pagination.


