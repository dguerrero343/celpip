import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ai_provider import EvaluationInput, EvaluationOutput
from app.ai.dependencies import get_ai_provider
from app.main import app
from app.models.ai_student_context import AIStudentContext
from app.models.ai_usage import AIUsage
from app.models.enums import (
    LearningObjectiveStatus,
    WeaknessTrend,
    WritingAttemptType,
)
from app.models.user import User
from app.models.user_score_history import UserScoreHistory
from app.models.writing_learning_objective import WritingLearningObjective
from app.models.writing_task import WritingTask
from app.models.writing_weakness_observation import WritingWeaknessObservation
from app.services.learning_profile_service import get_persistent_weaknesses


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
            weakness_signals=(
                {
                    "skill": "grammar",
                    "issue_key": "article_usage",
                    "label": "Grammar: review article usage",
                },
                {
                    "skill": "vocabulary",
                    "issue_key": "vocabulary_repetition",
                    "label": "Vocabulary repetition",
                },
            ),
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
            next_objective={
                "skill": "grammar",
                "objective": "Use articles accurately with every singular count noun.",
                "success_criteria": "No more than one article error in the next response.",
            },
            previous_objective_assessment={
                "status": (
                    "ACHIEVED" if request.previous_objective is not None else "NOT_APPLICABLE"
                ),
                "explanation": "The current response provides enough evidence for comparison.",
            },
            evaluator_prompt_version="2026-08-02.v2",
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

    response = client.post(f"/writing/submissions/{created['id']}/evaluation", headers=headers)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "60"


async def test_evaluation_updates_history_context_usage_and_progress(
    client: TestClient, writing_task: WritingTask, db_session: AsyncSession
) -> None:
    provider = FakeEvaluationProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    headers = _register_and_login(client, "evaluated-writer@example.com")
    created = _submit(client, headers, str(writing_task.id))

    first = client.post(f"/writing/submissions/{created['id']}/evaluation", headers=headers)
    app.dependency_overrides[get_ai_provider] = lambda: None
    second = client.post(f"/writing/submissions/{created['id']}/evaluation", headers=headers)

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
        "test_simulation": {
            "total_submissions": 1,
            "evaluated_submissions": 1,
            "average_score": 8.5,
            "best_score": 8.5,
            "last_evaluated_at": progress.json()["last_evaluated_at"],
        },
        "guided_practice": {
            "total_submissions": 0,
            "evaluated_submissions": 0,
            "average_score": None,
            "best_score": None,
            "last_evaluated_at": None,
        },
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

    response = client.post(f"/writing/submissions/{created['id']}/evaluation", headers=headers)

    assert response.status_code == 409
    assert provider.requests == []


async def test_evaluation_carries_objective_forward_and_records_weakness_trends(
    client: TestClient, writing_task: WritingTask, db_session: AsyncSession
) -> None:
    provider = FakeEvaluationProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    headers = _register_and_login(client, "rolling-profile@example.com")

    first_submission = _submit(client, headers, str(writing_task.id))
    first = client.post(
        f"/writing/submissions/{first_submission['id']}/evaluation", headers=headers
    )
    second_submission = _submit(client, headers, str(writing_task.id))
    second = client.post(
        f"/writing/submissions/{second_submission['id']}/evaluation", headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["evaluator_prompt_version"] == "2026-08-02.v2"
    assert first.json()["next_objective"]["skill"] == "grammar"
    assert provider.requests[0].previous_objective is None
    assert provider.requests[1].previous_objective == first.json()["next_objective"]
    assert provider.requests[1].weaknesses == (
        "Grammar: review article usage",
        "Vocabulary repetition",
    )

    objectives = list(
        (
            await db_session.scalars(
                select(WritingLearningObjective).order_by(
                    WritingLearningObjective.created_at,
                    WritingLearningObjective.source_submission_id,
                )
            )
        ).all()
    )
    assert len(objectives) == 2
    assert {item.status for item in objectives} == {
        LearningObjectiveStatus.ACHIEVED,
        LearningObjectiveStatus.PENDING,
    }
    assessed = next(item for item in objectives if item.status == LearningObjectiveStatus.ACHIEVED)
    assert assessed.assessed_submission_id is not None

    observations = list((await db_session.scalars(select(WritingWeaknessObservation))).all())
    assert len(observations) == 4
    assert {item.trend for item in observations} == {
        WeaknessTrend.NEW,
        WeaknessTrend.STABLE,
    }


async def test_test_simulation_evidence_outweighs_guided_frequency(
    client: TestClient, writing_task: WritingTask, db_session: AsyncSession
) -> None:
    headers = _register_and_login(client, "profile-weighting@example.com")
    first = _submit(client, headers, str(writing_task.id))
    second = _submit(client, headers, str(writing_task.id))
    third = _submit(client, headers, str(writing_task.id))
    user = await db_session.scalar(
        select(User).where(User.email == "profile-weighting@example.com")
    )
    assert user is not None

    for submission in (first, second):
        db_session.add(
            WritingWeaknessObservation(
                user_id=user.id,
                submission_id=uuid.UUID(str(submission["id"])),
                weakness_key="guided_issue",
                weakness_label="Guided issue",
                skill="organization",
                trend=WeaknessTrend.STABLE,
                is_present=True,
                attempt_type=WritingAttemptType.GUIDED_PRACTICE,
                rubric_score=7,
            )
        )
    db_session.add(
        WritingWeaknessObservation(
            user_id=user.id,
            submission_id=uuid.UUID(str(third["id"])),
            weakness_key="test_issue",
            weakness_label="Test issue",
            skill="grammar",
            trend=WeaknessTrend.STABLE,
            is_present=True,
            attempt_type=WritingAttemptType.TEST_SIMULATION,
            rubric_score=7,
        )
    )
    await db_session.commit()

    profile = await get_persistent_weaknesses(db_session, user_id=user.id)

    assert profile[0].key == "test_issue"
    guided = next(item for item in profile if item.key == "guided_issue")
    assert guided.guided_practice_frequency == 2
    assert guided.test_simulation_frequency == 0
