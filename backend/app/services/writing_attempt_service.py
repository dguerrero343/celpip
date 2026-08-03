import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.help_generator import (
    HELP_CONTENT_VERSION,
    HelpGenerator,
    WritingHelpContent,
    demo_help_content,
)
from app.models.ai_student_context import AIStudentContext
from app.models.ai_usage import AIUsage
from app.models.enums import WritingAttemptStatus, WritingAttemptType, WritingTaskType
from app.models.user import User
from app.models.writing_attempt import WritingAttempt
from app.models.writing_submission import WritingSubmission
from app.models.writing_task import WritingTask
from app.services.writing_service import assign_next_writing_task, count_words

PREPARATION_SECONDS = 59
WRITING_SECONDS = {WritingTaskType.EMAIL: 27 * 60, WritingTaskType.SURVEY: 26 * 60}
logger = logging.getLogger(__name__)


class WritingAttemptNotFoundError(Exception):
    """Attempt is absent or belongs to another user."""


class WritingAttemptModeLockedError(Exception):
    """Help mode cannot change after preparation."""


class WritingAttemptNotReadyError(Exception):
    """Writing has not started yet."""


class WritingAttemptAlreadyFinishedError(Exception):
    """Attempt is already submitted."""


class WritingHelpUnavailableError(Exception):
    """Stored or generated guidance could not be validated."""


class ActiveWritingAttemptError(Exception):
    """A different writing task is already in progress for this user."""

    def __init__(self, attempt: WritingAttempt) -> None:
        self.attempt = attempt
        super().__init__("Only one writing attempt can be active at a time")


def utc_now() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def synchronize_status(attempt: WritingAttempt, now: datetime | None = None) -> None:
    now = now or utc_now()
    if attempt.status == WritingAttemptStatus.PREPARING and now >= aware(
        attempt.preparation_expires_at
    ):
        attempt.status = WritingAttemptStatus.WRITING
    if attempt.status == WritingAttemptStatus.WRITING and now >= aware(attempt.writing_expires_at):
        attempt.status = WritingAttemptStatus.EXPIRED


def _attempt_query(user_id: uuid.UUID):
    return (
        select(WritingAttempt)
        .where(WritingAttempt.user_id == user_id)
        .execution_options(populate_existing=True)
        .options(
            selectinload(WritingAttempt.task),
            selectinload(WritingAttempt.assignment),
            selectinload(WritingAttempt.submission).selectinload(WritingSubmission.task),
            selectinload(WritingAttempt.submission).selectinload(WritingSubmission.evaluation),
        )
    )


async def get_attempt(
    session: AsyncSession, *, user_id: uuid.UUID, attempt_id: uuid.UUID
) -> WritingAttempt:
    attempt = await session.scalar(_attempt_query(user_id).where(WritingAttempt.id == attempt_id))
    if attempt is None:
        raise WritingAttemptNotFoundError
    old_status = attempt.status
    synchronize_status(attempt)
    if attempt.status != old_status:
        await session.commit()
    return attempt


async def get_active_attempt(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    task_type: WritingTaskType | None = None,
) -> WritingAttempt | None:
    filters = [
        WritingAttempt.status.in_((WritingAttemptStatus.PREPARING, WritingAttemptStatus.WRITING))
    ]
    if task_type is not None:
        filters.append(WritingAttempt.task.has(task_type=task_type))
    attempt = await session.scalar(
        _attempt_query(user_id).where(*filters).order_by(WritingAttempt.created_at.desc())
    )
    if attempt is not None:
        synchronize_status(attempt)
        await session.commit()
    return attempt


async def create_attempt(
    session: AsyncSession, *, user: User, task_type: WritingTaskType
) -> WritingAttempt:
    active = await get_active_attempt(session, user_id=user.id)
    if active is not None and utc_now() < aware(active.writing_expires_at):
        if active.task.task_type == task_type:
            return active
        raise ActiveWritingAttemptError(active)
    if active is not None:
        active.status = WritingAttemptStatus.EXPIRED
    assignment, task = await assign_next_writing_task(session, user=user, task_type=task_type)
    started = utc_now()
    writing_started = started + timedelta(seconds=PREPARATION_SECONDS)
    attempt = WritingAttempt(
        user_id=user.id,
        task_id=task.id,
        assignment_id=assignment.id,
        preparation_started_at=started,
        preparation_expires_at=writing_started,
        writing_started_at=writing_started,
        writing_expires_at=writing_started + timedelta(seconds=WRITING_SECONDS[task_type]),
    )
    session.add(attempt)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        winner = await get_active_attempt(session, user_id=user.id)
        stale_assignment = await session.get(type(assignment), assignment.id)
        if stale_assignment is not None and (
            winner is None or winner.assignment_id != stale_assignment.id
        ):
            await session.delete(stale_assignment)
            await session.commit()
        if winner is None:
            raise
        if winner.task.task_type != task_type:
            raise ActiveWritingAttemptError(winner) from None
        return winner
    return await get_attempt(session, user_id=user.id, attempt_id=attempt.id)


async def set_attempt_mode(
    session: AsyncSession, *, user_id: uuid.UUID, attempt_id: uuid.UUID, enabled: bool
) -> WritingAttempt:
    attempt = await get_attempt(session, user_id=user_id, attempt_id=attempt_id)
    if (
        utc_now() >= aware(attempt.preparation_expires_at)
        or attempt.status != WritingAttemptStatus.PREPARING
    ):
        raise WritingAttemptModeLockedError
    attempt.help_mode_enabled = enabled
    attempt.attempt_type = (
        WritingAttemptType.GUIDED_PRACTICE if enabled else WritingAttemptType.TEST_SIMULATION
    )
    await session.commit()
    return await get_attempt(session, user_id=user_id, attempt_id=attempt.id)


