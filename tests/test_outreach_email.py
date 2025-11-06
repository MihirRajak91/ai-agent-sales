from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId

from app.models.auth import TenantClaims
from app.models.retrieval import RetrievedChunk
from app.utils.constants import OUTREACH_EMAIL_DEFAULT_SUBJECT
from app.services import outreach


def _insert_lead_and_conversation(db, *, tenant: TenantClaims, conversation_id: str) -> str:
    now = datetime.now(timezone.utc)
    lead_id = db["leads"].insert_one(
        {
            "_id": ObjectId(),
            "conversation_id": conversation_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
            "intent": "book_appointment",
            "status": "open",
            "latest_message": "Can you email pricing details?",
            "created_at": now,
            "updated_at": now,
        }
    ).inserted_id

    db["conversations"].insert_one(
        {
            "_id": conversation_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
            "messages": [
                {"role": "assistant", "content": "Happy to help!", "timestamp": now},
                {
                    "role": "user",
                    "content": "Here's my email: lead@example.com",
                    "timestamp": now,
                },
            ],
            "created_at": now,
            "updated_at": now,
        }
    )
    return str(lead_id)


def _auth_headers(client):
    token_resp = client.post(
        "/auth/token",
        json={"org_id": "org1", "branch_id": "branch1", "user_id": "agent1"},
    )
    token_resp.raise_for_status()
    token = token_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_generate_email_draft_returns_recipient_and_body(api_client, monkeypatch):
    client, db, _ = api_client
    tenant = TenantClaims(org_id="org1", branch_id="branch1", user_id="agent1")
    conversation_id = "conv-email-1"
    lead_id = _insert_lead_and_conversation(db, tenant=tenant, conversation_id=conversation_id)

    class DummyLLM:
        def invoke(self, _prompt):
            return SimpleNamespace(content="Draft email body.")

    monkeypatch.setattr(outreach, "_build_llm", lambda: DummyLLM())
    monkeypatch.setattr(
        outreach,
        "query_knowledge_base",
        lambda _tenant, _query, top_k=None: SimpleNamespace(
            matches=[
                RetrievedChunk(
                    chunk_id="chunk-1",
                    score=0.88,
                    text="Pricing starts at $99 per month.",
                    page=2,
                    source="Pricing Guide",
                )
            ]
        ),
    )

    draft = outreach.generate_email_draft(tenant, conversation_id)

    assert draft["lead_id"] == lead_id
    assert draft["conversation_id"] == conversation_id
    assert draft["body"] == "Draft email body."
    assert draft["suggested_recipient"] == "lead@example.com"
    assert draft["subject"] == f"Next steps on your book appointment"
    assert draft["intent"] == "book_appointment"
    assert draft["latest_message"] == "Can you email pricing details?"


def test_generate_email_draft_endpoint_returns_payload(api_client, monkeypatch):
    client, db, _ = api_client
    headers = _auth_headers(client)
    tenant = TenantClaims(org_id="org1", branch_id="branch1", user_id="agent1")
    conversation_id = "conv-email-2"
    _insert_lead_and_conversation(db, tenant=tenant, conversation_id=conversation_id)
    db["leads"].update_one({"conversation_id": conversation_id}, {"$set": {"intent": ""}})

    class DummyLLM:
        def invoke(self, _prompt):
            return SimpleNamespace(content="Outbound follow-up draft.")

    monkeypatch.setattr(outreach, "_build_llm", lambda: DummyLLM())
    monkeypatch.setattr(
        outreach,
        "query_knowledge_base",
        lambda _tenant, _query, top_k=None: SimpleNamespace(matches=[]),
    )

    response = client.post(
        "/api/outreach/email/draft",
        json={"conversation_id": conversation_id, "history_limit": 0},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["body"] == "Outbound follow-up draft."
    assert payload["suggested_recipient"] == "lead@example.com"
    assert payload["subject"] == OUTREACH_EMAIL_DEFAULT_SUBJECT
