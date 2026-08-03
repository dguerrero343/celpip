"""Separate guided and test score history.

Revision ID: 20260802_0008
Revises: 20260802_0007
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260802_0008"
down_revision: str | None = "20260802_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_score_history",
        sa.Column(
            "attempt_type",
            postgresql.ENUM(name="writing_attempt_type", create_type=False),
            server_default="TEST_SIMULATION",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_score_history", "attempt_type")
