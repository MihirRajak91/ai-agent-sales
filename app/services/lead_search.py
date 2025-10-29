from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from time import perf_counter
from typing import Any, Dict, Iterable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.logging_config import get_logger
from app.models.auth import TenantClaims
from app.models.search import LeadSearchQuery
from app import deps
from app.services.lead_search_schema import (
    LEAD_ALWAYS_FILTERS,
    LEAD_REDACTED_FIELDS,
    LEAD_SEARCHABLE_FIELDS,
    describe_lead_schema,
)
from app.config.settings import settings

logger = get_logger("lead-search")

ALLOWED_FIELDS = set(LEAD_SEARCHABLE_FIELDS.keys()) | {"org_id", "branch_id", "_id"}
ALLOWED_OPERATORS = {
    "$and",
    "$or",
    "$in",
    "$nin",
    "$gt",
    "$gte",
    "$lt",
    "$lte",
    "$eq",
    "$ne",
    "$exists",
    "$regex",
}


LEAD_SEARCH_SYSTEM_PROMPT = f"""You translate natural-language requests into MongoDB query specifications.
Return STRICT JSON with keys:
- "collection": must be "leads"
- "filter": MongoDB filter document (JSON object)
- "projection": optional JSON object with fields to include/exclude (1 or 0)
- "limit": integer 1-100 (defaults to 20)

Schema:
{describe_lead_schema()}

Rules:
- Never refer to collections other than "leads".
- Only use the listed fields; reject unknown attributes.
- Always include equality filters for org_id and branch_id provided in the user context.
- Avoid free-text exposure of redactable fields unless explicitly requested.
- Do NOT include explanations, markdown, or surrounding text—only raw JSON.
"""

LEAD_SUMMARY_SYSTEM_PROMPT = """You craft concise CRM briefings for sales operators.
Summaries must:
- stay under 120 words.
- highlight totals, intent/status mix, and scheduling readiness.
- mention specific lead examples when helpful (use conversation_id when present).
- avoid apologies, hedging, or references to missing data.
Base everything solely on the provided records."""


@lru_cache(maxsize=1)
def _lead_search_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        api_key=settings.GEMINI_API_KEY,
        temperature=0.1,
        max_output_tokens=512,
    )


def generate_lead_search_query(
    tenant: TenantClaims,
    natural_query: str,
) -> LeadSearchQuery:
    """
    Convert a natural-language query into a validated LeadSearchQuery using Gemini.
    """
    llm = _lead_search_llm()
    tenant_context = (
        f"Tenant context: org_id={tenant.org_id}, branch_id={tenant.branch_id}."
    )

    messages = [
        SystemMessage(content=LEAD_SEARCH_SYSTEM_PROMPT),
        HumanMessage(content=f"{tenant_context}\nQuery: {natural_query}"),
    ]

    response = llm.invoke(messages)
    raw_content = response.content if hasattr(response, "content") else str(response)
    raw_content = _normalise_llm_json(raw_content)

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        logger.warning("Lead search LLM returned invalid JSON", extra={"raw": raw_content})
        raise ValueError("Failed to parse search query JSON") from exc

    query = LeadSearchQuery.model_validate(parsed)
    query = sanitize_lead_query(query, tenant)

    logger.info(
        "Lead search query generated",
        extra={
            "tenant_org": tenant.org_id,
            "tenant_branch": tenant.branch_id,
            "filter": query.filter,
            "projection": query.projection,
            "limit": query.limit,
        },
    )
    return query


def sanitize_lead_query(query: LeadSearchQuery, tenant: TenantClaims) -> LeadSearchQuery:
    _enforce_tenant_filters(query.filter, tenant)
    _validate_filter(query.filter)
    query.projection = _sanitize_projection(query.projection)
    return query


def build_lead_search_query_from_dict(
    tenant: TenantClaims, payload: Dict[str, Any]
) -> LeadSearchQuery:
    """
    Construct a LeadSearchQuery from a pre-defined JSON payload (manual mode).
    """
    query = LeadSearchQuery.model_validate(payload)
    return sanitize_lead_query(query, tenant)


def _enforce_tenant_filters(filter_doc: Dict[str, Any], tenant: TenantClaims) -> None:
    filter_doc.setdefault("org_id", tenant.org_id)
    filter_doc.setdefault("branch_id", tenant.branch_id)

    if filter_doc["org_id"] != tenant.org_id or filter_doc["branch_id"] != tenant.branch_id:
        raise ValueError("Tenant filters must match requesting tenant.")


