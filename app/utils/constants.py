from __future__ import annotations

from typing import Final

# Application metadata
FASTAPI_APP_TITLE: Final[str] = "Multi-tenant Conversational Sales Agent"
FASTAPI_APP_VERSION: Final[str] = "0.1.0"
FASTAPI_DOCS_URL: Final[str] = "/docs"
FASTAPI_REDOC_URL: Final[str | None] = None

# Startup logging
STARTUP_LOGGER_NAME: Final[str] = "startup"
STARTUP_LOG_MESSAGE: Final[str] = "FastAPI app started"
STARTUP_RUNTIME_LOG_MESSAGE: Final[str] = "Runtime configuration"
STARTUP_HEALTH_CHECKERS: Final[dict[str, str]] = {
    "mongo": "health_check_mongo",
    "pinecone": "health_check_pinecone",
    "gemini": "health_check_gemini",
}

# Retrieval service
DEFAULT_RETRIEVAL_TOP_K: Final[int] = 6
RETRIEVAL_TASK_TYPE: Final[str] = "RETRIEVAL_QUERY"
GEMINI_EMPTY_EMBEDDINGS_ERROR: Final[str] = "Gemini returned empty embeddings response"

# Chat service
CHAT_LOGGER_NAME: Final[str] = "chat"
DEFAULT_CHAT_HISTORY_LIMIT: Final[int] = 6
CHAT_SYSTEM_PROMPT: Final[str] = """You are a helpful sales assistant for internal teams.
Answer the user's question using ONLY the provided knowledge base context and prior conversation.
If the context does not contain the answer, reply with a brief apology and ask for more information.
Reference source numbers in parentheses (e.g., [source 1]) when quoting from specific chunks."""
CHAT_MODEL_TEMPERATURE: Final[float] = 0.3
CHAT_MODEL_MAX_OUTPUT_TOKENS: Final[int] = 512
CHAT_NO_CONTEXT_MESSAGE: Final[str] = "No relevant knowledge base entries were retrieved for this question."
CHAT_CONTEXT_SOURCE_FALLBACK: Final[str] = "knowledge base"
CHAT_SOURCE_TEMPLATE: Final[str] = "[source {index}] (page {page} from {source})\n{content}"
CHAT_INTENT_DETECTED_MESSAGE: Final[str] = "Intent detected"
CHAT_SCHEDULING_FAILURE_MESSAGE: Final[str] = "Scheduling handling failed"
CHAT_LEAD_RECORD_FAILURE_MESSAGE: Final[str] = "Failed to record lead"
CHAT_BOOKING_KEYWORDS: Final[tuple[str, ...]] = ("book", "schedule", "demo", "meeting", "appointment")
CHAT_PURCHASE_KEYWORDS: Final[tuple[str, ...]] = ("buy", "purchase", "pricing", "quote", "license")
CHAT_INTENT_HEURISTIC_CONFIDENCE: Final[float] = 0.6
CHAT_BOOKING_HEURISTIC_RATIONALE: Final[str] = "Keyword heuristic detected booking intent."
CHAT_PURCHASE_HEURISTIC_RATIONALE: Final[str] = "Keyword heuristic detected purchase intent."
CHAT_MESSAGE_ROLE_ASSISTANT: Final[str] = "assistant"
CHAT_MESSAGE_ROLE_USER: Final[str] = "user"
CHAT_PROMPT_HISTORY_VARIABLE: Final[str] = "history"
CHAT_PROMPT_HUMAN_TEMPLATE: Final[str] = "{input}"
CHAT_PROMPT_INPUT_KEY: Final[str] = "input"
CHAT_PROMPT_USER_QUESTION_TEMPLATE: Final[str] = "User question: {question}"
CHAT_PROMPT_CONTEXT_HEADER: Final[str] = "Knowledge base context:\n{context}"
CHAT_PROMPT_INSTRUCTIONS: Final[str] = (
    "Provide a concise answer grounded in the context above.\n"
    "If you mention a source, cite it as [source number]."
)

# User service
PASSWORD_HASH_SCHEMES: Final[tuple[str, ...]] = ("bcrypt",)
PASSWORD_HASH_DEPRECATED: Final[str] = "auto"
USER_COLLECTION_NAME: Final[str] = "users"
USER_EMAIL_FIELD: Final[str] = "email"
USER_HASHED_PASSWORD_FIELD: Final[str] = "hashed_password"
USER_ORG_ID_FIELD: Final[str] = "org_id"
USER_BRANCH_ID_FIELD: Final[str] = "branch_id"
USER_NAME_FIELD: Final[str] = "name"
USER_CREATED_AT_FIELD: Final[str] = "created_at"
USER_UPDATED_AT_FIELD: Final[str] = "updated_at"
DUPLICATE_USER_EMAIL_ERROR: Final[str] = "An account with this email already exists."
