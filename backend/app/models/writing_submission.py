import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import WritingAttemptType

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.writing_attempt import WritingAttempt
    from app.models.writing_evaluation import WritingEvaluation
    from app.models.writing_task import WritingTask


class WritingSubmission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "writing_submissions"
    __table_args__ = (
        CheckConstraint("word_count >= 0", name="nonnegative_word_count"),
        Index("ix_writing_submissions_user_submitted", "user_id", "submitted_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="submissions")
    task: Mapped["WritingTask"] = relationship(back_populates="submissions")
    evaluation: Mapped["WritingEvaluation | None"] = relationship(
        back_populates="submission", cascade="all, delete-orphan", passive_deletes=True
    )
    attempt: Mapped["WritingAttempt | None"] = relationship(back_populates="submission")

    @property
    def attempt_type(self) -> WritingAttemptType:
        return (
            self.attempt.attempt_type
            if self.attempt is not None
            else WritingAttemptType.TEST_SIMULATION
        )
