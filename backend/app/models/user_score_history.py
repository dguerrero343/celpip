import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import Skill

if TYPE_CHECKING:
    from app.models.user import User


class UserScoreHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_score_history"
    __table_args__ = (
        CheckConstraint("score BETWEEN 1 AND 12", name="score_range"),
        Index("ix_user_score_history_user_date", "user_id", "date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill: Mapped[Skill] = mapped_column(Enum(Skill, name="celpip_skill"), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    user: Mapped["User"] = relationship(back_populates="score_history")
