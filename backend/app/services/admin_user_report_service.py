import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage import AIUsage
from app.models.enums import UserRole, WritingAttemptStatus, WritingAttemptType
from app.models.user import User
from app.models.writing_attempt import WritingAttempt
from app.models.writing_evaluation import WritingEvaluation
from app.models.writing_submission import WritingSubmission
from app.models.writing_task import WritingTask
from app.models.writing_task_assignment import WritingTaskAssignment


@dataclass(slots=True)
class UserMetrics:
    assigned_exercises: int = 0
    attempts_started: int = 0
    active_attempts: int = 0
    exercises_completed: int = 0
    guided_practice_completed: int = 0
    test_simulation_completed: int = 0
    total_practice_seconds: int = 0
    test_scores: list[float] = field(default_factory=list)
    guided_scores: list[float] = field(default_factory=list)
    ai_request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")
    last_activity_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AdminUserSummaryRecord:
    id: uuid.UUID
    email: str
    first_name: str
    role: UserRole
    current_score: int | None
    target_score: int | None
    registered_at: datetime
    last_activity_at: datetime
    assigned_exercises: int
    attempts_started: int
    active_attempts: int
    exercises_completed: int
    guided_practice_completed: int
    test_simulation_completed: int
    total_practice_seconds: int
    average_test_score: float | None
    average_guided_score: float | None
    ai_request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


@dataclass(frozen=True, slots=True)
class AdminUserAttemptRecord:
    id: uuid.UUID
    task_type: str
    category: str
    status: WritingAttemptStatus
    attempt_type: WritingAttemptType
    help_mode_enabled: bool
    started_at: datetime
    submitted_at: datetime | None
    elapsed_seconds: int
    word_count: int
    estimated_score: float | None


@dataclass(frozen=True, slots=True)
class AdminUserUsageBreakdownRecord:
    request_type: str
    model: str
    request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


@dataclass(frozen=True, slots=True)
class AdminUserDetailRecord:
    summary: AdminUserSummaryRecord
    recent_attempts: list[AdminUserAttemptRecord]
    ai_usage_breakdown: list[AdminUserUsageBreakdownRecord]


