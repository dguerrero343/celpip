"""Allow only one active writing attempt per user.

Revision ID: 20260802_0006
Revises: 20260802_0005
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260802_0006"
down_revision: str | None = "20260802_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY user_id ORDER BY created_at DESC, id DESC
            ) AS position
            FROM writing_attempts
            WHERE status IN ('PREPARING', 'WRITING')
        )
        UPDATE writing_attempts
        SET status = 'EXPIRED'
        WHERE id IN (SELECT id FROM ranked WHERE position > 1)
        """
    )
    op.create_index(
        "uq_writing_attempts_one_active_per_user",
        "writing_attempts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PREPARING', 'WRITING')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_writing_attempts_one_active_per_user",
        table_name="writing_attempts",
        postgresql_where=sa.text("status IN ('PREPARING', 'WRITING')"),
    )
