"""Seed the local read-only demo dashboard.

Revision ID: 20260801_0003
Revises: 20260801_0002
Create Date: 2026-08-01
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260801_0003"
down_revision: str | None = "20260801_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_USER_ID = "20000000-0000-4000-8000-000000000001"

SUBMISSIONS = (
    {
        "id": "30000000-0000-4000-8000-000000000001",
        "task_id": "10000000-0000-4000-8000-000000000001",
        "answer_text": (
            "Dear Building Manager, I am writing about the construction noise beside my "
            "apartment. Work regularly begins before 6:30 a.m., including drilling and heavy "
            "equipment. The noise wakes my family and makes it difficult for me to prepare for "
            "work. I understand that repairs are necessary, but I would appreciate a later start. "
            "Could noisy work begin after 8:00 a.m. on weekdays and 9:00 a.m. on weekends? A "
            "weekly schedule posted in the lobby would also help residents plan ahead. Thank you "
            "for considering a solution that supports both the project and the people living here. "
            "Sincerely, Alex"
        ),
        "word_count": 100,
        "submitted_at": "2026-07-18T14:00:00+00:00",
        "evaluation_id": "40000000-0000-4000-8000-000000000001",
        "estimated_score": 7.5,
        "task_fulfillment_score": 8.0,
        "organization_score": 7.5,
        "vocabulary_score": 7.0,
        "grammar_score": 7.5,
        "score_gap": 2.5,
        "strengths": [
            "The purpose and requested solution are immediately clear.",
            "The tone stays polite and appropriate for a building manager.",
        ],
        "weaknesses": [
            "Add one specific example of how the interrupted sleep affects daily performance.",
            "Use a wider range of linking phrases between the problem and proposed solution.",
        ],
        "corrections": [
            {
                "original": (
                    "The noise wakes my family and makes it difficult for me to prepare for work."
                ),
                "revised": (
                    "As a result, my family is woken early and I struggle to concentrate at work."
                ),
            }
        ],
        "recommended_exercises": [
            "Practise cause-and-effect transitions in a formal email.",
            "Expand two supporting details while staying within the word limit.",
        ],
    },
    {
        "id": "30000000-0000-4000-8000-000000000002",
        "task_id": "10000000-0000-4000-8000-000000000003",
        "answer_text": (
            "I support expanding public transit because reliable transportation benefits more "
            "residents every day. Longer service hours would help shift workers reach their jobs "
            "without paying for taxis, while more frequent buses would shorten commutes for "
            "students and families. Better transit can also reduce traffic and air pollution. For "
            "example, residents may choose the bus when they know it arrives every ten minutes. "
            "Parks are valuable, but our city already has several green spaces that are difficult "
            "to reach without a car. Improving transit first would make those parks and other "
            "services more accessible. Therefore, transit is the more practical and inclusive "
            "investment for the city."
        ),
        "word_count": 102,
        "submitted_at": "2026-07-29T15:30:00+00:00",
        "evaluation_id": "40000000-0000-4000-8000-000000000002",
        "estimated_score": 8.5,
        "task_fulfillment_score": 9.0,
        "organization_score": 8.5,
        "vocabulary_score": 8.0,
        "grammar_score": 8.5,
        "score_gap": 1.5,
        "strengths": [
            "A consistent position is supported with relevant benefits and an example.",
            "Paragraph flow is logical and the comparison with parks strengthens the argument.",
        ],
        "weaknesses": [
            "Develop the environmental benefit with a more concrete consequence.",
            "Replace a few repeated uses of transit with precise alternatives.",
        ],
        "corrections": [
            {
                "original": "Better transit can also reduce traffic and air pollution.",
                "revised": (
                    "A dependable network would reduce car trips, easing congestion and local "
                    "emissions."
                ),
            }
        ],
        "recommended_exercises": [
            "Write one evidence-rich paragraph using a claim, example, and consequence.",
            "Build a synonym bank for transportation and municipal services.",
        ],
    },
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO users (
                id, email, password_hash, first_name, current_celpip_score,
                target_celpip_score, target_exam_date, role, is_active, created_at
            ) VALUES (
                CAST(:id AS uuid), 'demo@local.invalid', 'demo-account-disabled', 'Alex', 9, 10,
                DATE '2026-10-24', CAST('STUDENT' AS user_role), false,
                TIMESTAMPTZ '2026-07-01 12:00:00+00'
            )
            """
        ),
        {"id": DEMO_USER_ID},
    )

    submission_statement = sa.text(
        """
        INSERT INTO writing_submissions (
            id, user_id, task_id, answer_text, word_count, submitted_at
        ) VALUES (
            CAST(:id AS uuid), CAST(:user_id AS uuid), CAST(:task_id AS uuid),
            :answer_text, :word_count, CAST(CAST(:submitted_at AS text) AS timestamptz)
        )
        """
    )
    evaluation_statement = sa.text(
        """
        INSERT INTO writing_evaluations (
            id, submission_id, estimated_score, task_fulfillment_score,
            organization_score, vocabulary_score, grammar_score, score_gap,
            strengths, weaknesses, corrections, recommended_exercises,
            ai_raw_response, created_at
        ) VALUES (
            CAST(:evaluation_id AS uuid), CAST(:id AS uuid), :estimated_score,
            :task_fulfillment_score, :organization_score, :vocabulary_score,
            :grammar_score, :score_gap, CAST(:strengths AS jsonb),
            CAST(:weaknesses AS jsonb), CAST(:corrections AS jsonb),
            CAST(:recommended_exercises AS jsonb), CAST(:ai_raw_response AS jsonb),
            CAST(CAST(:submitted_at AS text) AS timestamptz) + INTERVAL '2 minutes'
        )
        """
    )
    for item in SUBMISSIONS:
        params = {**item, "user_id": DEMO_USER_ID}
        bind.execute(submission_statement, params)
        params.update(
            strengths=json.dumps(item["strengths"]),
            weaknesses=json.dumps(item["weaknesses"]),
            corrections=json.dumps(item["corrections"]),
            recommended_exercises=json.dumps(item["recommended_exercises"]),
            ai_raw_response=json.dumps({"source": "demo_fixture", "provider_called": False}),
        )
        bind.execute(evaluation_statement, params)

    bind.execute(
        sa.text(
            """
            INSERT INTO ai_student_context (
                user_id, current_score, target_score, score_gap, main_weaknesses,
                grammar_focus, vocabulary_focus, recommended_strategy, updated_at
            ) VALUES (
                CAST(:user_id AS uuid), 8.5, 10.0, 1.5,
                CAST(:weaknesses AS jsonb), CAST(:grammar AS jsonb),
                CAST(:vocabulary AS jsonb), :strategy,
                TIMESTAMPTZ '2026-07-29 15:32:00+00'
            )
            """
        ),
        {
            "user_id": DEMO_USER_ID,
            "weaknesses": json.dumps(["Supporting detail", "Vocabulary range"]),
            "grammar": json.dumps(["Complex sentence control", "Cause-and-effect clauses"]),
            "vocabulary": json.dumps(["Municipal services", "Formal transitions"]),
            "strategy": (
                "Plan one clear position, support each reason with a concrete consequence, "
                "and reserve two minutes to check sentence variety."
            ),
        },
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_score_history (id, user_id, skill, score, date) VALUES
                ('50000000-0000-4000-8000-000000000001', CAST(:user_id AS uuid),
                 CAST('WRITING' AS celpip_skill), 7.0, DATE '2026-07-04'),
                ('50000000-0000-4000-8000-000000000002', CAST(:user_id AS uuid),
                 CAST('WRITING' AS celpip_skill), 7.5, DATE '2026-07-18'),
                ('50000000-0000-4000-8000-000000000003', CAST(:user_id AS uuid),
                 CAST('WRITING' AS celpip_skill), 8.5, DATE '2026-07-29')
            """
        ),
        {"user_id": DEMO_USER_ID},
    )

    # Repair the punctuation in catalogs created from early Windows-encoded fixtures.
    bind.execute(
        sa.text(
            """
            UPDATE writing_tasks
            SET prompt = replace(prompt, '150â€“200', '150–200')
            WHERE prompt LIKE '%150â€“200%'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM users WHERE id = '{DEMO_USER_ID}'"  # noqa: S608
    )
