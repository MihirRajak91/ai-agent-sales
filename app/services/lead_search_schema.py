"""
Lead collection schema metadata used by the upcoming natural-language search service.

The module centralises which fields are safe to expose, how they should be described to
an LLM, and which tenant-specific filters must be applied to every query.
"""

from __future__ import annotations

from typing import Dict, List

LEAD_ALWAYS_FILTERS: List[str] = ["org_id", "branch_id"]
"""Fields that must be present in every MongoDB filter to enforce tenant isolation."""


LEAD_SEARCHABLE_FIELDS: Dict[str, Dict[str, object]] = {
    "intent": {
        "type": "string",
        "description": "Lead intent label detected by the assistant.",
        "enum": ["book_appointment", "purchase", "none"],
        "examples": ["book_appointment"],
    },
    "confidence": {
        "type": "number",
        "description": "Confidence score (0-1) produced by the intent classifier.",
        "examples": [0.92, 0.45],
    },
    "status": {
        "type": "string",
        "description": "Lead status managed by operators.",
        "enum": ["open", "contacted", "closed"],
    },
    "latest_message": {
        "type": "string",
        "description": "Most recent user message that triggered lead capture (PII caution).",
        "redactable": True,
        "examples": ["Can we book a demo next week?"],
    },
    "created_at": {
        "type": "datetime",
        "description": "UTC timestamp when the lead was first captured.",
        "examples": ["2025-10-25T07:30:57Z"],
    },
    "updated_at": {
        "type": "datetime",
        "description": "UTC timestamp of the last lead update.",
    },
    "appointment_event_id": {
        "type": "string",
        "description": "Google Calendar event ID linked to this lead, if any.",
        "examples": ["evt_1234"],
    },
    "appointment_start": {
        "type": "datetime",
        "description": "Start time of the scheduled appointment, if any.",
    },
    "appointment_end": {
        "type": "datetime",
        "description": "End time of the scheduled appointment, if any.",
    },
    "calendar_id": {
        "type": "string",
        "description": "Google Calendar identifier used for the appointment.",
        "examples": ["primary"],
    },
    "conversation_id": {
        "type": "string",
        "description": "Conversation thread that produced this lead.",
        "examples": ["demo-thread"],
    },
    "rationale": {
        "type": "string",
        "description": "Short explanation provided by the intent classifier.",
        "redactable": True,
    },
    "user_id": {
        "type": "string",
        "description": "Identifier of the agent/operator chat user.",
    },
}
"""Metadata describing which lead fields can be safely exposed to the search interface."""


LEAD_REDACTED_FIELDS = {
    field for field, meta in LEAD_SEARCHABLE_FIELDS.items() if meta.get("redactable")
}
"""Fields that may contain sensitive free text and should be excluded or masked by default."""


def describe_lead_schema() -> str:
    """Return a human-readable schema summary for use in prompt engineering or docs."""
    lines = ["Lead collection schema:"]
    for field, meta in LEAD_SEARCHABLE_FIELDS.items():
        line = f"- {field} ({meta['type']}): {meta['description']}"
        if meta.get("enum"):
            line += f" Values: {', '.join(meta['enum'])}."
        if meta.get("examples"):
            examples = ", ".join(str(ex) for ex in meta["examples"])
            line += f" Examples: {examples}."
        if field in LEAD_REDACTED_FIELDS:
            line += " [REDACTABLE]"
        lines.append(line)
    lines.append(
        f"All queries must include filters for: {', '.join(LEAD_ALWAYS_FILTERS)}."
    )
    return "\n".join(lines)
