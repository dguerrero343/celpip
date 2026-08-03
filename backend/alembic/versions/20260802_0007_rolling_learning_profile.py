"""Add rolling writing learning profiles and versioned evaluations.

Revision ID: 20260802_0007
Revises: 20260802_0006
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260802_0007"
down_revision: str | None = "20260802_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    weakness_trend = postgresql.ENUM("NEW", "IMPROVED", "STABLE", "WORSENED", name="weakness_trend")
    objective_status = postgresql.ENUM(
        "PENDING",
        "ACHIEVED",
        "PARTIALLY_ACHIEVED",
        "NOT_ACHIEVED",
        name="learning_objective_status",
    )
    weakness_trend.create(op.get_bind(), checkfirst=True)
    objective_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "writing_evaluations",
        sa.Column(
            "weakness_signals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "writing_evaluations",
        sa.Column(
            "next_objective",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "writing_evaluations",
        sa.Column(
            "previous_objective_assessment",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "writing_evaluations",
        sa.Column(
            "evaluator_prompt_version",
            sa.String(length=40),
            server_default="legacy",
            nullable=False,
        ),
    )

    op.create_table(
        "writing_weakness_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("weakness_key", sa.String(length=80), nullable=False),
        sa.Column("weakness_label", sa.String(length=240), nullable=False),
        sa.Column("skill", sa.String(length=40), nullable=False),
        sa.Column(
            "trend",
            postgresql.ENUM(name="weakness_trend", create_type=False),
            nullable=False,
        ),
        sa.Column("is_present", sa.Boolean(), nullable=False),
        sa.Column(
            "attempt_type",
            postgresql.ENUM(name="writing_attempt_type", create_type=False),
            nullable=False,
        ),
        sa.Column("rubric_score", sa.Numeric(precision=3, scale=1), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["writing_submissions.id"],
            name=op.f("fk_writing_weakness_observations_submission_id_writing_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_writing_weakness_observations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_writing_weakness_observations")),
    )
    op.create_index(
        "ix_weakness_observations_user_created",
        "writing_weakness_observations",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_weakness_observations_user_key",
        "writing_weakness_observations",
        ["user_id", "weakness_key"],
    )

    op.create_table(
        "writing_learning_objectives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_submission_id", sa.Uuid(), nullable=False),
        sa.Column("assessed_submission_id", sa.Uuid(), nullable=True),
        sa.Column(
            "attempt_type",
            postgresql.ENUM(name="writing_attempt_type", create_type=False),
            nullable=False,
        ),
        sa.Column("skill", sa.String(length=40), nullable=False),
        sa.Column("objective", sa.String(length=300), nullable=False),
        sa.Column("success_criteria", sa.String(length=300), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="learning_objective_status", create_type=False),
            nullable=False,
        ),
        sa.Column("assessment_explanation", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assessed_submission_id"],
            ["writing_submissions.id"],
            name=op.f("fk_writing_learning_objectives_assessed_submission_id_writing_submissions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_submission_id"],
            ["writing_submissions.id"],
            name=op.f("fk_writing_learning_objectives_source_submission_id_writing_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_writing_learning_objectives_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_writing_learning_objectives")),
        sa.UniqueConstraint(
            "source_submission_id",
            name=op.f("uq_writing_learning_objectives_source_submission_id"),
        ),
    )
    op.create_index(
        op.f("ix_writing_learning_objectives_user_id"),
        "writing_learning_objectives",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_writing_learning_objectives_user_id"),
        table_name="writing_learning_objectives",
    )
    op.drop_table("writing_learning_objectives")
    op.drop_index("ix_weakness_observations_user_key", table_name="writing_weakness_observations")
    op.drop_index(
        "ix_weakness_observations_user_created", table_name="writing_weakness_observations"
    )
    op.drop_table("writing_weakness_observations")
    op.drop_column("writing_evaluations", "evaluator_prompt_version")
    op.drop_column("writing_evaluations", "previous_objective_assessment")
    op.drop_column("writing_evaluations", "next_objective")
    op.drop_column("writing_evaluations", "weakness_signals")
    postgresql.ENUM(name="learning_objective_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="weakness_trend").drop(op.get_bind(), checkfirst=True)
