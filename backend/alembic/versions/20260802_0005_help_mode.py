"""Add server-authoritative writing attempts and cached help content.

Revision ID: 20260802_0005
Revises: 20260802_0004
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260802_0005"
down_revision: str | None = "20260802_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

attempt_type = postgresql.ENUM(
    "GUIDED_PRACTICE", "TEST_SIMULATION", name="writing_attempt_type", create_type=False
)
attempt_status = postgresql.ENUM(
    "PREPARING", "WRITING", "SUBMITTED", "EXPIRED", name="writing_attempt_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    attempt_type.create(bind, checkfirst=True)
    attempt_status.create(bind, checkfirst=True)
    op.add_column(
        "writing_tasks", sa.Column("help_content_json", postgresql.JSONB(astext_type=sa.Text()))
    )
    op.add_column("writing_tasks", sa.Column("help_content_version", sa.String(length=40)))
    op.add_column("writing_tasks", sa.Column("help_content_model", sa.String(length=100)))
    op.add_column(
        "writing_tasks", sa.Column("help_content_generated_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "writing_tasks",
        sa.Column(
            "help_content_is_fixture", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.create_table(
        "writing_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid()),
        sa.Column("submission_id", sa.Uuid()),
        sa.Column("help_mode_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("attempt_type", attempt_type, server_default="TEST_SIMULATION", nullable=False),
        sa.Column("status", attempt_status, server_default="PREPARING", nullable=False),
        sa.Column("preparation_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preparation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("writing_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("writing_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("answer_text", sa.Text(), server_default="", nullable=False),
        sa.Column("word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "help_sections_opened",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("help_panel_open_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("help_visible_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_saved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("word_count >= 0", name="nonnegative_word_count"),
        sa.CheckConstraint(
            "help_panel_open_count >= 0",
            name="nonnegative_help_panel_open_count",
        ),
        sa.CheckConstraint("help_visible_seconds >= 0", name="nonnegative_help_visible_seconds"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["writing_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["writing_task_assignments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["writing_submissions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id"),
    )
    op.create_index("ix_writing_attempts_user_status", "writing_attempts", ["user_id", "status"])
    op.create_index(
        "ix_writing_attempts_user_created", "writing_attempts", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("writing_attempts")
    for column in (
        "help_content_is_fixture",
        "help_content_generated_at",
        "help_content_model",
        "help_content_version",
        "help_content_json",
    ):
        op.drop_column("writing_tasks", column)
    attempt_status.drop(op.get_bind(), checkfirst=True)
    attempt_type.drop(op.get_bind(), checkfirst=True)
