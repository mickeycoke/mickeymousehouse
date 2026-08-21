from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from app.database import Base


class UserNote(Base):
    """An admin-authored announcement shown to staff at login.

    Editing a note bumps `updated_at`, which is what makes a dismissed note
    come BACK: a dismissal only silences the note as it stood when dismissed
    (see UserNoteDismissal), so a fresh edit re-surfaces it for everyone.
    """
    __tablename__ = "user_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    body = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    # SET NULL: deleting the author must not delete the announcement.
    created_by_user_id = Column(UUID(as_uuid=True),
                                ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserNoteDismissal(Base):
    """One row per (user, note) "Disregard" click.

    `dismissed_at` is compared against the note's `updated_at`: the note is
    hidden only while dismissed_at >= updated_at. Re-editing the note makes
    updated_at newer, so it shows again — "dismiss until you change it".
    """
    __tablename__ = "user_note_dismissals"
    __table_args__ = (UniqueConstraint("note_id", "user_id", name="uq_note_dismissal"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    note_id = Column(UUID(as_uuid=True), ForeignKey("user_notes.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    # CASCADE: a dismissal is meaningless without its note or user.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    dismissed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
