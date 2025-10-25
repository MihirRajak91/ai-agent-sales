import json

import pytest

from fastapi.testclient import TestClient

from app.models.auth import TenantClaims
from app.models.search import LeadSearchQuery
from app.services import lead_search
from app.settings import settings


class DummyLLM:
    def __call__(self, *_args, **_kwargs):
        return self

    def invoke(self, messages):
        payload = self.payload
        if isinstance(payload, str):
            content = payload
        else:
            content = json.dumps(payload)
        return type("Resp", (), {"content": content})()


@pytest.fixture
def tenant():
    return TenantClaims(org_id="org1", branch_id="branch1", user_id="agent1")


def test_generate_query_adds_tenant_filters(monkeypatch, tenant):
    lead_search._lead_search_llm.cache_clear()
    llm = DummyLLM()
    llm.payload = {
        "collection": "leads",
        "filter": {"status": "open"},
        "projection": {"intent": 1},
        "limit": 5,
    }
    monkeypatch.setattr(lead_search, "_lead_search_llm", lambda: llm)

    query = lead_search.generate_lead_search_query(tenant, "show open leads")
    assert query.collection == "leads"
    assert query.filter["org_id"] == "org1"
    assert query.filter["branch_id"] == "branch1"
    assert query.limit == 5
    assert query.projection == {"intent": 1}


def test_generate_query_invalid_field(monkeypatch, tenant):
    lead_search._lead_search_llm.cache_clear()
    llm = DummyLLM()
    llm.payload = {
        "collection": "leads",
        "filter": {"unknown": "value"},
    }
    monkeypatch.setattr(lead_search, "_lead_search_llm", lambda: llm)

    with pytest.raises(ValueError):
        lead_search.generate_lead_search_query(tenant, "bad field")


def test_generate_query_rejects_wrong_collection(monkeypatch, tenant):
    lead_search._lead_search_llm.cache_clear()
    llm = DummyLLM()
    llm.payload = {
        "collection": "sessions",
        "filter": {"status": "open"},
    }
    monkeypatch.setattr(lead_search, "_lead_search_llm", lambda: llm)

    with pytest.raises(ValueError):
        lead_search.generate_lead_search_query(tenant, "wrong collection")


def test_execute_lead_search_returns_sanitized_results(api_client, tenant):
    _client, db, _calendar = api_client
    leads = db["leads"]
    leads.insert_many(
        [
            {
                "org_id": "org1",
                "branch_id": "branch1",
                "user_id": "agent1",
                "intent": "book_appointment",
                "status": "open",
                "latest_message": "Need a demo tomorrow",
            },
            {
                "org_id": "org1",
                "branch_id": "branch1",
                "user_id": "agent1",
                "intent": "purchase",
                "status": "closed",
            },
            {
                "org_id": "org2",
                "branch_id": "branchX",
                "intent": "book_appointment",
                "status": "open",
            },
        ]
    )

    query = LeadSearchQuery(
        collection="leads",
        filter={"status": "open", "org_id": "org1", "branch_id": "branch1"},
        limit=10,
    )
    result = lead_search.execute_lead_search_query(tenant, query, intent_label="query_leads")
    assert result["count"] == 1
    record = result["results"][0]
    assert record["intent"] == "book_appointment"
    assert "latest_message" not in record
    assert result["query"]["filter"]["status"] == "open"


def test_execute_lead_search_respects_limit(api_client, tenant):
    _client, db, _calendar = api_client
    leads = db["leads"]
    for i in range(5):
        leads.insert_one(
            {
                "org_id": "org1",
                "branch_id": "branch1",
                "user_id": "agent1",
                "intent": "book_appointment",
                "status": "open",
                "latest_message": f"lead {i}",
            }
        )

    query = LeadSearchQuery(
        collection="leads",
        filter={"org_id": "org1", "branch_id": "branch1"},
        limit=2,
    )
    result = lead_search.execute_lead_search_query(tenant, query)
    assert result["count"] == 2
    assert all("latest_message" not in rec for rec in result["results"])
    assert result["query"]["limit"] == 2


