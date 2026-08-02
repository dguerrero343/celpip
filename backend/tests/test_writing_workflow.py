from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ai_provider import EvaluationInput, EvaluationOutput
from app.ai.dependencies import get_ai_provider
from app.main import app
from app.models.ai_student_context import AIStudentContext
from app.models.ai_usage import AIUsage
from app.models.user_score_history import UserScoreHistory
from app.models.writing_task import WritingTask


class FakeEvaluationProvider:
    def __init__(self) -> None:
        self.requests: list[EvaluationInput] = []

    async def evaluate_writing(self, request: EvaluationInput) -> EvaluationOutput:
        self.requests.append(request)
        return EvaluationOutput(
            model="fake-celpip-evaluator",
            score=8.5,
            task_fulfillment=9,
            organization=8,
            vocabulary=8.5,
            grammar=8,
            strengths=("Clear purpose", "Professional tone"),
            weaknesses=("Grammar: review article usage", "Vocabulary repetition"),
            corrections=(
                {
                    "original": "I look forward to hear",
                    "revised": "I look forward to hearing",
                },
            ),
            recommended_next_steps=("Practice article usage.", "Vary transition words."),
            raw_response={"provider_request_id": "fake-123"},
            input_tokens=320,
            output_tokens=180,
            estimated_cost=Decimal("0.004200"),
        )


def _register_and_login(
    client: TestClient, email: str, *, target_score: int | None = 10
) -> dict[str, str]:
    registration = {
        "email": email,
        "password": "correct-horse-battery-staple",
        "first_name": "Writer",
        "current_celpip_score": 7,
        "target_celpip_score": target_score,
    }
    assert client.post("/auth/register", json=registration).status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": email, "password": registration["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _submit(client: TestClient, headers: dict[str, str], task_id: str) -> dict[str, object]:
    answer = (
        "Dear Manager, I am writing to request a flexible work schedule. "
        "Working from home twice a week would reduce my commute and help me focus. "
        "I will remain available during business hours and attend every required meeting. "
        "Thank you for considering this arrangement."
    )
    response = client.post(
        "/writing/submissions",
        headers=headers,
        json={"task_id": task_id, "answer_text": answer},
    )
    assert response.status_code == 201
    return response.json()


def test_writing_routes_require_authentication(client: TestClient) -> None:
    assert client.get("/writing/tasks").status_code == 401
    assert client.get("/writing/submissions").status_code == 401
    assert client.get("/writing/progress").status_code == 401


async def test_task_catalog_submission_and_history(
    client: TestClient, writing_task: WritingTask
) -> None:
    headers = _register_and_login(client, "catalog-writer@example.com")

    catalog = client.get(
        "/writing/tasks?task_type=EMAIL&difficulty=INTERMEDIATE&category=work",
        headers=headers,
    )
    assert catalog.status_code == 200
    assert catalog.json()["total"] == 1
    assert catalog.json()["items"][0]["id"] == str(writing_task.id)

    created = _submit(client, headers, str(writing_task.id))
    assert created["word_count"] == 43
    assert created["evaluation"] is None
    assert created["task"]["category"] == "Workplace"

    history = client.get("/writing/submissions", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == created["id"]

    detail = client.get(f"/writing/submissions/{created['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["answer_text"] == created["answer_text"]


async def test_submission_ownership_is_enforced(
    client: TestClient, writing_task: WritingTask
) -> None:
    owner_headers = _register_and_login(client, "owner@example.com")
    other_headers = _register_and_login(client, "other@example.com")
    created = _submit(client, owner_headers, str(writing_task.id))

    response = client.get(f"/writing/submissions/{created['id']}", headers=other_headers)

    assert response.status_code == 404


async def test_evaluation_requires_a_configured_provider(
    client: TestClient, writing_task: WritingTask
) -> None:
    headers = _register_and_login(client, "no-provider@example.com")
    created = _submit(client, headers, str(writing_task.id))

    response = client.post(
        f"/writing/submissions/{created['id']}/evaluation", headers=headers
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "60"


async def test_evaluation_updates_history_context_usage_and_progress(
    client: TestClient, writing_task: WritingTask, db_session: AsyncSession
) -> None:
    provider = FakeEvaluationProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    headers = _register_and_login(client, "evaluated-writer@example.com")
    created = _submit(client, headers, str(writing_task.id))

    first = client.post(
        f"/writing/submissions/{created['id']}/evaluation", headers=headers
    )
    app.dependency_overrides[get_ai_provider] = lambda: None
    second = client.post(
        f"/writing/submissions/{created['id']}/evaluation", headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["estimated_score"] == 8.5
    assert first.json()["score_gap"] == 1.5
    assert "ai_raw_response" not in first.json()
    assert len(provider.requests) == 1
    assert provider.requests[0].target_score == 10
    assert "flexible work schedule" in provider.requests[0].task_prompt

    progress = client.get("/writing/progress", headers=headers)
    assert progress.status_code == 200
    assert progress.json() == {
        "total_submissions": 1,
        "evaluated_submissions": 1,
        "current_score": 9.0,
        "target_score": 10.0,
        "average_score": 8.5,
        "best_score": 8.5,
        "last_evaluated_at": progress.json()["last_evaluated_at"],
    }
    assert progress.json()["last_evaluated_at"] is not None

    assert await db_session.scalar(select(func.count(AIUsage.id))) == 1
    assert await db_session.scalar(select(func.count(UserScoreHistory.id))) == 1
    context = await db_session.scalar(select(AIStudentContext))
    assert context is not None
    assert context.main_weaknesses == [
        "Grammar: review article usage",
        "Vocabulary repetition",
    ]


async def test_target_score_is_required_for_evaluation(
    client: TestClient, writing_task: WritingTask
) -> None:
    provider = FakeEvaluationProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    headers = _register_and_login(client, "no-target@example.com", target_score=None)
    created = _submit(client, headers, str(writing_task.id))

    response = client.post(
        f"/writing/submissions/{created['id']}/evaluation", headers=headers
    )

    assert response.status_code == 409
    assert provider.requests == []
