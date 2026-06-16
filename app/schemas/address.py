from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class AddressCreate(BaseModel):
    type: str = "shipping"
    full_name: str
    phone: Optional[str] = None
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "India"
    is_default: bool = False


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
