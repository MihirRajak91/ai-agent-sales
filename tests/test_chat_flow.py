import pytest


def _auth_headers(client):
    token_resp = client.post(
        "/auth/token",
        json={"org_id": "org1", "branch_id": "branch1", "user_id": "agent1"},
    )
    token_resp.raise_for_status()
    token = token_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_booking_request_prompts_for_time(api_client, monkeypatch):
    monkeypatch.setattr(
        "app.services.scheduling._extract_datetimes",
        lambda _message: (None, None),
    )

    client, db, _ = api_client
    headers = _auth_headers(client)

    response = client.post(
        "/api/chat",
        json={"conversation_id": "conv-demo", "query": "Can I book a demo sometime?"},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["intent"]["label"] == "book_appointment"
    assert "Please share a specific date and time" in payload["answer"]
    assert payload["sources"] == []
    assert payload["lead_id"] is not None

    lead_doc = db["leads"].find_one({"conversation_id": "conv-demo"})
    assert lead_doc is not None
    assert lead_doc["intent"] == "book_appointment"
    assert lead_doc.get("appointment_event_id") is None


def test_booking_with_time_creates_event(api_client):
    client, db, calendar_events = api_client
    headers = _auth_headers(client)

    # first message to create lead
    client.post(
        "/api/chat",
        json={"conversation_id": "conv-resched", "query": "Can I book a demo sometime?"},
        headers=headers,
    )

    response = client.post(
        "/api/chat",
        json={
            "conversation_id": "conv-resched",
            "query": "Schedule it for May 6 at 10:00 AM PST",
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert "Demo scheduled" in payload["answer"]
    assert payload["lead_id"] is not None

    lead_doc = db["leads"].find_one({"conversation_id": "conv-resched"})
    assert lead_doc is not None
    assert lead_doc.get("appointment_event_id") in calendar_events


def test_informational_query_uses_llm(api_client):
    client, _db, _events = api_client
    headers = _auth_headers(client)

    response = client.post(
        "/api/chat",
        json={"conversation_id": "conv-info", "query": "Tell me about NexaFlow."},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["label"] == "none"
    assert payload["answer"] == "Stubbed assistant response."
    assert payload["sources"] == []