def _auth_headers(client: TestClient) -> dict:
    resp = client.post(
        "/auth/token",
        json={"org_id": "org1", "branch_id": "branch1", "user_id": "agent1"},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_api_manual_json_query(api_client):
    client, db, _calendar = api_client
    db["leads"].insert_one(
        {
            "org_id": "org1",
            "branch_id": "branch1",
            "user_id": "agent1",
            "intent": "purchase",
            "status": "contacted",
        }
    )

    manual_query = json.dumps(
        {
            "collection": "leads",
            "filter": {"status": "contacted"},
            "projection": {"intent": 1, "status": 1},
            "limit": 5,
        }
    )

    response = client.get(
        "/api/leads/search",
        params={"q": manual_query},
        headers=_auth_headers(client),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["status"] == "contacted"
    assert payload["query"]["filter"]["status"] == "contacted"



def test_generate_query_handles_code_fence(monkeypatch, tenant):
    lead_search._lead_search_llm.cache_clear()
    llm = DummyLLM()
    llm.payload = "```json\n{\"collection\": \"leads\", \"filter\": {\"status\": \"open\"}, \"limit\": 5}\n```"
    monkeypatch.setattr(lead_search, "_lead_search_llm", lambda: llm)

    query = lead_search.generate_lead_search_query(tenant, "show open leads")
    assert query.collection == "leads"
    assert query.filter["org_id"] == "org1"
    assert query.limit == 5


def test_friendly_summary_handles_results():
    from frontend.streamlit_app import _friendly_lead_summary

    result = {
        "count": 2,
        "query": {"filter": {"status": "open", "intent": "book_appointment"}},
        "results": [
            {"conversation_id": "c1", "intent": "book_appointment", "status": "open", "confidence": 0.8},
            {"conversation_id": "c2", "intent": "book_appointment", "status": "open", "confidence": 0.7},
        ],
    }
    text = _friendly_lead_summary(result)
    assert "2 lead(s)" in text
    assert "c1" in text


def test_summarize_lead_results_uses_llm(monkeypatch):
    lead_search._lead_summary_llm.cache_clear()
    llm = DummyLLM()
    llm.payload = "Gemini summary text"
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(lead_search, "_lead_summary_llm", lambda: llm)

    records = [
        {
            "conversation_id": "conv-1",
            "intent": "book_appointment",
            "status": "open",
            "confidence": 0.82,
        },
        {
            "conversation_id": "conv-2",
            "intent": "book_appointment",
            "status": "open",
            "confidence": 0.74,
            "appointment_event_id": "evt-123",
        },
    ]

    summary = lead_search.summarize_lead_results("show open leads needing booking", records)
    assert summary == "Gemini summary text"


def test_summarize_lead_results_handles_structured_llm_content(monkeypatch):
    lead_search._lead_summary_llm.cache_clear()

    class ContentPart:
        def __init__(self, text):
            self.text = text

    class Content:
        def __init__(self, parts):
            self.parts = parts

    class StructuredLLM:
        def invoke(self, *_args, **_kwargs):
            return type("Resp", (), {"content": [Content([ContentPart("Detailed lead briefing.")])]} )()

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(lead_search, "_lead_summary_llm", lambda: StructuredLLM())

    records = [
        {"conversation_id": "conv-5", "intent": "purchase", "status": "open"},
    ]

    summary = lead_search.summarize_lead_results("show purchase leads", records)
    assert summary == "Detailed lead briefing."


def test_summarize_lead_results_reads_additional_kwargs(monkeypatch):
    lead_search._lead_summary_llm.cache_clear()

    class Response:
        def __init__(self):
            self.content = ""
            self.additional_kwargs = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Candidate-driven summary text."},
                            ]
                        },
                        "finish_reason": "MAX_TOKENS",
                        "safety_ratings": [],
                    }
                ],
                "usage_metadata": {"output_tokens": 0},
            }
            self.response_metadata = {"token_usage": {"output_tokens": 0}}

    class CandidateLLM:
        def invoke(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(lead_search, "_lead_summary_llm", lambda: CandidateLLM())

    records = [
        {"conversation_id": "conv-6", "intent": "book_appointment", "status": "open"},
    ]

    summary = lead_search.summarize_lead_results("show open leads", records)
    assert summary == "Candidate-driven summary text."


def test_summarize_lead_results_fallback_on_llm_error(monkeypatch):
    lead_search._lead_summary_llm.cache_clear()

    class BrokenLLM:
        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("LLM offline")

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(lead_search, "_lead_summary_llm", lambda: BrokenLLM())

    records = [
        {
            "conversation_id": "conv-3",
            "intent": "book_appointment",
            "status": "open",
            "confidence": 0.81,
        },
        {
            "conversation_id": "conv-4",
            "intent": "purchase",
            "status": "closed",
            "confidence": 0.6,
        },
    ]

    summary = lead_search.summarize_lead_results("show recent leads", records)
    assert summary.startswith("2 lead(s) matched the query.")
    assert "Intent mix" in summary
    assert "Examples:" in summary

