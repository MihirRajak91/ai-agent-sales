import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_tenant
from app.models.auth import TenantClaims
from app.models.lead import Lead
from app.services import lead_search
from app.services.lead import list_leads

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=list[Lead])
async def get_leads(tenant: TenantClaims = Depends(get_current_tenant)) -> list[Lead]:
    return list_leads(tenant)


@router.get("/search")
async def search_leads(
    q: str = Query(..., description="Natural language search query."),
    summarize: bool = Query(
        False, description="Include Gemini-generated summary of results."
    ),
    tenant: TenantClaims = Depends(get_current_tenant),
) -> dict:
    try:
        manual_payload = _parse_manual_query(q)
        if manual_payload is not None:
            query = lead_search.build_lead_search_query_from_dict(
                tenant, manual_payload
            )
        else:
            query = lead_search.generate_lead_search_query(tenant, q)

        result = lead_search.execute_lead_search_query(
            tenant, query, intent_label="query_leads"
        )
        if summarize:
            result["summary"] = lead_search.summarize_lead_results(q, result["results"])
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _parse_manual_query(raw: str) -> Dict[str, Any] | None:
    raw = raw.strip()
    if not raw.startswith("{"):
        return None
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Manual query must be a JSON object.")
        return payload
    except json.JSONDecodeError as exc:
        raise ValueError("Could not decode manual JSON query.") from exc
