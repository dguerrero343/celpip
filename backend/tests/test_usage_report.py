from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.openai_costs import OpenAICostReport, get_organization_costs_provider
from app.main import app
from app.models.ai_usage import AIUsage
from app.models.enums import UserRole
from app.models.user import User


def _register_and_login(client: TestClient, email: str) -> dict[str, str]:
    password = "correct-horse-battery-staple"
    assert client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": email.split("@")[0],
            "target_celpip_score": 10,
        },
    ).status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


class FakeCostsProvider:
    async def get_costs(self, *, start_date: date, end_date: date) -> OpenAICostReport:
        del start_date, end_date
        return OpenAICostReport(
            total_cost=Decimal("0.012000"),
            daily_costs={date.today(): Decimal("0.012000")},
            currency="usd",
        )


async def test_student_usage_report_is_limited_to_own_calls(
    client: TestClient, db_session: AsyncSession
) -> None:
    student_headers = _register_and_login(client, "usage-student@example.com")
    _register_and_login(client, "other-usage@example.com")
    students = (await db_session.scalars(select(User).order_by(User.email))).all()
    for index, user in enumerate(students, start=1):
        db_session.add(
            AIUsage(
                user_id=user.id,
                model="gpt-5-mini",
                input_tokens=100 * index,
                output_tokens=20 * index,
                estimated_cost=Decimal("0.001000") * index,
                request_type="writing_evaluation",
            )
        )
    await db_session.commit()

    response = client.get("/usage/report", headers=student_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "personal"
    assert body["totals"]["request_count"] == 1
    assert body["totals"]["input_tokens"] == 200
    assert body["totals"]["estimated_cost_usd"] == 0.002
    assert body["by_user"] == []
    assert body["provider"]["status"] == "personal_scope"


async def test_admin_usage_report_compares_openai_billed_costs(
    client: TestClient, db_session: AsyncSession
) -> None:
    admin_headers = _register_and_login(client, "owner@example.com")
    _register_and_login(client, "student@example.com")
    users = (await db_session.scalars(select(User).order_by(User.email))).all()
    admin = next(user for user in users if user.email == "owner@example.com")
    admin.role = UserRole.ADMIN
    for user in users:
        db_session.add(
            AIUsage(
                user_id=user.id,
                model="gpt-5-mini",
                input_tokens=500,
                output_tokens=100,
                estimated_cost=Decimal("0.003000"),
                request_type="writing_evaluation",
            )
        )
    await db_session.commit()
    app.dependency_overrides[get_organization_costs_provider] = lambda: FakeCostsProvider()

    response = client.get("/usage/report", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "organization"
    assert body["totals"]["request_count"] == 2
    assert body["totals"]["total_tokens"] == 1200
    assert body["totals"]["estimated_cost_usd"] == 0.006
    assert len(body["by_user"]) == 2
    assert body["provider"]["status"] == "available"
    assert body["provider"]["billed_cost_usd"] == 0.012
    assert body["provider"]["difference_usd"] == 0.006


def test_usage_report_requires_authentication(client: TestClient) -> None:
    assert client.get("/usage/report").status_code == 401

