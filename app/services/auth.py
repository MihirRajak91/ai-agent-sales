from datetime import datetime, timedelta, timezone

import jwt

from app.models.auth import TenantClaims
from app.config.settings import settings


def create_access_token(
    claims: TenantClaims, expires_delta: timedelta | None = None
) -> str:
    """
    Generate a signed JWT embedding tenant claims and standard metadata.
    """
    now = datetime.now(timezone.utc)
    lifetime = expires_delta or timedelta(seconds=settings.JWT_TTL_SECONDS)
    expire_at = now + lifetime

    payload = {
        "iss": settings.JWT_ISS,
        "aud": settings.JWT_AUD,
        "iat": int(now.timestamp()),
        "exp": int(expire_at.timestamp()),
        "org_id": claims.org_id,
        "branch_id": claims.branch_id,
        "user_id": claims.user_id,
    }

    if claims.name:
        payload["name"] = claims.name

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_access_token(token: str) -> TenantClaims:
    """
    Decode and validate a JWT, returning the tenant claims payload.
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALG],
        audience=settings.JWT_AUD,
        issuer=settings.JWT_ISS,
    )

    return TenantClaims.model_validate(
        {
            "org_id": payload["org_id"],
            "branch_id": payload["branch_id"],
            "user_id": payload["user_id"],
            "name": payload.get("name"),
        }
    )
