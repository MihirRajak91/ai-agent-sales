from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.deps import get_current_tenant
from app.models.auth import TenantClaims
from app.services.ingest import ingest_pdf_document

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def ingest_pdf(
    file: UploadFile = File(...),
    tenant: TenantClaims = Depends(get_current_tenant),
) -> dict[str, object]:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF uploads are supported"
        )

    file_bytes = await file.read()

    try:
        result = ingest_pdf_document(file_bytes, file.filename or "document.pdf", tenant)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return {
        "document_id": result.document_id,
        "namespace": result.namespace,
        "page_count": result.page_count,
        "chunk_count": result.chunk_count,
        "filename": result.filename,
    }
