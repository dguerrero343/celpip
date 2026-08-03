from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_student_context import AIStudentContext
from app.models.enums import Difficulty, WritingTaskStatus, WritingTaskType
from app.models.user import User
from app.models.writing_submission import WritingSubmission
from app.models.writing_task import WritingTask
from app.services.demo_service import DEMO_USER_ID


async def test_demo_dashboard_serializes_legacy_submission_without_attempt(
    client: TestClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "demo_mode", True)
    user = User(
        id=DEMO_USER_ID,
        email="demo@local.invalid",
        password_hash="disabled",
        first_name="Demo",
        current_celpip_score=8,
        target_celpip_score=10,
    )
    context = AIStudentContext(
        user=user,
        current_score=Decimal("8.0"),
        target_score=Decimal("10.0"),
        score_gap=Decimal("2.0"),
        main_weaknesses=["organization"],
        grammar_focus=["sentence variety"],
        vocabulary_focus=["formal requests"],
        recommended_strategy="Use a clear paragraph plan.",
    )
    task = WritingTask(
        task_type=WritingTaskType.EMAIL,
        category="Community",
        difficulty=Difficulty.INTERMEDIATE,
        status=WritingTaskStatus.APPROVED,
        prompt="Write an email requesting information. Write 150-200 words.",
    )
    submission = WritingSubmission(
        user=user,
        task=task,
        answer_text="Please provide the requested information.",
        word_count=5,
    )
    db_session.add_all([user, context, task, submission])
    await db_session.commit()

    response = client.get("/demo/dashboard")

    assert response.status_code == 200
    assert response.json()["submissions"][0]["attempt_type"] == "TEST_SIMULATION"
