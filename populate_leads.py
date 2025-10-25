from pymongo import MongoClient
from datetime import datetime, timedelta

client = MongoClient("mongodb://localhost:27017")
db = client["multi_tenant_sales"]
leads = db["leads"]

leads.delete_many({"org_id": "org1", "branch_id": "branch1"})

now = datetime(2025, 10, 25, 12, 0)

seed_data = [
    {
        "org_id": "org1",
        "branch_id": "branch1",
        "user_id": "agent1",
        "intent": "book_appointment",
        "confidence": 0.92,
        "status": "open",
        "latest_message": "Can we book a product demo next Tuesday at 3pm?",
        "created_at": now.isoformat() + "Z",
        "updated_at": (now + timedelta(hours=1)).isoformat() + "Z",
        "appointment_event_id": None,
        "appointment_start": None,
        "appointment_end": None,
        "calendar_id": None,
        "conversation_id": "conv-1001",
        "rationale": "Explicit request to schedule a demo.",
    },
    {
        "org_id": "org1",
        "branch_id": "branch1",
        "user_id": "agent2",
        "intent": "purchase",
        "confidence": 0.78,
        "status": "contacted",
        "latest_message": "We need enterprise pricing for 50 seats.",
        "created_at": (now - timedelta(days=3)).isoformat() + "Z",
        "updated_at": (now - timedelta(days=1)).isoformat() + "Z",
        "appointment_event_id": "evt_enterprise_demo",
        "appointment_start": (now + timedelta(days=2)).isoformat() + "Z",
        "appointment_end": (now + timedelta(days=2, hours=1)).isoformat() + "Z",
        "calendar_id": "primary",
        "conversation_id": "conv-2002",
        "rationale": "Customer asked about pricing tiers.",
    },
    {
        "org_id": "org1",
        "branch_id": "branch1",
        "user_id": "agent3",
        "intent": "book_appointment",
        "confidence": 0.65,
        "status": "open",
        "latest_message": "Need a quick onboarding walkthrough",
        "created_at": (now - timedelta(days=2)).isoformat() + "Z",
        "updated_at": (now - timedelta(days=2, hours=-4)).isoformat() + "Z",
        "appointment_event_id": None,
        "appointment_start": None,
        "appointment_end": None,
        "calendar_id": None,
        "conversation_id": "conv-3003",
        "rationale": "User asked for walkthrough timing.",
    },
    {
        "org_id": "org1",
        "branch_id": "branch1",
        "user_id": "agent4",
        "intent": "purchase",
        "confidence": 0.55,
        "status": "closed",
        "latest_message": "Thanks, we went with another vendor.",
        "created_at": (now - timedelta(days=7)).isoformat() + "Z",
        "updated_at": (now - timedelta(days=5)).isoformat() + "Z",
        "appointment_event_id": None,
        "appointment_start": None,
        "appointment_end": None,
        "calendar_id": None,
        "conversation_id": "conv-4004",
        "rationale": "Lead closed lost.",
    },
    {
        "org_id": "org1",
        "branch_id": "branch1",
        "user_id": "agent5",
        "intent": "book_appointment",
        "confidence": 0.83,
        "status": "contacted",
        "latest_message": "Let's reschedule the demo to Friday morning.",
        "created_at": (now - timedelta(days=1)).isoformat() + "Z",
        "updated_at": now.isoformat() + "Z",
        "appointment_event_id": "evt_reschedule_demo",
        "appointment_start": (now + timedelta(days=1)).isoformat() + "Z",
        "appointment_end": (now + timedelta(days=1, hours=1)).isoformat() + "Z",
        "calendar_id": "primary",
        "conversation_id": "conv-5005",
        "rationale": "Customer requested reschedule.",
    },
]

leads.insert_many(seed_data)
print(f"Inserted {len(seed_data)} leads for org1/branch1.")