def _validate_filter(filter_doc: Dict[str, Any]) -> None:
    for key, value in filter_doc.items():
        if key.startswith("$"):
            if key not in ALLOWED_OPERATORS:
                raise ValueError(f"Operator '{key}' is not allowed.")
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        _validate_filter(item)
            elif isinstance(value, dict):
                _validate_filter(value)
            continue

        if key not in ALLOWED_FIELDS:
            raise ValueError(f"Field '{key}' is not searchable.")

        if isinstance(value, dict):
            _validate_filter(value)


def _sanitize_projection(
    projection: Optional[Dict[str, int]]
) -> Optional[Dict[str, int]]:
    if projection is None:
        return None

    sanitized: Dict[str, int] = {}
    for field, include in projection.items():
        if field in LEAD_REDACTED_FIELDS:
            continue
        if field in ALLOWED_FIELDS:
            sanitized[field] = 1 if include else 0
    if not sanitized:
        return None
    return sanitized


def execute_lead_search_query(
    tenant: TenantClaims,
    query: LeadSearchQuery,
    *,
    intent_label: str | None = None,
) -> Dict[str, Any]:
    """
    Execute a validated lead search query and return sanitized results.
    """
    db = deps.get_mongo_database()
    filter_doc = dict(query.filter)
    projection = query.projection or None

    start = perf_counter()
    cursor = (
        db[query.collection]
        .find(filter_doc, projection)
        .limit(query.limit)
    )

    results = []
    for document in cursor:
        sanitized = {
            key: value
            for key, value in document.items()
            if key not in LEAD_REDACTED_FIELDS
        }
        if "_id" in sanitized:
            sanitized["_id"] = str(sanitized["_id"])
        results.append(sanitized)

    elapsed_ms = round((perf_counter() - start) * 1000, 2)

    logger.info(
        "Lead search executed",
        extra={
            "tenant_org": tenant.org_id,
            "tenant_branch": tenant.branch_id,
            "intent": intent_label,
            "filter": filter_doc,
            "projection": projection,
            "limit": query.limit,
            "result_count": len(results),
            "elapsed_ms": elapsed_ms,
        },
    )

    return {
        "results": results,
        "count": len(results),
        "limit": query.limit,
        "elapsed_ms": elapsed_ms,
        "query": {
            "filter": filter_doc,
            "projection": projection,
            "limit": query.limit,
        },
    }


def _normalise_llm_json(raw: str) -> str:
    raw = (raw or "").strip()

    if "```" in raw:

        segments = [segment.strip() for segment in raw.split("```") if segment.strip()]
        for segment in segments:
            candidate = segment
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                raw = candidate
                break

    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]

    return raw


@lru_cache(maxsize=1)
def _lead_summary_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        api_key=settings.GEMINI_API_KEY,
        temperature=0.3,
        max_output_tokens=256,
    )


