from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    chunk_id: str
    score: float = Field(ge=0)
    text: str
    page: int | None = Field(default=None, ge=1)
    source: str | None = None


class RetrievalResult(BaseModel):
    query: str
    namespace: str
    matches: list[RetrievedChunk]
