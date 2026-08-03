import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.help_generator import (
    HELP_CONTENT_VERSION,
    HelpGenerationOutput,
    WritingHelpContent,
    demo_help_content,
    get_help_generator,
)
from app.main import app
from app.models.enums import Difficulty, WritingAttemptStatus, WritingTaskType
from app.models.writing_attempt import WritingAttempt
from app.models.writing_task import WritingTask


def auth(client: TestClient, email: str) -> dict[str, str]:
    password = "correct-horse-battery-staple"
    assert (
        client.post(
            "/auth/register",
            json={
                "email": email,
                "password": password,
                "first_name": "Writer",
                "target_celpip_score": 12,
            },
        ).status_code
        == 201
    )
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def start(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/writing/attempts", headers=headers, json={"task_type": "EMAIL"})
    assert response.status_code == 201
    return response.json()


async def test_only_one_writing_attempt_can_be_active(
    client: TestClient, db_session: AsyncSession, writing_task: WritingTask
) -> None:
    survey = WritingTask(
        task_type=WritingTaskType.SURVEY,
        category="Community",
        difficulty=Difficulty.INTERMEDIATE,
        prompt="Choose one community improvement and explain your reasons. Write 150–200 words.",
    )
    db_session.add(survey)
    await db_session.commit()
    headers = auth(client, "one-at-a-time@example.com")

    first = start(client, headers)
    same_task = client.post("/writing/attempts", headers=headers, json={"task_type": "EMAIL"})
    blocked = client.post("/writing/attempts", headers=headers, json={"task_type": "SURVEY"})

    assert same_task.status_code == 201
    assert same_task.json()["id"] == first["id"]
    assert blocked.status_code == 409
    assert "Task 1 is already in progress" in blocked.json()["detail"]
    attempts = list((await db_session.scalars(select(WritingAttempt))).all())
    assert len(attempts) == 1

    attempts[0].status = WritingAttemptStatus.EXPIRED
    await db_session.commit()
    next_task = client.post("/writing/attempts", headers=headers, json={"task_type": "SURVEY"})
    assert next_task.status_code == 201
    assert next_task.json()["task"]["task_type"] == "SURVEY"


async def begin_writing(db_session: AsyncSession, attempt_id: str) -> None:
    attempt = await db_session.scalar(
        select(WritingAttempt).where(WritingAttempt.id == uuid.UUID(attempt_id))
    )
    assert attempt is not None
    now = datetime.now(UTC)
    attempt.preparation_expires_at = now - timedelta(seconds=1)
    attempt.writing_started_at = now - timedelta(seconds=1)
    attempt.status = WritingAttemptStatus.WRITING
    await db_session.commit()


async def test_help_mode_is_saved_and_locked_when_writing_starts(
    client: TestClient, db_session: AsyncSession, writing_task: WritingTask
) -> None:
    headers = auth(client, "mode@example.com")
    attempt = start(client, headers)
    enabled = client.patch(
        f"/writing/attempts/{attempt['id']}/mode", headers=headers, json={"help_mode_enabled": True}
    )
    assert enabled.status_code == 200
    assert enabled.json()["help_mode_enabled"] is True
    assert enabled.json()["attempt_type"] == "GUIDED_PRACTICE"

    await begin_writing(db_session, attempt["id"])
    locked = client.patch(
        f"/writing/attempts/{attempt['id']}/mode",
        headers=headers,
        json={"help_mode_enabled": False},
    )
    assert locked.status_code == 409
    restored = client.get(f"/writing/attempts/{attempt['id']}", headers=headers).json()
    assert restored["help_mode_enabled"] is True
    assert restored["writing_expires_at"] == enabled.json()["writing_expires_at"]


async def test_standard_mode_never_exposes_help(
    client: TestClient, db_session: AsyncSession, writing_task: WritingTask
) -> None:
    headers = auth(client, "standard@example.com")
    attempt = start(client, headers)
    await begin_writing(db_session, attempt["id"])
    response = client.get(f"/writing/attempts/{attempt['id']}/help", headers=headers)
    assert response.status_code == 404


class FakeHelpGenerator:
    def __init__(self, task: WritingTask) -> None:
        self.calls = 0
        self.task = task

    async def generate(self, **kwargs) -> HelpGenerationOutput:
        self.calls += 1
        content = demo_help_content(WritingTaskType.EMAIL, self.task.category, self.task.prompt)
        return HelpGenerationOutput(content, "fake-help-model", 120, 300, Decimal("0.000200"))


async def test_guided_help_is_generated_once_cached_and_returned(
    client: TestClient, db_session: AsyncSession, writing_task: WritingTask
) -> None:
    generator = FakeHelpGenerator(writing_task)
    writing_task.help_content_json = demo_help_content(
        WritingTaskType.EMAIL, writing_task.category, writing_task.prompt
    ).model_dump(mode="json")
    writing_task.help_content_version = HELP_CONTENT_VERSION
    writing_task.help_content_model = "demo-fixture"
    writing_task.help_content_is_fixture = True
    await db_session.commit()
    app.dependency_overrides[get_help_generator] = lambda: generator
    headers = auth(client, "guided@example.com")
    attempt = start(client, headers)
    assert (
        client.patch(
            f"/writing/attempts/{attempt['id']}/mode",
            headers=headers,
            json={"help_mode_enabled": True},
        ).status_code
        == 200
    )
    await begin_writing(db_session, attempt["id"])

    first = client.get(f"/writing/attempts/{attempt['id']}/help", headers=headers)
    second = client.get(f"/writing/attempts/{attempt['id']}/help", headers=headers)
    assert first.status_code == second.status_code == 200
    assert len(first.json()["content"]["sentence_frameworks"]) == 6
    assert generator.calls == 1
    await db_session.refresh(writing_task)
    assert writing_task.help_content_model == "fake-help-model"


async def test_autosave_refresh_ownership_and_separate_progress(
    client: TestClient, db_session: AsyncSession, writing_task: WritingTask
) -> None:
    owner = auth(client, "attempt-owner@example.com")
    other = auth(client, "attempt-other@example.com")
    attempt = start(client, owner)
    client.patch(
        f"/writing/attempts/{attempt['id']}/mode", headers=owner, json={"help_mode_enabled": True}
    )
    await begin_writing(db_session, attempt["id"])
    payload = {
        "answer_text": "A restored autosaved response with useful details.",
        "help_sections_opened": ["structure", "vocabulary"],
        "help_panel_open_count": 2,
        "help_visible_seconds": 14,
    }
    saved = client.patch(f"/writing/attempts/{attempt['id']}/autosave", headers=owner, json=payload)
    assert saved.status_code == 200
    restored = client.get(f"/writing/attempts/{attempt['id']}", headers=owner)
    assert restored.json()["answer_text"] == payload["answer_text"]
    assert restored.json()["help_sections_opened"] == ["structure", "vocabulary"]
    assert client.get(f"/writing/attempts/{attempt['id']}", headers=other).status_code == 404

    submitted = client.post(
        f"/writing/attempts/{attempt['id']}/submit", headers=owner, json=payload
    )
    assert submitted.status_code == 200
    assert submitted.json()["submission"]["attempt_type"] == "GUIDED_PRACTICE"
    progress = client.get("/writing/progress", headers=owner).json()
    assert progress["guided_practice"]["total_submissions"] == 1
    assert progress["test_simulation"]["total_submissions"] == 0


def test_invalid_ai_output_is_rejected_safely() -> None:
    invalid = demo_help_content(
        WritingTaskType.EMAIL, "Workplace", "Explain your request."
    ).model_dump()
    invalid["sentence_frameworks"] = invalid["sentence_frameworks"][:2]
    invalid["recommended_structure"][0]["guidance"] = "<script>alert('x')</script>"
    with pytest.raises(ValidationError):
        WritingHelpContent.model_validate(invalid)
