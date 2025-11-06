import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from pymongo import MongoClient
from pinecone import Pinecone
from pinecone.exceptions import NotFoundException
from google import genai

from app.models.auth import TenantClaims
from app.services.auth import decode_access_token
from app.config.settings import settings

TESTING = os.getenv("TESTING") == "1"

mongo_client = None
mongo_db = None
_pinecone_index: Optional[object] = None
gemini_client = None

if not TESTING:
    # Mongo
    mongo_client = MongoClient(settings.MONGODB_URI)
    mongo_db = mongo_client[settings.MONGODB_DB_NAME]

    # Pinecone
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    try:
        _pinecone_index = pc.Index(settings.PINECONE_INDEX)
    except NotFoundException:
        _pinecone_index = None

    # Gemini client (Developer API)
    gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)


def get_pinecone_index():
    if _pinecone_index is None:
        raise RuntimeError(
            f"Pinecone index '{settings.PINECONE_INDEX}' not found. "
            "Create it (dimension=768, metric=cosine) or update PINECONE_INDEX."
        )
    return _pinecone_index


def get_mongo_database():
    if mongo_db is None:
        raise RuntimeError("MongoDB client not initialised")
    return mongo_db


def get_gemini_client():
    if gemini_client is None:
        raise RuntimeError("Gemini client not initialised")
    return gemini_client


_MISSING = object()


def configure_test_dependencies(
    *,
    mongo_db_override=_MISSING,
    pinecone_index=_MISSING,
    gemini_client_override=_MISSING,
):
    """
    Allow tests to inject lightweight doubles for external services without
    touching the production initialization code path.
    """

    global mongo_db, _pinecone_index, gemini_client

    if mongo_db_override is not _MISSING:
        mongo_db = mongo_db_override

    if pinecone_index is not _MISSING:
        _pinecone_index = pinecone_index

    if gemini_client_override is not _MISSING:
        gemini_client = gemini_client_override


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_tenant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TenantClaims:
    cached_claims = getattr(request.state, "tenant_claims", None)
    if cached_claims:
        return cached_claims

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    token = credentials.credentials

    try:
        claims = decode_access_token(token)
    except (jwt.PyJWTError, ValidationError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    request.state.tenant_claims = claims
    return claims


def health_check_mongo() -> tuple[bool, str]:
    if mongo_db is None:
        return False, "MongoDB client not initialised"

    try:
        mongo_db.command("ping")
        return True, "MongoDB reachable"
    except Exception as exc:  # pragma: no cover - diagnostics
        return False, f"MongoDB unavailable: {exc}"


def health_check_pinecone() -> tuple[bool, str]:
    if _pinecone_index is None:
        return False, f"Pinecone index '{settings.PINECONE_INDEX}' not initialised"

    try:
        _pinecone_index.describe_index_stats()
        return True, "Pinecone reachable"
    except Exception as exc:  # pragma: no cover - diagnostics
        return False, f"Pinecone unavailable: {exc}"


def health_check_gemini() -> tuple[bool, str]:
    if gemini_client is None:
        return False, "Gemini client not initialised"

    try:
        models = gemini_client.models.list()
        iterable = models if hasattr(models, "__iter__") else getattr(models, "models", [])
        iterator = iter(iterable)
        try:
            first = next(iterator)
            description = getattr(first, "name", None) or "model available"
        except StopIteration:
            description = "no models returned but service reachable"
        return True, f"Gemini reachable ({description})"
    except Exception as exc:  # pragma: no cover - diagnostics
        return False, f"Gemini unavailable: {exc}"
