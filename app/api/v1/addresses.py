from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.address import Address
from app.models.user import User
from app.schemas.address import AddressCreate, AddressUpdate, AddressResponse

router = APIRouter()


@router.get("/", response_model=List[AddressResponse])
def list_addresses(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    addresses = db.query(Address).filter(Address.user_id == current_user.id).all()
    return addresses


@router.get("/{address_id}", response_model=AddressResponse)
def get_address(
    address_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    address = db.query(Address).filter(
        Address.id == address_id,
        Address.user_id == current_user.id
    ).first()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    return address


@router.post("/", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
def create_address(
    address_data: AddressCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # If this is set as default, unset other defaults
    if address_data.is_default:
        db.query(Address).filter(
            Address.user_id == current_user.id,
            Address.type == address_data.type
        ).update({"is_default": False})

    address = Address(
        user_id=current_user.id,
        **address_data.model_dump()
    )
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


@router.put("/{address_id}", response_model=AddressResponse)
def update_address(
    address_id: UUID,
    address_data: AddressUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    address = db.query(Address).filter(
        Address.id == address_id,
        Address.user_id == current_user.id
    ).first()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    update_data = address_data.model_dump(exclude_unset=True)

    # If setting as default, unset other defaults
    if update_data.get("is_default"):
        db.query(Address).filter(
            Address.user_id == current_user.id,
            Address.type == address.type,
            Address.id != address_id
        ).update({"is_default": False})

    for field, value in update_data.items():
        setattr(address, field, value)

    db.commit()
    db.refresh(address)
    return address


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    address = db.query(Address).filter(
        Address.id == address_id,
        Address.user_id == current_user.id
    ).first()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    db.delete(address)
    db.commit()


@router.post("/{address_id}/set-default", response_model=AddressResponse)
def set_default_address(
    address_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    address = db.query(Address).filter(
        Address.id == address_id,
        Address.user_id == current_user.id
    ).first()
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    # Unset other defaults of same type
    db.query(Address).filter(
        Address.user_id == current_user.id,
        Address.type == address.type,
        Address.id != address_id
    ).update({"is_default": False})

    address.is_default = True
    db.commit()
    db.refresh(address)
    return address
