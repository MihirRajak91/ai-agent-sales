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
CHAT_PURCHASE_SALES_TONE_INSTRUCTIONS: Final[str] = (
    "Adopt a consultative sales tone that highlights the product's value, clearly enumerate pricing or package "
    "options from the context, and guide the customer toward choosing an option."
)
CHAT_PURCHASE_CONFIRMATION_KEYWORDS: Final[tuple[str, ...]] = (
    "confirm purchase",
    "confirm my order",
    "purchase now",
    "buy now",
    "proceed with purchase",
    "ready to buy",
    "place the order",
    "let's buy",
    "i'll take it",
    "i am ready to buy",
)
CHAT_PURCHASE_INVOICE_SYSTEM_PROMPT: Final[str] = (
    "You are a billing assistant for a sales team. Based on the conversation history and knowledge base context, "
    "produce a detailed purchase confirmation that includes the selected products, unit pricing, subtotal, taxes "
    "if mentioned, and the grand total. Summaries must rely solely on the provided context and conversation."
)
CHAT_PURCHASE_INVOICE_USER_TEMPLATE: Final[str] = (
    "Conversation history summary:\n{conversation_summary}\n\n"
    "Knowledge base context:\n{context}\n\n"
    "Latest customer message:\n{user_message}\n\n"
    "{payment_instructions}\n"
    "Generate an invoice-style response that confirms the order details and next steps."
)
CHAT_PURCHASE_PAYMENT_INSTRUCTIONS: Final[str] = (
    "Include payment options for phone transfer and bank transfer with any account or contact details mentioned "
    "in the context. If no details are available, explicitly state that a representative will follow up with "
    "transfer details."
)
CHAT_PURCHASE_EMAIL_SENT_TEMPLATE: Final[str] = "I've emailed the invoice to {email} so you have a copy of the details."
CHAT_PURCHASE_EMAIL_MISSING_ADDRESS: Final[str] = (
    "I wasn't able to find an email address. Please share the best email so I can send the invoice."
)
CHAT_PURCHASE_EMAIL_FAILURE_MESSAGE: Final[str] = (
    "I couldn't send the invoice email just now. I'll try again shortly or a teammate will follow up."
)
CHAT_PURCHASE_EMAIL_SUBJECT: Final[str] = "Your purchase confirmation"

# Outreach / sales pitch
OUTREACH_EMAIL_SYSTEM_PROMPT: Final[str] = (
    "You are a sales specialist crafting follow-up emails for warm leads. "
    "Write in a concise, confident tone (under ~170 words), highlighting product value and actionable next steps. "
    "Incorporate knowledge base snippets verbatim when referencing pricing or product facts."
)
OUTREACH_EMAIL_TEMPLATE: Final[str] = (
    "Lead intent: {intent}\n"
    "Latest customer message: {latest_message}\n"
    "Conversation recap:\n{conversation_summary}\n\n"
    "Knowledge base snippets:\n{context}\n\n"
    "Compose a follow-up email addressed to the customer. Start with a friendly greeting, present a tailored pitch, "
    "include relevant pricing or offer details if available, and close with clear payment options (phone transfer and bank transfer). "
    "If pricing isn't present, state that a representative will follow up with specifics."
)
OUTREACH_EMAIL_DEFAULT_SUBJECT: Final[str] = "Next steps on your interest"
OUTREACH_EMAIL_DEFAULT_HISTORY_LIMIT: Final[int] = 8

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
