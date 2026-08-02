from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import DUMMY_PASSWORD_HASH, hash_password, verify_and_update_password
from app.core.config import settings
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserCreate


class EmailAlreadyRegisteredError(Exception):
    """Raised when a registration attempts to reuse an email address."""


def _is_email_unique_violation(exc: IntegrityError) -> bool:
    diagnostic = getattr(exc.orig, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name == "ix_users_email":
        return True
    return "UNIQUE constraint failed: users.email" in str(exc.orig)


async def register_user(session: AsyncSession, data: UserCreate) -> User:
    email = str(data.email).strip().lower()
    existing_user = await session.scalar(select(User.id).where(User.email == email))
    if existing_user is not None:
        raise EmailAlreadyRegisteredError

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        current_celpip_score=data.current_celpip_score,
        target_celpip_score=data.target_celpip_score,
        target_exam_date=data.target_exam_date,
        role=(
            UserRole.ADMIN
            if email in {item.strip().lower() for item in settings.admin_emails}
            else UserRole.STUDENT
        ),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_email_unique_violation(exc):
            raise EmailAlreadyRegisteredError from exc
        raise
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.strip().lower()))
    user = result.scalar_one_or_none()
    encoded_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    verified, updated_hash = verify_and_update_password(password, encoded_hash)
    if user is None or not user.is_active or not verified:
        return None
    if (
        user.role != UserRole.ADMIN
        and user.email in {item.strip().lower() for item in settings.admin_emails}
    ):
        user.role = UserRole.ADMIN
        await session.commit()
    if updated_hash is not None:
        user.password_hash = updated_hash
        await session.commit()
    return user
