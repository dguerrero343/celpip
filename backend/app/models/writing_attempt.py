import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import WritingAttemptStatus, WritingAttemptType

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.writing_submission import WritingSubmission
    from app.models.writing_task import WritingTask
    from app.models.writing_task_assignment import WritingTaskAssignment

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class WritingAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "writing_attempts"
    __table_args__ = (
        CheckConstraint("word_count >= 0", name="nonnegative_word_count"),
        CheckConstraint("help_panel_open_count >= 0", name="nonnegative_help_panel_open_count"),
        CheckConstraint("help_visible_seconds >= 0", name="nonnegative_help_visible_seconds"),
        Index("ix_writing_attempts_user_status", "user_id", "status"),
        Index("ix_writing_attempts_user_created", "user_id", "created_at"),
        Index(
            "uq_writing_attempts_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('PREPARING', 'WRITING')"),
            sqlite_where=text("status IN ('PREPARING', 'WRITING')"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("writing_task_assignments.id", ondelete="SET NULL")
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("writing_submissions.id", ondelete="SET NULL"), unique=True
    )
    help_mode_enabled: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    attempt_type: Mapped[WritingAttemptType] = mapped_column(
        Enum(WritingAttemptType, name="writing_attempt_type"),
        default=WritingAttemptType.TEST_SIMULATION,
        server_default=WritingAttemptType.TEST_SIMULATION.value,
        nullable=False,
    )
    status: Mapped[WritingAttemptStatus] = mapped_column(
        Enum(WritingAttemptStatus, name="writing_attempt_status"),
        default=WritingAttemptStatus.PREPARING,
        server_default=WritingAttemptStatus.PREPARING.value,
        nullable=False,
    )
    preparation_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    preparation_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    writing_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    writing_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answer_text: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    help_sections_opened: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, default=list, server_default="[]", nullable=False
    )
    help_panel_open_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    help_visible_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="writing_attempts")
    task: Mapped["WritingTask"] = relationship(back_populates="attempts")
    assignment: Mapped["WritingTaskAssignment | None"] = relationship(back_populates="attempts")
    submission: Mapped["WritingSubmission | None"] = relationship(back_populates="attempt")