def _save_fields(
    attempt: WritingAttempt,
    *,
    answer_text: str,
    sections: list[str],
    open_count: int,
    visible_seconds: int,
) -> None:
    attempt.answer_text = answer_text
    attempt.word_count = count_words(answer_text)
    if attempt.help_mode_enabled:
        attempt.help_sections_opened = sorted(set(attempt.help_sections_opened) | set(sections))
        attempt.help_panel_open_count = max(attempt.help_panel_open_count, open_count)
        attempt.help_visible_seconds = max(attempt.help_visible_seconds, visible_seconds)
    attempt.last_saved_at = utc_now()


async def autosave_attempt(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    answer_text: str,
    sections: list[str],
    open_count: int,
    visible_seconds: int,
) -> WritingAttempt:
    attempt = await get_attempt(session, user_id=user_id, attempt_id=attempt_id)
    now = utc_now()
    if now < aware(attempt.writing_started_at):
        raise WritingAttemptNotReadyError
    if attempt.submitted_at is not None:
        raise WritingAttemptAlreadyFinishedError
    if now >= aware(attempt.writing_expires_at):
        attempt.status = WritingAttemptStatus.EXPIRED
        await session.commit()
        return attempt
    _save_fields(
        attempt,
        answer_text=answer_text,
        sections=sections,
        open_count=open_count,
        visible_seconds=visible_seconds,
    )
    await session.commit()
    return await get_attempt(session, user_id=user_id, attempt_id=attempt.id)


async def submit_attempt(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    answer_text: str,
    sections: list[str],
    open_count: int,
    visible_seconds: int,
) -> WritingAttempt:
    attempt = await get_attempt(session, user_id=user_id, attempt_id=attempt_id)
    if attempt.submission_id is not None:
        return attempt
    now = utc_now()
    if now < aware(attempt.writing_started_at):
        raise WritingAttemptNotReadyError
    if now < aware(attempt.writing_expires_at):
        _save_fields(
            attempt,
            answer_text=answer_text,
            sections=sections,
            open_count=open_count,
            visible_seconds=visible_seconds,
        )
    else:
        attempt.status = WritingAttemptStatus.EXPIRED
    if not attempt.answer_text.strip():
        await session.commit()
        return await get_attempt(session, user_id=user_id, attempt_id=attempt.id)
    submission = WritingSubmission(
        user_id=user_id,
        task_id=attempt.task_id,
        answer_text=attempt.answer_text,
        word_count=attempt.word_count,
    )
    session.add(submission)
    await session.flush()
    attempt.submission_id = submission.id
    attempt.submitted_at = now
    attempt.status = (
        WritingAttemptStatus.SUBMITTED
        if now < aware(attempt.writing_expires_at)
        else WritingAttemptStatus.EXPIRED
    )
    if attempt.assignment is not None:
        attempt.assignment.status = "COMPLETED"
    await session.commit()
    return await get_attempt(session, user_id=user_id, attempt_id=attempt.id)


async def get_or_generate_help(
    session: AsyncSession, *, user: User, attempt_id: uuid.UUID, generator: HelpGenerator | None
) -> tuple[WritingHelpContent, bool]:
    attempt = await get_attempt(session, user_id=user.id, attempt_id=attempt_id)
    if not attempt.help_mode_enabled:
        raise WritingAttemptNotFoundError
    if utc_now() < aware(attempt.writing_started_at):
        raise WritingAttemptNotReadyError
    task = await session.scalar(
        select(WritingTask).where(WritingTask.id == attempt.task_id).with_for_update()
    )
    if task is None:
        raise WritingAttemptNotFoundError
    cache_is_reusable = (
        task.help_content_json is not None
        and task.help_content_version == HELP_CONTENT_VERSION
        and (not task.help_content_is_fixture or generator is None)
    )
    if cache_is_reusable:
        try:
            return WritingHelpContent.model_validate(
                task.help_content_json
            ), task.help_content_is_fixture
        except ValueError as exc:
            logger.warning(
                "Stored writing help failed validation task_id=%s error_type=%s",
                task.id,
                type(exc).__name__,
            )
            raise WritingHelpUnavailableError from exc
    context = await session.get(AIStudentContext, user.id)
    weaknesses = tuple(context.main_weaknesses[:3]) if context is not None else ()
    target = user.target_celpip_score or 12
    try:
        if generator is None:
            content = demo_help_content(task.task_type, task.category, task.prompt)
            model, is_fixture = "demo-fixture", True
            usage = None
        else:
            output = await generator.generate(
                task_type=task.task_type,
                instructions=task.prompt,
                topic=task.category,
                target_score=target,
                weaknesses=weaknesses,
            )
            content, model, is_fixture, usage = output.content, output.model, False, output
    except Exception as exc:
        logger.warning(
            "Writing help generation failed task_id=%s error_type=%s",
            task.id,
            type(exc).__name__,
        )
        raise WritingHelpUnavailableError from exc
    task.help_content_json = content.model_dump(mode="json")
    task.help_content_version = HELP_CONTENT_VERSION
    task.help_content_model = model
    task.help_content_generated_at = utc_now()
    task.help_content_is_fixture = is_fixture
    if usage is not None:
        session.add(
            AIUsage(
                user_id=user.id,
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost=usage.estimated_cost,
                request_type="writing_help_generation",
            )
        )
    await session.commit()
    return content, is_fixture
