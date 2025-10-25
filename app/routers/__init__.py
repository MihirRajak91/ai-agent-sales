"""API routers exposed by the FastAPI application."""

from .auth import router as auth_router
from .appointments import router as appointments_router
from .chat import router as chat_router
from .google_oauth import router as google_oauth_router
from .health import router as health_router
from .ingest import router as ingest_router
from .leads import router as leads_router

__all__ = [
    "auth_router",
    "appointments_router",
    "chat_router",
    "google_oauth_router",
    "health_router",
    "ingest_router",
    "leads_router",
]
