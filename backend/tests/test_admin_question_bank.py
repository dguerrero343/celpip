from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.question_generator import (
    GeneratedQuestion,
    QuestionGenerationOutput,
    get_question_generator,
)
from app.main import app
from app.models.ai_usage import AIUsage
from app.models.enums import UserRole, WritingTaskSource, WritingTaskStatus
from app.models.user import User
from app.models.writing_task import WritingTask


def _register_and_login(client: TestClient, email: str) -> dict[str, str]:
    password = "correct-horse-battery-staple"
    assert client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Administrator",
            "target_celpip_score": 10,
        },
    ).status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _admin_headers(
    client: TestClient, db_session: AsyncSession
) -> dict[str, str]:
    headers = _register_and_login(client, "admin@example.com")
    admin = await db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin is not None
    admin.role = UserRole.ADMIN
    await db_session.commit()
    return headers


def _valid_task() -> dict[str, object]:
    return {
        "task_type": "EMAIL",
        "category": "Community",
        "difficulty": "INTERMEDIATE",
        "scenario_key": "community-recreation-hours",
        "focus_tags": ["TONE", "TASK_COMPLETENESS"],
        "target_score_min": 5,
        "target_score_max": 12,
        "prompt": (
            "Your community centre has reduced its evening hours. Write an email to the "
            "centre manager. Describe how you use the centre, explain how the new hours "
            "affect residents, and suggest a practical schedule. Write 150–200 words."
        ),
    }


async def test_admin_gate_and_question_lifecycle(
    client: TestClient, db_session: AsyncSession
) -> None:
    student_headers = _register_and_login(client, "student-admin-test@example.com")
    assert client.get("/admin/question-bank", headers=student_headers).status_code == 403
    assert client.get("/admin/evaluation-consistency", headers=student_headers).status_code == 403
    admin_headers = await _admin_headers(client, db_session)
    consistency = client.get("/admin/evaluation-consistency", headers=admin_headers)
    assert consistency.status_code == 200
    assert consistency.json()["metrics"] == []

    created = client.post("/admin/question-bank", headers=admin_headers, json=_valid_task())
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "DRAFT"
    assert task["source"] == "HUMAN"

    student_catalog = client.get("/writing/tasks", headers=student_headers)
    assert all(item["id"] != task["id"] for item in student_catalog.json()["items"])
    assert client.get(f"/writing/tasks/{task['id']}", headers=student_headers).status_code == 404
    assert client.post(
        "/writing/submissions",
        headers=student_headers,
        json={"task_id": task["id"], "answer_text": "This draft must remain private."},
    ).status_code == 404

    review = client.post(
        f"/admin/question-bank/{task['id']}/status",
        headers=admin_headers,
        json={"status": "IN_REVIEW"},
    )
    assert review.status_code == 200
    approved = client.post(
        f"/admin/question-bank/{task['id']}/status",
        headers=admin_headers,
        json={"status": "APPROVED"},
    )
    assert approved.status_code == 200
    assert approved.json()["reviewed_at"] is not None

    student_catalog = client.get("/writing/tasks", headers=student_headers)
    assert any(item["id"] == task["id"] for item in student_catalog.json()["items"])

    summary = client.get("/admin/question-bank/summary", headers=admin_headers)
    assert summary.status_code == 200
    assert summary.json()["approved_tasks"] == 1


class FakeQuestionGenerator:
    async def generate(self, **_: object) -> QuestionGenerationOutput:
        return QuestionGenerationOutput(
            questions=(
                GeneratedQuestion(
                    category="Workplace",
                    scenario_key="workplace-training-choice",
                    prompt=(
                        "Your employer can offer either an online professional course or an "
                        "in-person workshop. Choose the option you support and explain why that "
                        "option is better for employees. Write 150–200 words."
                    ),
                    focus_tags=["CONTENT_DEVELOPMENT", "ORGANIZATION"],
                    target_score_min=5,
                    target_score_max=12,
                ),
            ),
            model="fake-generator",
            input_tokens=500,
            output_tokens=250,
            estimated_cost=Decimal("0.000625"),
        )


async def test_ai_generation_creates_drafts_and_records_usage(
    client: TestClient, db_session: AsyncSession
) -> None:
    headers = await _admin_headers(client, db_session)
    app.dependency_overrides[get_question_generator] = lambda: FakeQuestionGenerator()

    response = client.post(
        "/admin/question-bank/generate",
        headers=headers,
        json={"task_type": "SURVEY", "count": 1},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["status"] == "DRAFT"
    task = await db_session.scalar(select(WritingTask))
    assert task is not None
    assert task.source == WritingTaskSource.AI
    assert task.status == WritingTaskStatus.DRAFT
    assert await db_session.scalar(select(func.count(AIUsage.id))) == 1
    usage = await db_session.scalar(select(AIUsage))
    assert usage is not None
    assert usage.request_type == "question_generation"
