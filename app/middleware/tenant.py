from typing import Callable

import jwt
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.auth import decode_access_token


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Decode bearer tokens (when present) and attach tenant claims to request.state.
    Endpoints that require authentication should still declare the dependency so
    explicit 401s are returned when the header is missing.
    """

    def __init__(self, app, *, exempt_paths: tuple[str, ...] | None = None):
        super().__init__(app)
        self.exempt_paths = exempt_paths or ()

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]):
        if self.exempt_paths and request.url.path.startswith(self.exempt_paths):
            return await call_next(request)

        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not token:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid authorization scheme"},
                )

            try:
                claims = decode_access_token(token)
            except jwt.PyJWTError:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or expired token"},
                )

            request.state.tenant_claims = claims

        return await call_next(request)
