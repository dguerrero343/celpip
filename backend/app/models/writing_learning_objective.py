import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import LearningObjectiveStatus, WritingAttemptType


class WritingLearningObjective(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "writing_learning_objectives"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_submissions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    assessed_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("writing_submissions.id", ondelete="SET NULL")
    )
    attempt_type: Mapped[WritingAttemptType] = mapped_column(
        Enum(WritingAttemptType, name="writing_attempt_type", create_type=False), nullable=False
    )
    skill: Mapped[str] = mapped_column(String(40), nullable=False)
    objective: Mapped[str] = mapped_column(String(300), nullable=False)
    success_criteria: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[LearningObjectiveStatus] = mapped_column(
        Enum(LearningObjectiveStatus, name="learning_objective_status"),
        default=LearningObjectiveStatus.PENDING,
        nullable=False,
    )
    assessment_explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
