from fastapi import FastAPI

from app.logging_config import get_logger, setup_logging
from app.middleware import TenantContextMiddleware
from app.routers import (
    appointments_router,
    auth_router,
    chat_router,
    google_oauth_router,
    health_router,
    ingest_router,
    leads_router,
)
from app.settings import settings
from app import deps


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    setup_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="Multi-tenant Conversational Sales Agent",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    app.add_middleware(TenantContextMiddleware)

    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(ingest_router)
    app.include_router(leads_router)
    app.include_router(appointments_router)
    app.include_router(google_oauth_router)
    app.include_router(health_router)

    logger = get_logger("startup")

    @app.on_event("startup")
    async def _log_startup() -> None:
        logger.info("FastAPI app started", extra={"env": settings.APP_ENV})

        if settings.PRINT_SETTINGS_ON_STARTUP:
            logger.info(
                "Runtime configuration",
                extra={
                    "env": settings.APP_ENV,
                    "log_level": settings.LOG_LEVEL,
                    "mongodb_db": settings.MONGODB_DB_NAME,
                    "pinecone_index": settings.PINECONE_INDEX,
                    "frontend_url": settings.FRONTEND_URL,
                },
            )

        _run_startup_checks(logger)

    return app


app = create_app()


def _run_startup_checks(logger) -> None:
    checks = {
        "mongo": deps.health_check_mongo,
        "pinecone": deps.health_check_pinecone,
        "gemini": deps.health_check_gemini,
    }

    for name, checker in checks.items():
        healthy, message = checker()
        log_extra = {"service": name}
        if healthy:
            logger.info(message, extra=log_extra)
        else:
            logger.warning(message, extra=log_extra)
