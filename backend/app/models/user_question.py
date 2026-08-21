from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from app.database import Base


class UserQuestion(Base):
    """A question thread a staff member opened with the admin.

    The thread is the conversation; its messages live in UserQuestionMessage so
    admin and user can go back and forth. `status` is the admin's triage state.
    """
    __tablename__ = "user_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # CASCADE: the thread is the asker's own content.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    # Denormalised so the inbox can show/filter by studio without re-deriving it.
    studio_id = Column(UUID(as_uuid=True), ForeignKey("studios.id", ondelete="SET NULL"),
                       nullable=True, index=True)
    status = Column(String(20), nullable=False, default="new")   # new | read | resolved
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Bumped on every new message so the inbox can sort by most-recent activity.
    last_message_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class UserQuestionMessage(Base):
    """One message in a question thread — from the asker or from an admin."""
    __tablename__ = "user_question_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey("user_questions.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    # SET NULL + nullable: keep an admin's replies even if that admin is
    # deleted; the thread history is the point.
    author_user_id = Column(UUID(as_uuid=True),
                            ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # True when written by staff/admin replying — drives left/right styling and
    # the "unread reply" hint without re-checking the author's current role.
    is_admin_reply = Column(Boolean, nullable=False, default=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
