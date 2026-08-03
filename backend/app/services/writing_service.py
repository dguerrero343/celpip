import random
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ai_student_context import AIStudentContext
from app.models.enums import Difficulty, WritingAttemptType, WritingTaskStatus, WritingTaskType
from app.models.user import User
from app.models.writing_attempt import WritingAttempt
from app.models.writing_evaluation import WritingEvaluation
from app.models.writing_submission import WritingSubmission
from app.models.writing_task import WritingTask
from app.models.writing_task_assignment import WritingTaskAssignment

WORD_PATTERN = re.compile(r"\b\w+(?:[’'-]\w+)*\b", flags=re.UNICODE)


class WritingTaskNotFoundError(Exception):
    """Raised when a requested writing task does not exist."""


class WritingSubmissionNotFoundError(Exception):
    """Raised when a submission is absent or does not belong to the user."""


class NoUnseenWritingTaskError(Exception):
    """Raised when a user has exhausted the approved catalog for a task type."""


@dataclass(frozen=True, slots=True)
class WritingProgress:
    total_submissions: int
    evaluated_submissions: int
    current_score: float | None
    target_score: float | None
    average_score: float | None
    best_score: float | None
    last_evaluated_at: datetime | None
    test_simulation: "WritingProgressSummary"
    guided_practice: "WritingProgressSummary"


@dataclass(frozen=True, slots=True)
class WritingProgressSummary:
    total_submissions: int
    evaluated_submissions: int
    average_score: float | None
    best_score: float | None
    last_evaluated_at: datetime | None


def count_words(answer_text: str) -> int:
    return len(WORD_PATTERN.findall(answer_text))


async def list_writing_tasks(
    session: AsyncSession,
    *,
    task_type: WritingTaskType | None,
    difficulty: Difficulty | None,
    category: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[WritingTask], int]:
    filters = []
    filters.append(WritingTask.status == WritingTaskStatus.APPROVED)
    if task_type is not None:
        filters.append(WritingTask.task_type == task_type)
    if difficulty is not None:
        filters.append(WritingTask.difficulty == difficulty)
    if category:
        filters.append(WritingTask.category.ilike(f"%{category.strip()}%"))

    total = await session.scalar(select(func.count(WritingTask.id)).where(*filters))
    tasks = await session.scalars(
        select(WritingTask)
        .where(*filters)
        .order_by(WritingTask.task_type, WritingTask.difficulty, WritingTask.created_at)
        .limit(limit)
        .offset(offset)
    )
    return tasks.all(), int(total or 0)


def _selection_score(
    task: WritingTask,
    *,
    target_score: int | None,
    weaknesses: tuple[str, ...],
    practiced_categories: set[str],
) -> float:
    normalized_weaknesses = " ".join(weaknesses).lower().replace("_", " ")
    matched_tags = sum(
        1 for tag in task.focus_tags if tag.lower().replace("_", " ") in normalized_weaknesses
    )
    score = matched_tags * 45
    if target_score is not None and task.target_score_min <= target_score <= task.target_score_max:
        score += 25
    if task.category.casefold() not in practiced_categories:
        score += 15
    return score + random.random() * 5


async def assign_next_writing_task(
    session: AsyncSession, *, user: User, task_type: WritingTaskType
) -> tuple[WritingTaskAssignment, WritingTask]:
    for _ in range(3):
        assigned_families = select(WritingTaskAssignment.family_id).where(
            WritingTaskAssignment.user_id == user.id
        )
        candidates = list(
            (
                await session.scalars(
                    select(WritingTask).where(
                        WritingTask.task_type == task_type,
                        WritingTask.status == WritingTaskStatus.APPROVED,
                        WritingTask.family_id.not_in(assigned_families),
                    )
                )
            ).all()
        )
        if not candidates:
            raise NoUnseenWritingTaskError

        practiced_categories = {
            value.casefold()
            for value in (
                await session.scalars(
                    select(WritingTask.category)
                    .join(WritingTaskAssignment, WritingTaskAssignment.task_id == WritingTask.id)
                    .where(WritingTaskAssignment.user_id == user.id)
                )
            ).all()
        }
        context = await session.get(AIStudentContext, user.id)
        weaknesses = tuple(context.main_weaknesses) if context is not None else ()
        target_score = (
            int(context.target_score) if context is not None else user.target_celpip_score
        )
        task = max(
            candidates,
            key=lambda item: _selection_score(
                item,
                target_score=target_score,
                weaknesses=weaknesses,
                practiced_categories=practiced_categories,
            ),
        )
        assignment = WritingTaskAssignment(
            user_id=user.id,
            task_id=task.id,
            family_id=task.family_id,
            status="ASSIGNED",
        )
        session.add(assignment)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            continue
        await session.refresh(assignment)
        return assignment, task
    raise NoUnseenWritingTaskError