class AdminUserNotFoundError(Exception):
    """Raised when an administrator requests a user that does not exist."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _latest(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    candidate = _aware(candidate)
    return candidate if current is None or candidate > _aware(current) else current


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _elapsed_seconds(
    *,
    status: WritingAttemptStatus,
    started_at: datetime,
    expires_at: datetime,
    submitted_at: datetime | None,
    now: datetime,
) -> int:
    started = _aware(started_at)
    expires = _aware(expires_at)
    if submitted_at is not None:
        ended = min(_aware(submitted_at), expires)
    elif status == WritingAttemptStatus.EXPIRED:
        ended = expires
    else:
        ended = min(now, expires)
    return max(0, int((ended - started).total_seconds()))


async def _load_user_metrics(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, UserMetrics]:
    metrics = {user_id: UserMetrics() for user_id in user_ids}
    assignment_rows = await session.execute(
        select(WritingTaskAssignment.user_id, WritingTaskAssignment.assigned_at).where(
            WritingTaskAssignment.user_id.in_(user_ids)
        )
    )
    for user_id, assigned_at in assignment_rows.all():
        item = metrics[user_id]
        item.assigned_exercises += 1
        item.last_activity_at = _latest(item.last_activity_at, assigned_at)

    now = datetime.now(UTC)
    attempt_rows = await session.execute(
        select(
            WritingAttempt.user_id,
            WritingAttempt.status,
            WritingAttempt.preparation_started_at,
            WritingAttempt.writing_expires_at,
            WritingAttempt.submitted_at,
            WritingAttempt.updated_at,
        ).where(WritingAttempt.user_id.in_(user_ids))
    )
    for user_id, status, started_at, expires_at, submitted_at, updated_at in attempt_rows.all():
        item = metrics[user_id]
        item.attempts_started += 1
        if status in (WritingAttemptStatus.PREPARING, WritingAttemptStatus.WRITING):
            item.active_attempts += 1
        item.total_practice_seconds += _elapsed_seconds(
            status=status,
            started_at=started_at,
            expires_at=expires_at,
            submitted_at=submitted_at,
            now=now,
        )
        item.last_activity_at = _latest(item.last_activity_at, updated_at)

    submission_rows = await session.execute(
        select(
            WritingSubmission.user_id,
            WritingAttempt.attempt_type,
            WritingEvaluation.estimated_score,
            WritingSubmission.submitted_at,
        )
        .outerjoin(WritingAttempt, WritingAttempt.submission_id == WritingSubmission.id)
        .outerjoin(WritingEvaluation, WritingEvaluation.submission_id == WritingSubmission.id)
        .where(WritingSubmission.user_id.in_(user_ids))
    )
    for user_id, attempt_type, score, submitted_at in submission_rows.all():
        item = metrics[user_id]
        item.exercises_completed += 1
        resolved_type = attempt_type or WritingAttemptType.TEST_SIMULATION
        if resolved_type == WritingAttemptType.GUIDED_PRACTICE:
            item.guided_practice_completed += 1
            if score is not None:
                item.guided_scores.append(float(score))
        else:
            item.test_simulation_completed += 1
            if score is not None:
                item.test_scores.append(float(score))
        item.last_activity_at = _latest(item.last_activity_at, submitted_at)

    usage_rows = await session.execute(
        select(
            AIUsage.user_id,
            AIUsage.input_tokens,
            AIUsage.output_tokens,
            AIUsage.estimated_cost,
            AIUsage.created_at,
        ).where(AIUsage.user_id.in_(user_ids))
    )
    for user_id, input_tokens, output_tokens, cost, created_at in usage_rows.all():
        item = metrics[user_id]
        item.ai_request_count += 1
        item.input_tokens += int(input_tokens)
        item.output_tokens += int(output_tokens)
        item.estimated_cost_usd += Decimal(cost)
        item.last_activity_at = _latest(item.last_activity_at, created_at)

    return metrics


def _summary_record(user: User, item: UserMetrics) -> AdminUserSummaryRecord:
    return AdminUserSummaryRecord(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        role=user.role,
        current_score=user.current_celpip_score,
        target_score=user.target_celpip_score,
        registered_at=user.created_at,
        last_activity_at=item.last_activity_at or _aware(user.created_at),
        assigned_exercises=item.assigned_exercises,
        attempts_started=item.attempts_started,
        active_attempts=item.active_attempts,
        exercises_completed=item.exercises_completed,
        guided_practice_completed=item.guided_practice_completed,
        test_simulation_completed=item.test_simulation_completed,
        total_practice_seconds=item.total_practice_seconds,
        average_test_score=_average(item.test_scores),
        average_guided_score=_average(item.guided_scores),
        ai_request_count=item.ai_request_count,
        input_tokens=item.input_tokens,
        output_tokens=item.output_tokens,
        total_tokens=item.input_tokens + item.output_tokens,
        estimated_cost_usd=float(item.estimated_cost_usd),
    )


async def list_admin_user_summaries(
    session: AsyncSession,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[AdminUserSummaryRecord], int]:
    filters = []
    if search and (term := search.strip().lower()):
        pattern = f"%{term}%"
        filters.append(
            or_(func.lower(User.email).like(pattern), func.lower(User.first_name).like(pattern))
        )

    total = int(await session.scalar(select(func.count(User.id)).where(*filters)) or 0)
    users = list(
        (
            await session.scalars(
                select(User)
                .where(*filters)
                .order_by(User.created_at.desc(), User.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    if not users:
        return [], total

    metrics = await _load_user_metrics(session, [user.id for user in users])
    return [_summary_record(user, metrics[user.id]) for user in users], total


async def get_admin_user_detail(
    session: AsyncSession, *, user_id: uuid.UUID
) -> AdminUserDetailRecord:
    user = await session.get(User, user_id)
    if user is None:
        raise AdminUserNotFoundError

    metrics = await _load_user_metrics(session, [user.id])
    now = datetime.now(UTC)
    attempt_rows = await session.execute(
        select(
            WritingAttempt.id,
            WritingTask.task_type,
            WritingTask.category,
            WritingAttempt.status,
            WritingAttempt.attempt_type,
            WritingAttempt.help_mode_enabled,
            WritingAttempt.preparation_started_at,
            WritingAttempt.writing_expires_at,
            WritingAttempt.submitted_at,
            WritingAttempt.word_count,
            WritingEvaluation.estimated_score,
        )
        .join(WritingTask, WritingTask.id == WritingAttempt.task_id)
        .outerjoin(
            WritingEvaluation,
            WritingEvaluation.submission_id == WritingAttempt.submission_id,
        )
        .where(WritingAttempt.user_id == user.id)
        .order_by(WritingAttempt.created_at.desc(), WritingAttempt.id.desc())
        .limit(50)
    )
    recent_attempts = [
        AdminUserAttemptRecord(
            id=attempt_id,
            task_type=task_type.value,
            category=category,
            status=status,
            attempt_type=attempt_type,
            help_mode_enabled=help_mode_enabled,
            started_at=started_at,
            submitted_at=submitted_at,
            elapsed_seconds=_elapsed_seconds(
                status=status,
                started_at=started_at,
                expires_at=expires_at,
                submitted_at=submitted_at,
                now=now,
            ),
            word_count=word_count,
            estimated_score=float(score) if score is not None else None,
        )
        for (
            attempt_id,
            task_type,
            category,
            status,
            attempt_type,
            help_mode_enabled,
            started_at,
            expires_at,
            submitted_at,
            word_count,
            score,
        ) in attempt_rows.all()
    ]

    usage_rows = await session.execute(
        select(
            AIUsage.request_type,
            AIUsage.model,
            func.count(AIUsage.id),
            func.sum(AIUsage.input_tokens),
            func.sum(AIUsage.output_tokens),
            func.sum(AIUsage.estimated_cost),
        )
        .where(AIUsage.user_id == user.id)
        .group_by(AIUsage.request_type, AIUsage.model)
        .order_by(func.sum(AIUsage.estimated_cost).desc())
    )
    usage_breakdown = [
        AdminUserUsageBreakdownRecord(
            request_type=request_type,
            model=model,
            request_count=int(request_count),
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            total_tokens=int(input_tokens or 0) + int(output_tokens or 0),
            estimated_cost_usd=float(cost or 0),
        )
        for (
            request_type,
            model,
            request_count,
            input_tokens,
            output_tokens,
            cost,
        ) in usage_rows.all()
    ]

    return AdminUserDetailRecord(
        summary=_summary_record(user, metrics[user.id]),
        recent_attempts=recent_attempts,
        ai_usage_breakdown=usage_breakdown,
    )
