import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ai_student_context import AIStudentContext
from app.models.enums import WritingTaskStatus
from app.models.user import User
from app.models.user_score_history import UserScoreHistory
from app.models.writing_submission import WritingSubmission
from app.models.writing_task import WritingTask
from app.services.writing_service import WritingProgress, get_writing_progress

DEMO_USER_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")


class DemoDataNotFoundError(Exception):
    """Raised when demo mode is enabled before its seed migration has run."""


@dataclass(frozen=True, slots=True)
class DemoDashboard:
    user: User
    context: AIStudentContext
    progress: WritingProgress
    exercises: list[WritingTask]
    submissions: list[WritingSubmission]
    score_history: list[UserScoreHistory]


async def get_demo_dashboard(session: AsyncSession) -> DemoDashboard:
    user = await session.get(User, DEMO_USER_ID)
    context = await session.get(AIStudentContext, DEMO_USER_ID)
    if user is None or context is None:
        raise DemoDataNotFoundError

    exercises = list(
        (
            await session.scalars(
                select(WritingTask).where(
                    WritingTask.status == WritingTaskStatus.APPROVED
                ).order_by(
                    WritingTask.task_type,
                    WritingTask.difficulty,
                    WritingTask.created_at,
                )
            )
        ).all()
    )
    submissions = list(
        (
            await session.scalars(
                select(WritingSubmission)
                .where(WritingSubmission.user_id == DEMO_USER_ID)
                .options(
                    selectinload(WritingSubmission.task),
                    selectinload(WritingSubmission.evaluation),
                    selectinload(WritingSubmission.attempt),
                )
                .order_by(WritingSubmission.submitted_at.desc())
            )
        ).all()
    )
    score_history = list(
        (
            await session.scalars(
                select(UserScoreHistory)
                .where(UserScoreHistory.user_id == DEMO_USER_ID)
                .order_by(UserScoreHistory.date)
            )
        ).all()
    )

    return DemoDashboard(
        user=user,
        context=context,
        progress=await get_writing_progress(session, user),
        exercises=exercises,
        submissions=submissions,
        score_history=score_history,
    )
