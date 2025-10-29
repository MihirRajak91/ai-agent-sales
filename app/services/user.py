from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from passlib.context import CryptContext
from pymongo.collection import Collection

from app import deps
from app.models.user import User, UserCreate
from app.utils.constants import (
    DUPLICATE_USER_EMAIL_ERROR,
    PASSWORD_HASH_DEPRECATED,
    PASSWORD_HASH_SCHEMES,
    USER_BRANCH_ID_FIELD,
    USER_COLLECTION_NAME,
    USER_CREATED_AT_FIELD,
    USER_EMAIL_FIELD,
    USER_HASHED_PASSWORD_FIELD,
    USER_NAME_FIELD,
    USER_ORG_ID_FIELD,
    USER_UPDATED_AT_FIELD,
)


pwd_context = CryptContext(schemes=list(PASSWORD_HASH_SCHEMES), deprecated=PASSWORD_HASH_DEPRECATED)


def _collection() -> Collection:
    collection = deps.get_mongo_database()[USER_COLLECTION_NAME]
    # Ensure email uniqueness to prevent duplicate registrations.
    collection.create_index(USER_EMAIL_FIELD, unique=True)
    return collection


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def get_user_by_email(email: str) -> Optional[User]:
    normalized_email = email.lower()
    doc = _collection().find_one({USER_EMAIL_FIELD: normalized_email})
    if not doc:
        return None
    return _doc_to_user(doc)


def create_user(payload: UserCreate) -> User:
    existing = get_user_by_email(payload.email)
    if existing:
        raise ValueError(DUPLICATE_USER_EMAIL_ERROR)

    now = datetime.now(timezone.utc)
    doc = {
        USER_EMAIL_FIELD: payload.email.lower(),
        USER_HASHED_PASSWORD_FIELD: hash_password(payload.password),
        USER_ORG_ID_FIELD: payload.org_id,
        USER_BRANCH_ID_FIELD: payload.branch_id,
        USER_NAME_FIELD: payload.name,
        USER_CREATED_AT_FIELD: now,
        USER_UPDATED_AT_FIELD: now,
    }
    result = _collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_user(doc)


def authenticate_user(email: str, password: str) -> Optional[User]:
    doc = _collection().find_one({USER_EMAIL_FIELD: email.lower()})
    if not doc:
        return None

    hashed_password = doc.get(USER_HASHED_PASSWORD_FIELD)
    if not hashed_password or not verify_password(password, hashed_password):
        return None

    return _doc_to_user(doc)


def _doc_to_user(doc: dict) -> User:
    return User(
        id=str(doc.get("_id")),
        email=doc.get(USER_EMAIL_FIELD),
        org_id=doc.get(USER_ORG_ID_FIELD),
        branch_id=doc.get(USER_BRANCH_ID_FIELD),
        name=doc.get(USER_NAME_FIELD),
        created_at=doc.get(USER_CREATED_AT_FIELD),
        updated_at=doc.get(USER_UPDATED_AT_FIELD, doc.get(USER_CREATED_AT_FIELD)),
    )
