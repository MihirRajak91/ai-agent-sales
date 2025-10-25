import os
from typing import Dict, Tuple

import mongomock
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app import deps
from app.main import app
from app.models.appointment import (
    AppointmentRequest,
    AppointmentResponse,
    AppointmentUpdateRequest,
)
from app.settings import settings


class FakeEmbeddingResponse:
    def __init__(self):
        self.embeddings = [
            type("Embed", (), {"values": [0.0] * settings.EMBED_OUTPUT_DIM})()
        ]


class FakeGeminiModels:
    def embed_content(self, *args, **kwargs):
        return FakeEmbeddingResponse()


class FakeGeminiClient:
    def __init__(self):
        self.models = FakeGeminiModels()


class FakePineconeIndex:
    def __init__(self):
        self._store: Dict[str, list] = {}

    def upsert(self, vectors, namespace):
        self._store.setdefault(namespace, []).extend(vectors)

    def query(self, namespace, vector, top_k, include_metadata):
        matches = []
        for item in self._store.get(namespace, [])[:top_k]:
            matches.append(
                {
                    "id": item["id"],
                    "score": 0.5,
                    "metadata": item.get("metadata", {}),
                }
            )
        return {"matches": matches}

    def describe_index_stats(self):
        return {}


class FakeLLM:
    def invoke(self, *_args, **_kwargs):
        return AIMessage(content="Stubbed assistant response.")

    def __call__(self, *_args, **_kwargs):
        return self.invoke(*_args, **_kwargs)


@pytest.fixture(autouse=True)
def _testing_env(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    yield


@pytest.fixture
def api_client(monkeypatch) -> Tuple[TestClient, mongomock.database.Database, Dict[str, dict]]:
    mongo_client = mongomock.MongoClient()
    test_db = mongo_client["test_sales"]
    pinecone_index = FakePineconeIndex()
    gemini_client = FakeGeminiClient()

    deps.configure_test_dependencies(
        mongo_db_override=test_db,
        pinecone_index=pinecone_index,
        gemini_client_override=gemini_client,
    )

    calendar_events: Dict[str, dict] = {}

    def fake_create_appointment(_tenant, request: AppointmentRequest):
        event_id = f"evt_{len(calendar_events) + 1}"
        event = {
            "id": event_id,
            "htmlLink": f"https://calendar.example.com/{event_id}",
            "status": "confirmed",
            "summary": request.summary,
            "start": {"dateTime": request.start_time.isoformat()},
            "end": {"dateTime": request.end_time.isoformat()},
        }
        calendar_events[event_id] = event
        return AppointmentResponse(
            event_id=event_id,
            html_link=event["htmlLink"],
            status="confirmed",
            summary=request.summary,
            start=event["start"],
            end=event["end"],
            calendar_id=request.calendar_id or "primary",
        )

    def fake_update_appointment(_tenant, event_id: str, request: AppointmentUpdateRequest):
        event = calendar_events.get(event_id)
        if event is None:
            raise ValueError("Event not found")
        if request.start_time:
            event["start"] = {"dateTime": request.start_time.isoformat()}
        if request.end_time:
            event["end"] = {"dateTime": request.end_time.isoformat()}
        return AppointmentResponse(
            event_id=event_id,
            html_link=event["htmlLink"],
            status="confirmed",
            summary=request.summary or event.get("summary"),
            start=event["start"],
            end=event["end"],
            calendar_id=request.calendar_id or "primary",
        )

    def fake_delete_appointment(_tenant, event_id: str, calendar_id: str = "primary"):
        calendar_events.pop(event_id, None)

    monkeypatch.setattr("app.services.chat.ChatGoogleGenerativeAI", lambda *_, **__: FakeLLM())
    monkeypatch.setattr("app.services.scheduling.create_appointment", fake_create_appointment)
    monkeypatch.setattr("app.services.scheduling.update_appointment", fake_update_appointment)
    monkeypatch.setattr("app.services.scheduling.delete_appointment", fake_delete_appointment)

    client = TestClient(app)
    yield client, test_db, calendar_events
    mongo_client.drop_database("test_sales")
