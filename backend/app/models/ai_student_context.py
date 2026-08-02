import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.user import User

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class AIStudentContext(Base):
    __tablename__ = "ai_student_context"
    __table_args__ = (
        CheckConstraint("current_score BETWEEN 1 AND 12", name="current_score_range"),
        CheckConstraint("target_score BETWEEN 1 AND 12", name="target_score_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    current_score: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    target_score: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    score_gap: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    main_weaknesses: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    grammar_focus: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    vocabulary_focus: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    recommended_strategy: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="ai_context")
