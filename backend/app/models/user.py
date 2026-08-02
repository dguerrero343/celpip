from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, Enum, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.ai_student_context import AIStudentContext
    from app.models.ai_usage import AIUsage
    from app.models.user_score_history import UserScoreHistory
    from app.models.writing_submission import WritingSubmission
    from app.models.writing_task_assignment import WritingTaskAssignment


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "current_celpip_score IS NULL OR current_celpip_score BETWEEN 1 AND 12",
            name="current_score_range",
        ),
        CheckConstraint(
            "target_celpip_score IS NULL OR target_celpip_score BETWEEN 1 AND 12",
            name="target_score_range",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    current_celpip_score: Mapped[int | None] = mapped_column(SmallInteger)
    target_celpip_score: Mapped[int | None] = mapped_column(SmallInteger)
    target_exam_date: Mapped[date | None] = mapped_column(Date)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        default=UserRole.STUDENT,
        server_default=UserRole.STUDENT.value,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    submissions: Mapped[list["WritingSubmission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    ai_context: Mapped["AIStudentContext | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    score_history: Mapped[list["UserScoreHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    ai_usage: Mapped[list["AIUsage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    task_assignments: Mapped[list["WritingTaskAssignment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
