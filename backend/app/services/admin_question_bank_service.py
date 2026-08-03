import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WritingTaskSource, WritingTaskStatus, WritingTaskType
from app.models.user import User
from app.models.writing_submission import WritingSubmission
from app.models.writing_task import WritingTask
from app.models.writing_task_assignment import WritingTaskAssignment
from app.schemas.admin import AdminQuestionBankSummary, AdminTaskCreate, AdminTaskUpdate
from app.services.task_quality_service import task_style_issues


class AdminTaskNotFoundError(Exception):
    pass


class DuplicateTaskError(Exception):
    pass


class TaskStyleValidationError(Exception):
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


@dataclass(frozen=True)
class AdminTaskRecord:
    task: WritingTask
    assignment_count: int
    submission_count: int
    style_issues: list[str]


def style_issues(task_type: WritingTaskType, prompt: str) -> list[str]:
    return task_style_issues(task_type, prompt)


async def _ensure_unique_prompt(
    session: AsyncSession, prompt: str, *, excluding_id: uuid.UUID | None = None
) -> None:
    normalized = " ".join(prompt.split()).casefold()
    statement = select(WritingTask.id, WritingTask.prompt)
    if excluding_id is not None:
        statement = statement.where(WritingTask.id != excluding_id)
    for _, existing in (await session.execute(statement)).all():
        if " ".join(existing.split()).casefold() == normalized:
            raise DuplicateTaskError


async def _record(session: AsyncSession, task: WritingTask) -> AdminTaskRecord:
    assignments = await session.scalar(
        select(func.count(WritingTaskAssignment.id)).where(WritingTaskAssignment.task_id == task.id)
    )
    submissions = await session.scalar(
        select(func.count(WritingSubmission.id)).where(WritingSubmission.task_id == task.id)
    )
    return AdminTaskRecord(
        task=task,
        assignment_count=int(assignments or 0),
        submission_count=int(submissions or 0),
        style_issues=style_issues(task.task_type, task.prompt),
    )


async def list_admin_tasks(
    session: AsyncSession,
    *,
    status: WritingTaskStatus | None,
    task_type: WritingTaskType | None,
    search: str | None,
) -> tuple[list[AdminTaskRecord], int]:
    filters = []
    if status is not None:
        filters.append(WritingTask.status == status)
    if task_type is not None:
        filters.append(WritingTask.task_type == task_type)
    if search:
        value = f"%{search.strip()}%"
        filters.append(
            WritingTask.category.ilike(value) | WritingTask.prompt.ilike(value)
        )
    tasks = list(
        (
            await session.scalars(
                select(WritingTask)
                .where(*filters)
                .order_by(WritingTask.updated_at.desc(), WritingTask.created_at.desc())
            )
        ).all()
    )
    return [await _record(session, task) for task in tasks], len(tasks)


async def get_admin_task(session: AsyncSession, task_id: uuid.UUID) -> WritingTask:
    task = await session.get(WritingTask, task_id)
    if task is None:
        raise AdminTaskNotFoundError
    return task


async def create_admin_task(session: AsyncSession, data: AdminTaskCreate) -> AdminTaskRecord:
    return await create_task_with_source(session, data, source=WritingTaskSource.HUMAN)


async def create_task_with_source(
    session: AsyncSession,
    data: AdminTaskCreate,
    *,
    source: WritingTaskSource,
    commit: bool = True,
) -> AdminTaskRecord:
    await _ensure_unique_prompt(session, data.prompt)
    task = WritingTask(
        **data.model_dump(),
        status=WritingTaskStatus.DRAFT,
        source=source,
    )
    session.add(task)
    if commit:
        await session.commit()
        await session.refresh(task)
    else:
        await session.flush()
    return await _record(session, task)


async def update_admin_task(
    session: AsyncSession, task_id: uuid.UUID, data: AdminTaskUpdate
) -> AdminTaskRecord:
    task = await get_admin_task(session, task_id)
    if task.status == WritingTaskStatus.APPROVED:
        task.status = WritingTaskStatus.IN_REVIEW
        task.reviewed_by = None
        task.reviewed_at = None
    await _ensure_unique_prompt(session, data.prompt, excluding_id=task.id)
    for field, value in data.model_dump().items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    return await _record(session, task)


async def change_admin_task_status(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    status: WritingTaskStatus,
    admin: User,
) -> AdminTaskRecord:
    task = await get_admin_task(session, task_id)
    if status == WritingTaskStatus.APPROVED:
        issues = style_issues(task.task_type, task.prompt)
        if issues:
            raise TaskStyleValidationError(issues)
        task.reviewed_by = admin.id
        task.reviewed_at = datetime.now(UTC)
    elif status in {WritingTaskStatus.DRAFT, WritingTaskStatus.IN_REVIEW}:
        task.reviewed_by = None
        task.reviewed_at = None
    task.status = status
    await session.commit()
    await session.refresh(task)
    return await _record(session, task)


async def get_question_bank_summary(session: AsyncSession) -> AdminQuestionBankSummary:
    statuses = dict(
        (
            await session.execute(
                select(WritingTask.status, func.count()).group_by(WritingTask.status)
            )
        ).all()
    )
    types = dict(
        (
            await session.execute(
                select(WritingTask.task_type, func.count()).group_by(WritingTask.task_type)
            )
        ).all()
    )
    total_assignments = await session.scalar(select(func.count(WritingTaskAssignment.id)))
    total_submissions = await session.scalar(select(func.count(WritingSubmission.id)))
    unique_students = await session.scalar(
        select(func.count(func.distinct(WritingTaskAssignment.user_id)))
    )
    return AdminQuestionBankSummary(
        total_tasks=sum(int(value) for value in statuses.values()),
        approved_tasks=int(statuses.get(WritingTaskStatus.APPROVED, 0)),
        draft_tasks=int(statuses.get(WritingTaskStatus.DRAFT, 0)),
        in_review_tasks=int(statuses.get(WritingTaskStatus.IN_REVIEW, 0)),
        retired_tasks=int(statuses.get(WritingTaskStatus.RETIRED, 0)),
        email_tasks=int(types.get(WritingTaskType.EMAIL, 0)),
        survey_tasks=int(types.get(WritingTaskType.SURVEY, 0)),
        total_assignments=int(total_assignments or 0),
        total_submissions=int(total_submissions or 0),
        unique_students=int(unique_students or 0),
    )
