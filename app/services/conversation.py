from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from app import deps
from app.models.auth import TenantClaims

MessageDict = dict


def _collection():
    db = deps.get_mongo_database()
    return db["conversations"]


def ensure_conversation(
    tenant: TenantClaims,
    conversation_id: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    """
    Retrieve or create a conversation record for the tenant.
    """
    collection = _collection()
    filter_query = {
        "_id": conversation_id,
        "org_id": tenant.org_id,
        "branch_id": tenant.branch_id,
        "user_id": tenant.user_id,
    }

    if conversation_id:
        existing = collection.find_one({"_id": conversation_id})
        if existing:
            if (
                existing.get("org_id") != tenant.org_id
                or existing.get("branch_id") != tenant.branch_id
                or existing.get("user_id") != tenant.user_id
            ):
                raise ValueError("Conversation belongs to a different tenant")
            return conversation_id

    if conversation_id is None:
        conversation_id = str(uuid4())
        filter_query["_id"] = conversation_id

    now = datetime.now(timezone.utc)
    conversation_doc = {
        "_id": conversation_id,
        "org_id": tenant.org_id,
        "branch_id": tenant.branch_id,
        "user_id": tenant.user_id,
        "title": title,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }
    collection.insert_one(conversation_doc)
    return conversation_id


def get_recent_messages(
    tenant: TenantClaims, conversation_id: str, limit: int = 6
) -> List[MessageDict]:
    """
    Return the most recent messages for the tenant conversation (ascending order).
    """
    collection = _collection()
    conversation = collection.find_one(
        {
            "_id": conversation_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
        },
        {
            "messages": {"$slice": -limit},
        },
    )
    if not conversation:
        raise ValueError("Conversation not found for tenant")

    return conversation.get("messages", [])


def append_messages(
    tenant: TenantClaims, conversation_id: str, messages: List[MessageDict]
) -> None:
    """
    Append messages to the conversation log and update timestamps.
    """
    if not messages:
        return

    collection = _collection()
    now = datetime.now(timezone.utc)
    result = collection.update_one(
        {
            "_id": conversation_id,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
        },
        {
            "$push": {"messages": {"$each": messages}},
            "$set": {"updated_at": now},
        },
    )

    if result.matched_count == 0:
        raise ValueError("Conversation not found for tenant")
