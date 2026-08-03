import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage import AIUsage
from app.models.enums import UserRole, WritingAttemptStatus, WritingAttemptType
from app.models.user import User
from app.models.writing_attempt import WritingAttempt
from app.models.writing_evaluation import WritingEvaluation
from app.models.writing_submission import WritingSubmission
from app.models.writing_task import WritingTask
from app.models.writing_task_assignment import WritingTaskAssignment


def _register_and_login(client: TestClient, email: str) -> dict[str, str]:
    password = "correct-horse-battery-staple"
    registration = {
        "email": email,
        "password": password,
        "first_name": email.split("@")[0],
        "current_celpip_score": 7,
        "target_celpip_score": 10,
    }
    assert client.post("/auth/register", json=registration).status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _admin_headers(
    client: TestClient, db_session: AsyncSession
) -> dict[str, str]:
    headers = _register_and_login(client, "report-admin@example.com")
    admin = await db_session.scalar(
        select(User).where(User.email == "report-admin@example.com")
    )
    assert admin is not None
    admin.role = UserRole.ADMIN
    await db_session.commit()
    return headers


async def test_user_summary_is_admin_only(
    client: TestClient, db_session: AsyncSession
) -> None:
    student_headers = _register_and_login(client, "summary-student@example.com")
    assert client.get("/admin/users/summary", headers=student_headers).status_code == 403
    student = await db_session.scalar(
        select(User).where(User.email == "summary-student@example.com")
    )
    assert student is not None
    assert client.get(f"/admin/users/{student.id}", headers=student_headers).status_code == 403

    admin_headers = await _admin_headers(client, db_session)
    response = client.get("/admin/users/summary", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert client.get(f"/admin/users/{uuid.uuid4()}", headers=admin_headers).status_code == 404


async def test_user_summary_aggregates_practice_scores_and_ai_usage(
    client: TestClient,
    db_session: AsyncSession,
    writing_task: WritingTask,
) -> None:
    admin_headers = await _admin_headers(client, db_session)
    _register_and_login(client, "student-report@example.com")
    student = await db_session.scalar(
        select(User).where(User.email == "student-report@example.com")
    )
    assert student is not None

    started_at = datetime(2026, 8, 3, 12, tzinfo=UTC)
    submitted_at = started_at + timedelta(seconds=900)
    assignment = WritingTaskAssignment(
        user=student,
        task=writing_task,
        family_id=writing_task.family_id,
    )
    submission = WritingSubmission(
        user=student,
        task=writing_task,
        answer_text="A concise guided-practice response.",
        word_count=5,
        submitted_at=submitted_at,
    )
    attempt = WritingAttempt(
        user=student,
        task=writing_task,
        assignment=assignment,
        submission=submission,
        help_mode_enabled=True,
        attempt_type=WritingAttemptType.GUIDED_PRACTICE,
        status=WritingAttemptStatus.SUBMITTED,
        preparation_started_at=started_at,
        preparation_expires_at=started_at + timedelta(seconds=59),
        writing_started_at=started_at + timedelta(seconds=59),
        writing_expires_at=started_at + timedelta(seconds=1_659),
        submitted_at=submitted_at,
        answer_text=submission.answer_text,
        word_count=submission.word_count,
    )
    evaluation = WritingEvaluation(
        submission=submission,
        estimated_score=Decimal("9.0"),
        task_fulfillment_score=Decimal("9.0"),
        organization_score=Decimal("9.0"),
        vocabulary_score=Decimal("9.0"),
        grammar_score=Decimal("9.0"),
        score_gap=Decimal("1.0"),
        strengths=["Clear structure"],
        weaknesses=["Add detail"],
        corrections=[],
        recommended_exercises=[],
        weakness_signals=[],
        next_objective={},
        previous_objective_assessment={},
        evaluator_prompt_version="test.v1",
        ai_raw_response={},
    )
    usage = AIUsage(
        user=student,
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        estimated_cost=Decimal("0.001500"),
        request_type="evaluation",
        created_at=submitted_at,
    )
    db_session.add_all([assignment, submission, attempt, evaluation, usage])
    await db_session.commit()

    response = client.get(
        "/admin/users/summary?search=student-report", headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["email"] == "student-report@example.com"
    assert item["assigned_exercises"] == 1
    assert item["attempts_started"] == 1
    assert item["active_attempts"] == 0
    assert item["exercises_completed"] == 1
    assert item["guided_practice_completed"] == 1
    assert item["test_simulation_completed"] == 0
    assert item["total_practice_seconds"] == 900
    assert item["average_guided_score"] == 9.0
    assert item["average_test_score"] is None
    assert item["ai_request_count"] == 1
    assert item["input_tokens"] == 100
    assert item["output_tokens"] == 50
    assert item["total_tokens"] == 150
    assert item["estimated_cost_usd"] == 0.0015

    detail_response = client.get(f"/admin/users/{student.id}", headers=admin_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["summary"]["email"] == "student-report@example.com"
    assert detail["summary"]["total_practice_seconds"] == 900
    assert len(detail["recent_attempts"]) == 1
    recent_attempt = detail["recent_attempts"][0]
    assert recent_attempt["task_type"] == writing_task.task_type
    assert recent_attempt["category"] == writing_task.category
    assert recent_attempt["status"] == "SUBMITTED"
    assert recent_attempt["attempt_type"] == "GUIDED_PRACTICE"
    assert recent_attempt["help_mode_enabled"] is True
    assert recent_attempt["elapsed_seconds"] == 900
    assert recent_attempt["word_count"] == 5
    assert recent_attempt["estimated_score"] == 9.0
    assert detail["ai_usage_breakdown"] == [
        {
            "request_type": "evaluation",
            "model": "test-model",
            "request_count": 1,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost_usd": 0.0015,
        }
    ]
