"""Seed the initial CELPIP writing task catalog.

Revision ID: 20260801_0002
Revises: 20260801_0001
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0002"
down_revision: str | None = "20260801_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TASKS = (
    {
        "id": "10000000-0000-4000-8000-000000000001",
        "task_type": "EMAIL",
        "category": "Community",
        "difficulty": "BEGINNER",
        "prompt": (
            "You recently moved into a new apartment, but loud construction begins very early "
            "each morning. Write an email to the building manager. Explain how the noise affects "
            "you, describe when it occurs, and suggest a reasonable solution. Write 150–200 words."
        ),
    },
    {
        "id": "10000000-0000-4000-8000-000000000002",
        "task_type": "EMAIL",
        "category": "Workplace",
        "difficulty": "INTERMEDIATE",
        "prompt": (
            "Your company has introduced a schedule that requires employees to work in the office "
            "five days a week. Write an email to your supervisor requesting a flexible "
            "arrangement. Explain your circumstances, show how your work will remain effective, "
            "and propose a specific schedule. Write 150–200 words."
        ),
    },
    {
        "id": "10000000-0000-4000-8000-000000000003",
        "task_type": "SURVEY",
        "category": "City Services",
        "difficulty": "INTERMEDIATE",
        "prompt": (
            "Your city has funding for one major improvement: expand public transit service or "
            "build more public parks. Choose the option you support. Explain your reasons and "
            "describe how residents would benefit. Write 150–200 words."
        ),
    },
    {
        "id": "10000000-0000-4000-8000-000000000004",
        "task_type": "SURVEY",
        "category": "Education",
        "difficulty": "ADVANCED",
        "prompt": (
            "A local college is deciding whether students should complete a work placement or an "
            "independent research project before graduation. Choose the better requirement. "
            "Support your position with reasons and examples. Write 150–200 words."
        ),
    },
)


def upgrade() -> None:
    statement = sa.text(
        """
        INSERT INTO writing_tasks (id, task_type, category, difficulty, prompt)
        VALUES (
            CAST(:id AS uuid),
            CAST(:task_type AS writing_task_type),
            :category,
            CAST(:difficulty AS task_difficulty),
            :prompt
        )
        """
    )
    bind = op.get_bind()
    for task in TASKS:
        bind.execute(statement, task)


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM writing_tasks
        WHERE id IN (
            '10000000-0000-4000-8000-000000000001',
            '10000000-0000-4000-8000-000000000002',
            '10000000-0000-4000-8000-000000000003',
            '10000000-0000-4000-8000-000000000004'
        )
        """
    )
