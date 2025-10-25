from __future__ import annotations

from typing import Any, Dict, List
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ========= App =========
    APP_ENV: str = Field("development", description="development|staging|production")
    LOG_LEVEL: str = Field("INFO", description="DEBUG|INFO|WARNING|ERROR")
    DEFAULT_TIMEZONE: str = Field("Asia/Kathmandu")
    PRINT_SETTINGS_ON_STARTUP: bool = Field(False)

    # ========= Auth (JWT) =========
    JWT_SECRET: str = Field(..., description="HMAC secret for dev; use KMS in prod")
    JWT_ALG: str = Field("HS256")
    JWT_TTL_SECONDS: int = Field(3600)
    JWT_ISS: str = Field("auth")
    JWT_AUD: str = Field("api")

    # ========= MongoDB =========
    MONGODB_URI: str = Field("mongodb://localhost:27017")
    MONGODB_DB_NAME: str = Field("multi_tenant_sales")

    # ========= Gemini (Developer API) =========
    GEMINI_API_KEY: str = Field(..., description="Gemini/Google API key (Developer API)")
    LLM_MODEL: str = Field("gemini-2.5-flash")
    EMBED_MODEL: str = Field("text-embedding-004")
    EMBED_OUTPUT_DIM: int = Field(768)

    # ========= Pinecone =========
    PINECONE_API_KEY: str = Field(..., description="Pinecone API key")
    PINECONE_INDEX: str = Field("kb-embeddings")

    # ========= Google Calendar (OAuth) =========
    GOOGLE_CALENDAR_AUTH_MODE: str = Field("oauth", description="oauth only for this task")
    GOOGLE_OAUTH_CLIENT_ID: str = Field(...)
    GOOGLE_OAUTH_CLIENT_SECRET: str = Field(...)
    GOOGLE_OAUTH_REDIRECT_URI: str = Field(...)

    # ========= Email Provider =========
    EMAIL_PROVIDER: str = Field("sendgrid", description="sendgrid|ses|smtp")
    EMAIL_FROM_NAME: str = Field("Sales Bot")
    EMAIL_FROM_ADDRESS: str = Field("bot@example.com")
    SENDGRID_API_KEY: str = Field("", description="Required if EMAIL_PROVIDER=sendgrid")
    SMTP_HOST: str = Field("smtp.gmail.com", description="Required if EMAIL_PROVIDER=smtp")
    SMTP_PORT: int = Field(587, description="Required if EMAIL_PROVIDER=smtp")
    SMTP_USERNAME: str = Field("", description="Required if EMAIL_PROVIDER=smtp")
    SMTP_PASSWORD: str = Field("", description="Required if EMAIL_PROVIDER=smtp")
    SMTP_USE_TLS: bool = Field(True, description="Use STARTTLS when EMAIL_PROVIDER=smtp")

    # ========= Google Service Account (optional) =========
    GOOGLE_SERVICE_ACCOUNT_TYPE: str = Field("", description="Service account type")
    GOOGLE_SERVICE_ACCOUNT_PROJECT_ID: str = Field("", description="Service account project id")
    GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID: str = Field("", description="Service account private key id")
    GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY: str = Field("", description="Service account private key")
    GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL: str = Field("", description="Service account client email")
    GOOGLE_SERVICE_ACCOUNT_CLIENT_ID: str = Field("", description="Service account client id")
    GOOGLE_SERVICE_ACCOUNT_AUTH_URI: str = Field("", description="Service account auth uri")
    GOOGLE_SERVICE_ACCOUNT_TOKEN_URI: str = Field("", description="Service account token uri")
    GOOGLE_SERVICE_ACCOUNT_AUTH_PROVIDER_X509_CERT_URL: str = Field("", description="Service account auth provider cert url")
    GOOGLE_SERVICE_ACCOUNT_CLIENT_X509_CERT_URL: str = Field("", description="Service account client cert url")
    GOOGLE_SERVICE_ACCOUNT_UNIVERSE_DOMAIN: str = Field("", description="Service account universe domain")

    # ========= Frontend =========
    FRONTEND_URL: str = Field("http://localhost:8001")

    # ========= Dev Convenience =========
    DEV_TOKEN_ENABLED: bool = Field(
        True,
        description="When true and APP_ENV=development, allow issuing a default dev JWT via GET /auth/token/dev",
    )
    DEV_TOKEN_ORG_ID: str = Field("demo_org")
    DEV_TOKEN_BRANCH_ID: str = Field("demo_branch")
    DEV_TOKEN_USER_ID: str = Field("demo_user")
    DEV_TOKEN_NAME: str = Field("Demo User")
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    
settings = Settings()
