import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    Difficulty,
    WritingTaskSource,
    WritingTaskStatus,
    WritingTaskType,
)

if TYPE_CHECKING:
    from app.models.writing_submission import WritingSubmission
    from app.models.writing_task_assignment import WritingTaskAssignment

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class WritingTask(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "writing_tasks"
    __table_args__ = (
        CheckConstraint(
            "target_score_min BETWEEN 1 AND 12 AND target_score_max BETWEEN 1 AND 12 "
            "AND target_score_min <= target_score_max",
            name="target_score_range",
        ),
    )

    task_type: Mapped[WritingTaskType] = mapped_column(
        Enum(WritingTaskType, name="writing_task_type"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="task_difficulty"), index=True, nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[WritingTaskStatus] = mapped_column(
        Enum(WritingTaskStatus, name="writing_task_status"),
        default=WritingTaskStatus.APPROVED,
        server_default=WritingTaskStatus.APPROVED.value,
        index=True,
        nullable=False,
    )
    source: Mapped[WritingTaskSource] = mapped_column(
        Enum(WritingTaskSource, name="writing_task_source"),
        default=WritingTaskSource.HUMAN,
        server_default=WritingTaskSource.HUMAN.value,
        nullable=False,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, index=True, nullable=False)
    scenario_key: Mapped[str | None] = mapped_column(String(160), index=True)
    focus_tags: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, default=list, server_default="[]", nullable=False
    )
    target_score_min: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1", nullable=False
    )
    target_score_max: Mapped[int] = mapped_column(
        SmallInteger, default=12, server_default="12", nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    submissions: Mapped[list["WritingSubmission"]] = relationship(
        back_populates="task", passive_deletes="all"
    )
    assignments: Mapped[list["WritingTaskAssignment"]] = relationship(
        back_populates="task", passive_deletes="all"
    )
