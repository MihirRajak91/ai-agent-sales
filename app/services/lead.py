from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app import deps
from app.models.auth import TenantClaims
from app.models.intent import IntentClassification, IntentLabel
from app.models.lead import Lead, LeadStatus


def _collection():
    db = deps.get_mongo_database()
    return db["leads"]


def record_lead(
    tenant: TenantClaims,
    *,
    conversation_id: str,
    intent: IntentClassification,
    latest_message: str,
    notes: Optional[str] = None,
) -> Lead:
    """
    Upsert a lead for the tenant and conversation when intent indicates follow-up.
    """
    if intent.label == IntentLabel.NONE:
        raise ValueError("Cannot record a lead with neutral intent")

    collection = _collection()
    now = datetime.now(timezone.utc)

    update = {
        "$set": {
            "conversation_id": conversation_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
            "intent": intent.label.value,
            "confidence": intent.confidence,
            "latest_message": latest_message,
            "updated_at": now,
        },
        "$setOnInsert": {
            "source": "chat",
            "created_at": now,
        },
    }
    update["$set"]["status"] = LeadStatus.OPEN.value

    if intent.rationale:
        update["$set"]["rationale"] = intent.rationale
    if notes:
        update["$set"]["notes"] = notes

    result = collection.find_one_and_update(
        {
            "conversation_id": conversation_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
        },
        update,
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    if result is None:
        raise RuntimeError("Failed to create or update lead")

    return _mongo_to_lead(result)


def list_leads(tenant: TenantClaims) -> List[Lead]:
    cursor = (
        _collection()
        .find(
            {
                "org_id": tenant.org_id,
                "branch_id": tenant.branch_id,
            }
        )
        .sort(
            [
                ("updated_at", -1),
                ("created_at", -1),
            ]
        )
    )
    return [_mongo_to_lead(doc) for doc in cursor]


def get_lead_by_conversation(
    tenant: TenantClaims,
    conversation_id: str,
) -> Optional[Lead]:
    doc = _collection().find_one(
        {
            "conversation_id": conversation_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
        },
        sort=[("updated_at", -1)],
    )
    if doc is None:
        return None
    return _mongo_to_lead(doc)


def attach_appointment(
    tenant: TenantClaims,
    *,
    lead_id: str,
    event_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    calendar_id: Optional[str] = "primary",
    status: LeadStatus = LeadStatus.CONTACTED,
    event_link: Optional[str] = None,
) -> Lead:
    collection = _collection()
    now = datetime.now(timezone.utc)

    try:
        lead_object_id = ObjectId(lead_id)
    except InvalidId as exc:
        raise ValueError("Invalid lead_id") from exc

    result = collection.find_one_and_update(
        {
            "_id": lead_object_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
        },
        {
            "$set": {
                "appointment_event_id": event_id,
                "appointment_start": start,
                "appointment_end": end,
                "calendar_id": calendar_id,
                "status": status.value,
                "appointment_html_link": event_link,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if result is None:
        raise ValueError("Lead not found for tenant")

    return _mongo_to_lead(result)


def clear_appointment(
    tenant: TenantClaims,
    *,
    lead_id: str,
    status: LeadStatus = LeadStatus.OPEN,
) -> Lead:
    collection = _collection()
    now = datetime.now(timezone.utc)

    try:
        lead_object_id = ObjectId(lead_id)
    except InvalidId as exc:
        raise ValueError("Invalid lead_id") from exc

    result = collection.find_one_and_update(
        {
            "_id": lead_object_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
        },
        {
            "$set": {
                "appointment_event_id": None,
                "appointment_start": None,
                "appointment_end": None,
                "calendar_id": None,
                "status": status.value,
                "appointment_html_link": None,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if result is None:
        raise ValueError("Lead not found for tenant")

    return _mongo_to_lead(result)


def _mongo_to_lead(doc) -> Lead:
    return Lead(
        id=str(doc.get("_id", "")),
        org_id=doc["org_id"],
        branch_id=doc["branch_id"],
        user_id=doc["user_id"],
        conversation_id=doc["conversation_id"],
        intent=doc["intent"],
        latest_message=doc.get("latest_message", ""),
        status=LeadStatus(doc.get("status", LeadStatus.OPEN.value)),
        source=doc.get("source", "chat"),
        created_at=doc.get("created_at", datetime.now(timezone.utc)),
        updated_at=doc.get("updated_at", datetime.now(timezone.utc)),
        notes=doc.get("notes"),
        confidence=doc.get("confidence"),
        rationale=doc.get("rationale"),
        appointment_event_id=doc.get("appointment_event_id"),
        appointment_start=doc.get("appointment_start"),
        appointment_end=doc.get("appointment_end"),
        calendar_id=doc.get("calendar_id"),
        appointment_html_link=doc.get("appointment_html_link"),
    )
