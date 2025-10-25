from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator


class LeadSearchQuery(BaseModel):
    collection: str = Field(
        ...,
        description="Mongo collection to query. Must be 'leads'.",
    )
    filter: Dict = Field(default_factory=dict, description="Mongo filter document.")
    projection: Optional[Dict[str, int]] = Field(
        default=None,
        description="Fields to include/exclude in the result set.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of documents to return.",
    )

    @field_validator("collection")
    @classmethod
    def validate_collection(cls, value: str) -> str:
        if value != "leads":
            raise ValueError("Only the 'leads' collection is supported.")
        return value
