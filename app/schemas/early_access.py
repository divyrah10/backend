from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class EarlyAccessAttribution(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    source: str = Field(default="direct", max_length=100)
    medium: str = Field(default="none", max_length=100)
    campaign: str = Field(default="early_access", max_length=100)
    content: Optional[str] = Field(default=None, max_length=100)


class EarlyAccessEventCreate(EarlyAccessAttribution):
    event_type: Literal["page_view", "store_entered"]
    landing_path: Optional[str] = Field(default=None, max_length=500)


class EarlyAccessLeadCreate(EarlyAccessAttribution):
    email: EmailStr


class EarlyAccessTrackResponse(BaseModel):
    tracked: bool
    message: str
