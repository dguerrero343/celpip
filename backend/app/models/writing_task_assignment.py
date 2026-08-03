import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.writing_attempt import WritingAttempt
    from app.models.writing_task import WritingTask


class WritingTaskAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "writing_task_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "family_id", name="uq_writing_task_assignments_user_family"),
        Index("ix_writing_task_assignments_user_assigned", "user_id", "assigned_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("writing_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ASSIGNED", nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="task_assignments")
    task: Mapped["WritingTask"] = relationship(back_populates="assignments")
    attempts: Mapped[list["WritingAttempt"]] = relationship(back_populates="assignment")
