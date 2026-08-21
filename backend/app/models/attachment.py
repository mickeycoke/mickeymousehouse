from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import deferred
import uuid
from datetime import datetime

from app.database import Base


class Attachment(Base):
    """An uploaded image (screenshot, QR code, …) pinned to a note or a chat
    message. Plain pictures only — the server never generates or interprets
    them.

    Bytes live in Postgres so the existing DB backup covers them; `data` is
    deferred so list queries never drag blobs along. An attachment starts
    unlinked (uploaded from a composer, visible only to its uploader) and is
    linked to exactly one parent when the note/message is created.
    """
    __tablename__ = "attachments"
    __table_args__ = (
        # At most one parent — a picture belongs to a note OR a message.
        CheckConstraint("note_id IS NULL OR question_message_id IS NULL",
                        name="ck_attachment_single_parent"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # CASCADE: deleting the note/message deletes its pictures with it.
    note_id = Column(UUID(as_uuid=True), ForeignKey("user_notes.id", ondelete="CASCADE"),
                     nullable=True, index=True)
    question_message_id = Column(UUID(as_uuid=True),
                                 ForeignKey("user_question_messages.id", ondelete="CASCADE"),
                                 nullable=True, index=True)
    # SET NULL: deleting the uploader must not delete what they attached.
    uploaded_by_user_id = Column(UUID(as_uuid=True),
                                 ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    data = deferred(Column(LargeBinary, nullable=False))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
