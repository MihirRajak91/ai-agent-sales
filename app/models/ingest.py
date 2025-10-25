from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    chunk_id: str
    text: str = Field(min_length=1)
    page: int = Field(ge=1)
    position: int = Field(ge=1)


class IngestionResult(BaseModel):
    document_id: str
    namespace: str
    page_count: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    filename: str
