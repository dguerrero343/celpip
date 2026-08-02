import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.writing_submission import WritingSubmission

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class WritingEvaluation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "writing_evaluations"
    __table_args__ = (
        CheckConstraint("estimated_score BETWEEN 1 AND 12", name="estimated_score_range"),
        CheckConstraint("task_fulfillment_score BETWEEN 1 AND 12", name="task_score_range"),
        CheckConstraint("organization_score BETWEEN 1 AND 12", name="organization_score_range"),
        CheckConstraint("vocabulary_score BETWEEN 1 AND 12", name="vocabulary_score_range"),
        CheckConstraint("grammar_score BETWEEN 1 AND 12", name="grammar_score_range"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_submissions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    estimated_score: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    task_fulfillment_score: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    organization_score: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    vocabulary_score: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    grammar_score: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    score_gap: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    weaknesses: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    corrections: Mapped[list[dict[str, str]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    recommended_exercises: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    ai_raw_response: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT, nullable=False)

    submission: Mapped["WritingSubmission"] = relationship(back_populates="evaluation")