async def get_writing_task(session: AsyncSession, task_id: uuid.UUID) -> WritingTask:
    task = await session.scalar(
        select(WritingTask).where(
            WritingTask.id == task_id,
            WritingTask.status == WritingTaskStatus.APPROVED,
        )
    )
    if task is None:
        raise WritingTaskNotFoundError
    return task


async def create_writing_submission(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    answer_text: str,
) -> WritingSubmission:
    task = await get_writing_task(session, task_id)
    submission = WritingSubmission(
        user_id=user_id,
        task_id=task_id,
        answer_text=answer_text,
        word_count=count_words(answer_text),
    )
    session.add(submission)
    assignment = await session.scalar(
        select(WritingTaskAssignment).where(
            WritingTaskAssignment.user_id == user_id,
            WritingTaskAssignment.family_id == task.family_id,
        )
    )
    if assignment is None:
        session.add(
            WritingTaskAssignment(
                user_id=user_id,
                task_id=task_id,
                family_id=task.family_id,
                status="COMPLETED",
            )
        )
    else:
        assignment.status = "COMPLETED"
    await session.commit()
    return await get_writing_submission(session, user_id=user_id, submission_id=submission.id)


def _submission_query(user_id: uuid.UUID):
    return (
        select(WritingSubmission)
        .where(WritingSubmission.user_id == user_id)
        .options(
            selectinload(WritingSubmission.task),
            selectinload(WritingSubmission.evaluation),
            selectinload(WritingSubmission.attempt),
        )
    )


async def get_writing_submission(
    session: AsyncSession, *, user_id: uuid.UUID, submission_id: uuid.UUID
) -> WritingSubmission:
    submission = await session.scalar(
        _submission_query(user_id).where(WritingSubmission.id == submission_id)
    )
    if submission is None:
        raise WritingSubmissionNotFoundError
    return submission


async def list_writing_submissions(
    session: AsyncSession, *, user_id: uuid.UUID, limit: int, offset: int
) -> tuple[Sequence[WritingSubmission], int]:
    total = await session.scalar(
        select(func.count(WritingSubmission.id)).where(WritingSubmission.user_id == user_id)
    )
    submissions = await session.scalars(
        _submission_query(user_id)
        .order_by(WritingSubmission.submitted_at.desc(), WritingSubmission.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return submissions.all(), int(total or 0)


async def get_writing_progress(session: AsyncSession, user: User) -> WritingProgress:
    async def summary(attempt_type: WritingAttemptType) -> WritingProgressSummary:
        type_filter = (
            WritingAttempt.attempt_type == WritingAttemptType.GUIDED_PRACTICE
            if attempt_type == WritingAttemptType.GUIDED_PRACTICE
            else (
                WritingAttempt.id.is_(None)
                | (WritingAttempt.attempt_type == WritingAttemptType.TEST_SIMULATION)
            )
        )
        row = (
            await session.execute(
                select(
                    func.count(WritingSubmission.id),
                    func.count(WritingEvaluation.id),
                    func.avg(WritingEvaluation.estimated_score),
                    func.max(WritingEvaluation.estimated_score),
                    func.max(WritingEvaluation.created_at),
                )
                .outerjoin(
                    WritingEvaluation, WritingEvaluation.submission_id == WritingSubmission.id
                )
                .outerjoin(WritingAttempt, WritingAttempt.submission_id == WritingSubmission.id)
                .where(WritingSubmission.user_id == user.id, type_filter)
            )
        ).one()
        return WritingProgressSummary(
            int(row[0] or 0),
            int(row[1] or 0),
            float(row[2]) if row[2] is not None else None,
            float(row[3]) if row[3] is not None else None,
            row[4],
        )

    test_summary = await summary(WritingAttemptType.TEST_SIMULATION)
    guided_summary = await summary(WritingAttemptType.GUIDED_PRACTICE)
    row = (
        await session.execute(
            select(
                func.count(WritingSubmission.id),
                func.count(WritingEvaluation.id),
                func.avg(WritingEvaluation.estimated_score),
                func.max(WritingEvaluation.estimated_score),
                func.max(WritingEvaluation.created_at),
            )
            .outerjoin(
                WritingEvaluation,
                WritingEvaluation.submission_id == WritingSubmission.id,
            )
            .where(WritingSubmission.user_id == user.id)
        )
    ).one()

    return WritingProgress(
        total_submissions=int(row[0] or 0),
        evaluated_submissions=int(row[1] or 0),
        current_score=float(user.current_celpip_score) if user.current_celpip_score else None,
        target_score=float(user.target_celpip_score) if user.target_celpip_score else None,
        average_score=float(row[2]) if row[2] is not None else None,
        best_score=float(row[3]) if row[3] is not None else None,
        last_evaluated_at=row[4],
        test_simulation=test_summary,
        guided_practice=guided_summary,
    )
