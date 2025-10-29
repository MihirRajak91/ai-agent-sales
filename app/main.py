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
from app.utils.constants import (
    FASTAPI_APP_TITLE,
    FASTAPI_APP_VERSION,
    FASTAPI_DOCS_URL,
    FASTAPI_REDOC_URL,
    STARTUP_HEALTH_CHECKERS,
    STARTUP_LOGGER_NAME,
    STARTUP_LOG_MESSAGE,
    STARTUP_RUNTIME_LOG_MESSAGE,
)


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    setup_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title=FASTAPI_APP_TITLE,
        version=FASTAPI_APP_VERSION,
        docs_url=FASTAPI_DOCS_URL,
        redoc_url=FASTAPI_REDOC_URL,
    )

    app.add_middleware(TenantContextMiddleware)

    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(ingest_router)
    app.include_router(leads_router)
    app.include_router(appointments_router)
    app.include_router(google_oauth_router)
    app.include_router(health_router)

    logger = get_logger(STARTUP_LOGGER_NAME)

    @app.on_event("startup")
    async def _log_startup() -> None:
        logger.info(STARTUP_LOG_MESSAGE, extra={"env": settings.APP_ENV})

        if settings.PRINT_SETTINGS_ON_STARTUP:
            logger.info(
                STARTUP_RUNTIME_LOG_MESSAGE,
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
        name: getattr(deps, checker_name)
        for name, checker_name in STARTUP_HEALTH_CHECKERS.items()
    }

    for name, checker in checks.items():
        healthy, message = checker()
        log_extra = {"service": name}
        if healthy:
            logger.info(message, extra=log_extra)
        else:
            logger.warning(message, extra=log_extra)