def summarize_lead_results(natural_query: str, records: list[Dict[str, Any]]) -> str:
    if not records:
        return "No leads matched that query."

    stats = _collect_lead_stats(records)
    fallback = _build_fallback_lead_summary(records, stats)

    if not settings.GEMINI_API_KEY:
        return fallback

    summary = None

    try:
        llm = _lead_summary_llm()
        stats_payload = {
            "total": stats["count"],
            "intent_counts": stats["intent_counts"],
            "status_counts": stats["status_counts"],
            "with_calendar_event": stats["with_calendar_event"],
        }
        sample_records = [
            {key: _json_safe(value) for key, value in record.items()}
            for record in records[:6]
        ]
        human_prompt = (
            "Generate an operator-facing summary of leads returned from a tenant-scoped search.\n"
            f"Original query: {natural_query}\n"
            f"Lead metrics (JSON): {json.dumps(stats_payload, ensure_ascii=False)}\n"
            "Sample leads (sanitized JSON list, max 6):\n"
            f"{json.dumps(sample_records, ensure_ascii=False, indent=2)}\n"
            "Write 2-3 sentences that highlight follow-up priorities, notable intents/statuses, and scheduling readiness."
        )
        messages = [
            SystemMessage(content=LEAD_SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]
        response = llm.invoke(messages)
        summary = _extract_response_text(response)
        if summary:
            logger.info(
                "Lead summary generated",
                extra={"source": "llm", "lead_count": len(records)},
            )
            return summary
        logger.debug(
            "Lead summary LLM returned empty content",
            extra={
                "content": repr(getattr(response, "content", None)),
                "additional_kwargs": repr(getattr(response, "additional_kwargs", None)),
                "response_metadata": repr(getattr(response, "response_metadata", None)),
            },
        )
    except Exception as exc:
        logger.warning(
            "Lead summary LLM failed; using fallback summary: %s",
            exc,
            extra={"error_type": type(exc).__name__},
        )

    if not summary:
        logger.info(
            "Lead summary fallback used",
            extra={"source": "fallback", "lead_count": len(records)},
        )

    return fallback


def _collect_lead_stats(records: list[Dict[str, Any]]) -> Dict[str, Any]:
    intent_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    scheduled = 0

    for record in records:
        intent = record.get("intent")
        if intent:
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

        status = record.get("status")
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1

        if record.get("appointment_event_id"):
            scheduled += 1

    return {
        "count": len(records),
        "intent_counts": intent_counts,
        "status_counts": status_counts,
        "with_calendar_event": scheduled,
    }


def _build_fallback_lead_summary(
    records: list[Dict[str, Any]], stats: Dict[str, Any]
) -> str:
    summary_parts = [f"{stats['count']} lead(s) matched the query."]

    if stats["intent_counts"]:
        intents_text = ", ".join(
            f"{intent} x{count}" for intent, count in stats["intent_counts"].items()
        )
        summary_parts.append(f"Intent mix: {intents_text}.")

    if stats["status_counts"]:
        status_text = ", ".join(
            f"{status} x{count}" for status, count in stats["status_counts"].items()
        )
        summary_parts.append(f"Statuses: {status_text}.")

    if stats["with_calendar_event"]:
        summary_parts.append(
            f"{stats['with_calendar_event']} lead(s) already have calendar events."
        )

    preview = _build_lead_preview(records)
    if preview:
        summary_parts.append("Examples: " + "; ".join(preview))

    return " ".join(summary_parts)


def _build_lead_preview(records: list[Dict[str, Any]], limit: int = 2) -> list[str]:
    preview: list[str] = []
    for record in records[:limit]:
        preview_bits: list[str] = []

        intent = record.get("intent")
        if intent:
            preview_bits.append(str(intent))

        status = record.get("status")
        if status:
            preview_bits.append(str(status))

        confidence = record.get("confidence")
        if isinstance(confidence, (int, float)):
            preview_bits.append(f"confidence {confidence:.2f}")
        elif confidence is not None:
            preview_bits.append(f"confidence {confidence}")

        identifier = record.get("conversation_id") or record.get("_id")
        preview.append(f"{identifier}: " + ", ".join(preview_bits))

    return preview


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _extract_response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    joined = _join_segments(_flatten_text_segments(content))

    if not joined and hasattr(response, "additional_kwargs"):
        joined = _join_segments(
            _flatten_text_segments(getattr(response, "additional_kwargs"))
        )

    if not joined and hasattr(response, "response_metadata"):
        joined = _join_segments(
            _flatten_text_segments(getattr(response, "response_metadata"))
        )

    return joined


def _flatten_text_segments(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, (list, tuple, set)):
        collected: list[str] = []
        for item in value:
            collected.extend(_flatten_text_segments(item))
        return collected

    if isinstance(value, dict):
        collected: list[str] = []
        processed_keys: set[str] = set()
        if isinstance(value.get("text"), str):
            collected.append(value["text"])
            processed_keys.add("text")
        if "parts" in value:
            collected.extend(_flatten_text_segments(value["parts"]))
            processed_keys.add("parts")
        if "content" in value:
            collected.extend(_flatten_text_segments(value["content"]))
            processed_keys.add("content")
        for key, item in value.items():
            if key in processed_keys:
                continue
            collected.extend(_flatten_text_segments(item))
        return collected

    # LangChain content parts may expose .text / .parts attributes
    text_attr = getattr(value, "text", None)
    if isinstance(text_attr, str):
        return [text_attr]

    parts_attr = getattr(value, "parts", None)
    if parts_attr is not None:
        return _flatten_text_segments(parts_attr)

    content_attr = getattr(value, "content", None)
    if content_attr is not None and content_attr is not value:
        return _flatten_text_segments(content_attr)

    return [str(value)]


def _join_segments(segments: list[str]) -> str:
    filtered = _filter_summary_segments(segments)
    return " ".join(filtered).strip()


def _filter_summary_segments(segments: list[str]) -> list[str]:
    filtered: list[str] = []
    for segment in segments:
        if not segment:
            continue
        stripped = segment.strip()
        if not stripped:
            continue
        if not any(ch.isalpha() for ch in stripped):
            continue
        if stripped.isupper() and len(stripped.split()) == 1:
            continue
        filtered.append(stripped)
    return filtered
