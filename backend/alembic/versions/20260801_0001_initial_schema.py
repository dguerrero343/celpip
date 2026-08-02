"""Create the phase-one CELPIP platform schema.

Revision ID: 20260801_0001
Revises: None
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260801_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM("STUDENT", "ADMIN", name="user_role", create_type=False)
writing_task_type = postgresql.ENUM("EMAIL", "SURVEY", name="writing_task_type", create_type=False)
task_difficulty = postgresql.ENUM(
    "BEGINNER", "INTERMEDIATE", "ADVANCED", name="task_difficulty", create_type=False
)
celpip_skill = postgresql.ENUM("WRITING", name="celpip_skill", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    writing_task_type.create(bind, checkfirst=True)
    task_difficulty.create(bind, checkfirst=True)
    celpip_skill.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("current_celpip_score", sa.SmallInteger(), nullable=True),
        sa.Column("target_celpip_score", sa.SmallInteger(), nullable=True),
        sa.Column("target_exam_date", sa.Date(), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="STUDENT"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "current_celpip_score IS NULL OR current_celpip_score BETWEEN 1 AND 12",
            name="ck_users_current_score_range",
        ),
        sa.CheckConstraint(
            "target_celpip_score IS NULL OR target_celpip_score BETWEEN 1 AND 12",
            name="ck_users_target_score_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "writing_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_type", writing_task_type, nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("difficulty", task_difficulty, nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_writing_tasks"),
    )
    op.create_index("ix_writing_tasks_task_type", "writing_tasks", ["task_type"])
    op.create_index("ix_writing_tasks_category", "writing_tasks", ["category"])
    op.create_index("ix_writing_tasks_difficulty", "writing_tasks", ["difficulty"])

    op.create_table(
        "writing_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("word_count >= 0", name="ck_writing_submissions_nonnegative_word_count"),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["writing_tasks.id"],
            name="fk_writing_submissions_task_id_writing_tasks",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_writing_submissions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_writing_submissions"),
    )
    op.create_index(
        "ix_writing_submissions_user_submitted",
        "writing_submissions",
        ["user_id", "submitted_at"],
    )

    op.create_table(
        "writing_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("estimated_score", sa.Numeric(3, 1), nullable=False),
        sa.Column("task_fulfillment_score", sa.Numeric(3, 1), nullable=False),
        sa.Column("organization_score", sa.Numeric(3, 1), nullable=False),
        sa.Column("vocabulary_score", sa.Numeric(3, 1), nullable=False),
        sa.Column("grammar_score", sa.Numeric(3, 1), nullable=False),
        sa.Column("score_gap", sa.Numeric(3, 1), nullable=False),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("corrections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommended_exercises", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ai_raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "estimated_score BETWEEN 1 AND 12",
            name="ck_writing_evaluations_estimated_score_range",
        ),
        sa.CheckConstraint(
            "task_fulfillment_score BETWEEN 1 AND 12",
            name="ck_writing_evaluations_task_score_range",
        ),
        sa.CheckConstraint(
            "organization_score BETWEEN 1 AND 12",
            name="ck_writing_evaluations_organization_score_range",
        ),
        sa.CheckConstraint(
            "vocabulary_score BETWEEN 1 AND 12",
            name="ck_writing_evaluations_vocabulary_score_range",
        ),
        sa.CheckConstraint(
            "grammar_score BETWEEN 1 AND 12",
            name="ck_writing_evaluations_grammar_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["writing_submissions.id"],
            name="fk_writing_evaluations_submission_id_writing_submissions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_writing_evaluations"),
        sa.UniqueConstraint("submission_id", name="uq_writing_evaluations_submission_id"),
    )

    op.create_table(
        "ai_student_context",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("current_score", sa.Numeric(3, 1), nullable=False),
        sa.Column("target_score", sa.Numeric(3, 1), nullable=False),
        sa.Column("score_gap", sa.Numeric(3, 1), nullable=False),
        sa.Column("main_weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("grammar_focus", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("vocabulary_focus", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommended_strategy", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "current_score BETWEEN 1 AND 12", name="ck_ai_student_context_current_score_range"
        ),
        sa.CheckConstraint(
            "target_score BETWEEN 1 AND 12", name="ck_ai_student_context_target_score_range"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_student_context_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_ai_student_context"),
    )

    op.create_table(
        "user_score_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("skill", celpip_skill, nullable=False),
        sa.Column("score", sa.Numeric(3, 1), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "score BETWEEN 1 AND 12", name="ck_user_score_history_score_range"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_score_history_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_score_history"),
    )
    op.create_index(
        "ix_user_score_history_user_date", "user_score_history", ["user_id", "date"]
    )

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("request_type", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("input_tokens >= 0", name="ck_ai_usage_nonnegative_input_tokens"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_ai_usage_nonnegative_output_tokens"),
        sa.CheckConstraint(
            "estimated_cost >= 0", name="ck_ai_usage_nonnegative_estimated_cost"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_usage_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_usage"),
    )
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("user_score_history")
    op.drop_table("ai_student_context")
    op.drop_table("writing_evaluations")
    op.drop_table("writing_submissions")
    op.drop_table("writing_tasks")
    op.drop_table("users")

    bind = op.get_bind()
    celpip_skill.drop(bind, checkfirst=True)
    task_difficulty.drop(bind, checkfirst=True)
    writing_task_type.drop(bind, checkfirst=True)
    user_role.drop(bind, checkfirst=True)
