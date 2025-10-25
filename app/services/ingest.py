from __future__ import annotations

import io
from datetime import datetime, timezone
from functools import lru_cache
from typing import Iterable, List
from uuid import uuid4

from pypdf import PdfReader
import tiktoken

from app import deps
from app.models.auth import TenantClaims
from app.models.ingest import DocumentChunk, IngestionResult
from app.settings import settings
from app.services.tenancy import build_tenant_namespace


MAX_PDF_BYTES = 15 * 1024 * 1024  # 15 MB ceiling for ingestion
CHUNK_TOKEN_LIMIT = 350
CHUNK_TOKEN_OVERLAP = 50


@lru_cache(maxsize=1)
def _token_encoding():
    return tiktoken.get_encoding("cl100k_base")


def ingest_pdf_document(file_bytes: bytes, filename: str, tenant: TenantClaims) -> IngestionResult:
    if len(file_bytes) == 0:
        raise ValueError("Uploaded file is empty")

    if len(file_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds maximum size of 15 MB")

    pages = _extract_pdf_pages(file_bytes)
    if not pages:
        raise ValueError("Could not extract text from PDF")

    document_id = str(uuid4())
    namespace = build_tenant_namespace(tenant)

    chunks = _chunk_pages(document_id, pages)
    vectors = _embed_chunks([chunk.text for chunk in chunks])

    _upsert_chunks(namespace, document_id, chunks, vectors, tenant, filename)
    _record_ingestion(document_id, namespace, filename, len(pages), len(chunks), tenant)

    return IngestionResult(
        document_id=document_id,
        namespace=namespace,
        page_count=len(pages),
        chunk_count=len(chunks),
        filename=filename,
    )


def _extract_pdf_pages(file_bytes: bytes) -> list[tuple[int, str]]:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages: list[tuple[int, str]] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        cleaned = text.strip()
        if cleaned:
            pages.append((index, cleaned))

    return pages


def _chunk_pages(document_id: str, pages: Iterable[tuple[int, str]]) -> List[DocumentChunk]:
    chunks: List[DocumentChunk] = []

    for page_number, text in pages:
        for position, chunk_text in enumerate(
            _chunk_text_tokens(text, CHUNK_TOKEN_LIMIT, CHUNK_TOKEN_OVERLAP), start=1
        ):
            chunk_id = f"{document_id}_p{page_number:04d}_c{position:02d}"
            chunks.append(DocumentChunk(chunk_id=chunk_id, text=chunk_text, page=page_number, position=position))

    return chunks


def _chunk_text_tokens(text: str, limit: int, overlap: int) -> Iterable[str]:
    encoding = _token_encoding()
    tokens = encoding.encode(text)
    total = len(tokens)
    start = 0

    while start < total:
        end = min(start + limit, total)
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens).strip()
        if chunk_text:
            yield chunk_text
        if end >= total:
            break
        start = max(0, end - overlap)


def _embed_chunks(texts: List[str]) -> List[List[float]]:
    client = deps.get_gemini_client()
    vectors: List[List[float]] = []

    for text in texts:
        response = client.models.embed_content(
            model=settings.EMBED_MODEL,
            contents=text,
            config={"task_type": "RETRIEVAL_DOCUMENT"},
        )
        if not response.embeddings:
            raise RuntimeError("Gemini returned empty embeddings response")

        vector = list(response.embeddings[0].values)
        if len(vector) != settings.EMBED_OUTPUT_DIM:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {settings.EMBED_OUTPUT_DIM}, got {len(vector)}"
            )
        vectors.append(vector)

    return vectors


def _upsert_chunks(
    namespace: str,
    document_id: str,
    chunks: List[DocumentChunk],
    vectors: List[List[float]],
    tenant: TenantClaims,
    filename: str,
) -> None:
    if len(chunks) != len(vectors):
        raise RuntimeError("Chunk and embedding counts do not match")

    index = deps.get_pinecone_index()
    payload = []

    for chunk, vector in zip(chunks, vectors):
        payload.append(
            {
                "id": chunk.chunk_id,
                "values": vector,
                "metadata": {
                    "text": chunk.text,
                    "page": chunk.page,
                    "chunk": chunk.position,
                    "source": filename,
                    "document_id": document_id,
                    "org_id": tenant.org_id,
                    "branch_id": tenant.branch_id,
                    "user_id": tenant.user_id,
                },
            }
        )

    index.upsert(vectors=payload, namespace=namespace)


def _record_ingestion(
    document_id: str,
    namespace: str,
    filename: str,
    page_count: int,
    chunk_count: int,
    tenant: TenantClaims,
) -> None:
    db = deps.get_mongo_database()
    db["ingestions"].insert_one(
        {
            "document_id": document_id,
            "namespace": namespace,
            "filename": filename,
            "page_count": page_count,
            "chunk_count": chunk_count,
            "org_id": tenant.org_id,
            "branch_id": tenant.branch_id,
            "user_id": tenant.user_id,
            "created_at": datetime.now(timezone.utc),
        }
    )

