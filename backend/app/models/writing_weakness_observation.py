import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import WeaknessTrend, WritingAttemptType


class WritingWeaknessObservation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "writing_weakness_observations"
    __table_args__ = (
        Index("ix_weakness_observations_user_created", "user_id", "created_at"),
        Index("ix_weakness_observations_user_key", "user_id", "weakness_key"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_submissions.id", ondelete="CASCADE"), nullable=False
    )
    weakness_key: Mapped[str] = mapped_column(String(80), nullable=False)
    weakness_label: Mapped[str] = mapped_column(String(240), nullable=False)
    skill: Mapped[str] = mapped_column(String(40), nullable=False)
    trend: Mapped[WeaknessTrend] = mapped_column(
        Enum(WeaknessTrend, name="weakness_trend"), nullable=False
    )
    is_present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attempt_type: Mapped[WritingAttemptType] = mapped_column(
        Enum(WritingAttemptType, name="writing_attempt_type", create_type=False), nullable=False
    )
    rubric_score: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
