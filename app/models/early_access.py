import uuid

from sqlalchemy import Column, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, TimestampMixin


class EarlyAccessEvent(Base, TimestampMixin):
    __tablename__ = "early_access_events"
    __table_args__ = (
        UniqueConstraint("session_id", "event_type", name="uq_early_access_session_event"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    source = Column(String(100), nullable=False, default="direct", index=True)
    medium = Column(String(100), nullable=False, default="none")
    campaign = Column(String(100), nullable=False, default="early_access", index=True)
    content = Column(String(100), nullable=True, index=True)
    landing_path = Column(String(500), nullable=True)


class EarlyAccessLead(Base, TimestampMixin):
    __tablename__ = "early_access_leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    source = Column(String(100), nullable=False, default="direct", index=True)
    medium = Column(String(100), nullable=False, default="none")
    campaign = Column(String(100), nullable=False, default="early_access", index=True)
    content = Column(String(100), nullable=True, index=True)
