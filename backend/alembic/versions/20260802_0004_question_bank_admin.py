"""Add curated question-bank workflow and no-repeat assignments.

Revision ID: 20260802_0004
Revises: 20260801_0003
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260802_0004"
down_revision: str | None = "20260801_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

task_status = postgresql.ENUM(
    "DRAFT", "IN_REVIEW", "APPROVED", "RETIRED", name="writing_task_status", create_type=False
)
task_source = postgresql.ENUM("HUMAN", "AI", name="writing_task_source", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    task_status.create(bind, checkfirst=True)
    task_source.create(bind, checkfirst=True)

    op.add_column(
        "writing_tasks",
        sa.Column("status", task_status, server_default="APPROVED", nullable=False),
    )
    op.add_column(
        "writing_tasks",
        sa.Column("source", task_source, server_default="HUMAN", nullable=False),
    )
    op.add_column("writing_tasks", sa.Column("family_id", sa.Uuid(), nullable=True))
    op.add_column("writing_tasks", sa.Column("scenario_key", sa.String(length=160)))
    op.add_column(
        "writing_tasks",
        sa.Column(
            "focus_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "writing_tasks",
        sa.Column("target_score_min", sa.SmallInteger(), server_default="1", nullable=False),
    )
    op.add_column(
        "writing_tasks",
        sa.Column("target_score_max", sa.SmallInteger(), server_default="12", nullable=False),
    )
    op.add_column("writing_tasks", sa.Column("reviewed_by", sa.Uuid()))
    op.add_column("writing_tasks", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "writing_tasks",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute("UPDATE writing_tasks SET family_id = id")
    op.alter_column("writing_tasks", "family_id", nullable=False)
    op.create_foreign_key(
        "fk_writing_tasks_reviewed_by_users",
        "writing_tasks",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_writing_tasks_target_score_range",
        "writing_tasks",
        "target_score_min BETWEEN 1 AND 12 AND target_score_max BETWEEN 1 AND 12 "
        "AND target_score_min <= target_score_max",
    )
    op.create_index("ix_writing_tasks_status", "writing_tasks", ["status"])
    op.create_index("ix_writing_tasks_family_id", "writing_tasks", ["family_id"])
    op.create_index("ix_writing_tasks_scenario_key", "writing_tasks", ["scenario_key"])

    op.create_table(
        "writing_task_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["writing_tasks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "family_id", name="uq_writing_task_assignments_user_family"),
    )
    op.create_index(
        "ix_writing_task_assignments_user_assigned",
        "writing_task_assignments",
        ["user_id", "assigned_at"],
    )
    op.execute(
        """
        INSERT INTO writing_task_assignments (
            id, user_id, task_id, family_id, status, assigned_at
        )
        SELECT DISTINCT ON (submission.user_id, submission.task_id)
            submission.id,
            submission.user_id,
            submission.task_id,
            submission.task_id,
            'COMPLETED',
            submission.submitted_at
        FROM writing_submissions AS submission
        ORDER BY submission.user_id, submission.task_id, submission.submitted_at
        """
    )


def downgrade() -> None:
    op.drop_table("writing_task_assignments")
    op.drop_index("ix_writing_tasks_scenario_key", table_name="writing_tasks")
    op.drop_index("ix_writing_tasks_family_id", table_name="writing_tasks")
    op.drop_index("ix_writing_tasks_status", table_name="writing_tasks")
    op.drop_constraint("ck_writing_tasks_target_score_range", "writing_tasks", type_="check")
    op.drop_constraint("fk_writing_tasks_reviewed_by_users", "writing_tasks", type_="foreignkey")
    for column in (
        "updated_at",
        "reviewed_at",
        "reviewed_by",
        "target_score_max",
        "target_score_min",
        "focus_tags",
        "scenario_key",
        "family_id",
        "source",
        "status",
    ):
        op.drop_column("writing_tasks", column)
    task_source.drop(op.get_bind(), checkfirst=True)
    task_status.drop(op.get_bind(), checkfirst=True)
