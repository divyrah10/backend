from fastapi import APIRouter, Depends, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.early_access import EarlyAccessEvent, EarlyAccessLead
from app.schemas.early_access import (
    EarlyAccessEventCreate,
    EarlyAccessLeadCreate,
    EarlyAccessTrackResponse,
)

router = APIRouter()


@router.post(
    "/events",
    response_model=EarlyAccessTrackResponse,
    status_code=status.HTTP_201_CREATED,
)
def track_early_access_event(
    event_data: EarlyAccessEventCreate,
    db: Session = Depends(get_db),
):
    event = EarlyAccessEvent(**event_data.model_dump())
    db.add(event)

    try:
        db.commit()
        return {"tracked": True, "message": "Event recorded"}
    except IntegrityError:
        db.rollback()
        return {"tracked": False, "message": "Event already recorded for this session"}


@router.post(
    "/leads",
    response_model=EarlyAccessTrackResponse,
    status_code=status.HTTP_201_CREATED,
)
def join_early_access(
    lead_data: EarlyAccessLeadCreate,
    db: Session = Depends(get_db),
):
    normalized_email = str(lead_data.email).strip().lower()
    existing_lead = db.query(EarlyAccessLead).filter(
        func.lower(EarlyAccessLead.email) == normalized_email
    ).first()

    if existing_lead:
        return {"tracked": False, "message": "You are already on the early-access list"}

    lead = EarlyAccessLead(
        **lead_data.model_dump(exclude={"email"}),
        email=normalized_email,
    )
    db.add(lead)
    db.commit()

    return {"tracked": True, "message": "You are on the early-access list"}
