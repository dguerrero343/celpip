from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Difficulty, WritingTaskType
from app.models.writing_task import WritingTask


def _register_and_login(client: TestClient) -> dict[str, str]:
    password = "correct-horse-battery-staple"
    assert client.post(
        "/auth/register",
        json={
            "email": "no-repeat@example.com",
            "password": password,
            "first_name": "Writer",
            "target_celpip_score": 9,
        },
    ).status_code == 201
    login = client.post(
        "/auth/login", json={"email": "no-repeat@example.com", "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_next_task_never_repeats_and_reports_exhaustion(
    client: TestClient, db_session: AsyncSession, writing_task: WritingTask
) -> None:
    second = WritingTask(
        task_type=WritingTaskType.EMAIL,
        category="Community",
        difficulty=Difficulty.INTERMEDIATE,
        prompt=(
            "Write an email about a community program. Explain your concern, describe its "
            "impact, and suggest a solution. Write 150–200 words."
        ),
    )
    db_session.add(second)
    await db_session.commit()
    headers = _register_and_login(client)

    first_response = client.post(
        "/writing/tasks/next", headers=headers, json={"task_type": "EMAIL"}
    )
    second_response = client.post(
        "/writing/tasks/next", headers=headers, json={"task_type": "EMAIL"}
    )
    exhausted = client.post(
        "/writing/tasks/next", headers=headers, json={"task_type": "EMAIL"}
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["task"]["id"] != second_response.json()["task"]["id"]
    assert exhausted.status_code == 409
    assert "No unseen" in exhausted.json()["detail"]
