from __future__ import annotations

from typing import List

from app import deps
from app.models.auth import TenantClaims
from app.models.retrieval import RetrievedChunk, RetrievalResult
from app.services.tenancy import build_tenant_namespace
from app.config.settings import settings
from app.utils.constants import (
    DEFAULT_RETRIEVAL_TOP_K,
    GEMINI_EMPTY_EMBEDDINGS_ERROR,
    RETRIEVAL_TASK_TYPE,
)


def query_knowledge_base(
    tenant: TenantClaims,
    query_text: str,
    top_k: int = DEFAULT_RETRIEVAL_TOP_K,
) -> RetrievalResult:
    """
    Query Pinecone for tenant-specific knowledge using a Gemini-generated embedding.

    The namespace and metadata checks ensure an org/branch only sees its own content.
    """
    namespace = build_tenant_namespace(tenant)

    gemini_client = deps.get_gemini_client()
    response = gemini_client.models.embed_content(
        model=settings.EMBED_MODEL,
        contents=query_text,
        config={"task_type": RETRIEVAL_TASK_TYPE},
    )

    if not response.embeddings:
        raise RuntimeError(GEMINI_EMPTY_EMBEDDINGS_ERROR)

    query_vector = list(response.embeddings[0].values)

    index = deps.get_pinecone_index()
    pinecone_response = index.query(
        namespace=namespace,
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
    )

    raw_matches = _extract_matches(pinecone_response)
    matches = _filter_matches(raw_matches, tenant)

    return RetrievalResult(
        query=query_text,
        namespace=namespace,
        matches=matches,
    )


def _extract_matches(response) -> List[dict]:
    if response is None:
        return []
    if isinstance(response, dict):
        return response.get("matches", [])
    matches = getattr(response, "matches", None)
    if matches is None:
        return []
    return matches


def _filter_matches(raw_matches: List[dict], tenant: TenantClaims) -> List[RetrievedChunk]:
    """
    Filter Pinecone matches to enforce tenant isolation and map into response models.
    """
    scoped_matches: List[RetrievedChunk] = []

    for match in raw_matches:
        metadata = match.get("metadata") or {}
        if (
            metadata.get("org_id") != tenant.org_id
            or metadata.get("branch_id") != tenant.branch_id
        ):
            # Defensive guard: namespace should already isolate, but double check.
            continue

        scoped_matches.append(
            RetrievedChunk(
                chunk_id=match.get("id", ""),
                score=float(match.get("score", 0.0)),
                text=metadata.get("text", ""),
                page=metadata.get("page"),
                source=metadata.get("source"),
            )
        )

    return scoped_matches
