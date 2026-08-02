import uuid

from fastapi.testclient import TestClient

from app.auth.tokens import create_access_token
from app.models.enums import UserRole

REGISTRATION = {
    "email": "Student@Example.com",
    "password": "correct-horse-battery-staple",
    "first_name": " Sam ",
    "current_celpip_score": 7,
    "target_celpip_score": 10,
    "target_exam_date": "2027-02-10",
}


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_login_and_read_current_user(client: TestClient) -> None:
    registration = client.post("/auth/register", json=REGISTRATION)
    assert registration.status_code == 201
    created = registration.json()
    assert created["email"] == "student@example.com"
    assert created["first_name"] == "Sam"
    assert created["role"] == "STUDENT"
    assert "password" not in created
    assert "password_hash" not in created

    login = client.post(
        "/auth/login",
        json={"email": "STUDENT@example.com", "password": REGISTRATION["password"]},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"
    assert login.headers["cache-control"] == "no-store"
    assert login.headers["pragma"] == "no-cache"
    assert "celpip_access_token=" in login.headers["set-cookie"]
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=lax" in login.headers["set-cookie"]

    current = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert current.status_code == 200
    assert current.json()["id"] == created["id"]

    current_from_cookie = client.get("/auth/me")
    assert current_from_cookie.status_code == 200
    assert current_from_cookie.json()["id"] == created["id"]

    logout = client.post("/auth/logout")
    assert logout.status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    assert client.post("/auth/register", json=REGISTRATION).status_code == 201
    duplicate = client.post(
        "/auth/register", json=REGISTRATION | {"email": "STUDENT@example.com"}
    )
    assert duplicate.status_code == 409


def test_bad_credentials_and_missing_token_are_rejected(client: TestClient) -> None:
    assert client.post("/auth/register", json=REGISTRATION).status_code == 201
    invalid_login = client.post(
        "/auth/login",
        json={"email": REGISTRATION["email"], "password": "definitely-wrong"},
    )
    assert invalid_login.status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer broken"}).status_code == 401


def test_valid_token_for_unknown_user_is_rejected(client: TestClient) -> None:
    token, _ = create_access_token(uuid.uuid4(), UserRole.STUDENT)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_registration_validates_score_and_password(client: TestClient) -> None:
    invalid = REGISTRATION | {"password": "short", "target_celpip_score": 13}
    response = client.post("/auth/register", json=invalid)
    assert response.status_code == 422
