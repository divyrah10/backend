import re

from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID


def indian_mobile(value: str) -> str:
    """10-digit Indian mobile; accepts +91, spaces and dashes. Couriers need it to deliver."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Enter a 10-digit mobile number")
    return digits


class AddressCreate(BaseModel):
    type: str = "shipping"
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "India"
    is_default: bool = False

    _phone = field_validator("phone")(indian_mobile)


class AddressUpdate(BaseModel):
    type: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    is_default: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else indian_mobile(value)


class AddressResponse(BaseModel):
    id: UUID
    type: str
    full_name: str
    phone: Optional[str]
    address_line1: str
    address_line2: Optional[str]
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool

    class Config:
        from_attributes = True
