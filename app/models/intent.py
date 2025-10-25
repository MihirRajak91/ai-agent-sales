from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IntentLabel(str, Enum):
    NONE = "none"
    BOOK_APPOINTMENT = "book_appointment"
    PURCHASE = "purchase"


class IntentClassification(BaseModel):
    label: IntentLabel = IntentLabel.NONE
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    rationale: Optional[str] = Field(default=None, description="Model rationale for the classification.")
