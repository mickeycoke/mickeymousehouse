import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class FranchiseOwner(Base):
    __tablename__ = "franchise_owners"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    franchise_id = Column(UUID(as_uuid=True), ForeignKey("franchises.id"), nullable=False)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # 'manager' (runs studios) or 'reports' (view-only franchise reporting)
    level = Column(String(20), nullable=False, default="manager")
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    assigned_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
