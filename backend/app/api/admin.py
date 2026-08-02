import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.ai.question_generator import QuestionGeneratorDependency
from app.api.dependencies import AdminUser, DatabaseSession
from app.models.ai_usage import AIUsage
from app.models.enums import Difficulty, WritingTaskSource, WritingTaskStatus, WritingTaskType
from app.models.writing_task import WritingTask
from app.schemas.admin import (
    AdminGenerateTasksRequest,
    AdminGenerateTasksResponse,
    AdminQuestionBankSummary,
    AdminTaskCreate,
    AdminTaskListResponse,
    AdminTaskResponse,
    AdminTaskStatusUpdate,
    AdminTaskUpdate,
)
from app.services.admin_question_bank_service import (
    AdminTaskNotFoundError,
    AdminTaskRecord,
    DuplicateTaskError,
    TaskStyleValidationError,
    change_admin_task_status,
    create_admin_task,
    create_task_with_source,
    get_question_bank_summary,
    list_admin_tasks,
    update_admin_task,
)

router = APIRouter(prefix="/admin", tags=["administration"])


def _response(record: AdminTaskRecord) -> AdminTaskResponse:
    task = record.task
    return AdminTaskResponse(
        id=task.id,
        family_id=task.family_id,
        task_type=task.task_type,
        category=task.category,
        difficulty=task.difficulty,
        prompt=task.prompt,
        status=task.status,
        source=task.source,
        scenario_key=task.scenario_key,
        focus_tags=task.focus_tags,
        target_score_min=task.target_score_min,
        target_score_max=task.target_score_max,
        reviewed_at=task.reviewed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        assignment_count=record.assignment_count,
        submission_count=record.submission_count,
        style_issues=record.style_issues,
    )


@router.get("/question-bank/summary", response_model=AdminQuestionBankSummary)
async def question_bank_summary(
    session: DatabaseSession, admin: AdminUser
) -> AdminQuestionBankSummary:
    del admin
    return await get_question_bank_summary(session)


@router.get("/question-bank", response_model=AdminTaskListResponse)
async def question_bank(
    session: DatabaseSession,
    admin: AdminUser,
    task_status: Annotated[WritingTaskStatus | None, Query(alias="status")] = None,
    task_type: WritingTaskType | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> AdminTaskListResponse:
    del admin
    records, total = await list_admin_tasks(
        session, status=task_status, task_type=task_type, search=search
    )
    return AdminTaskListResponse(items=[_response(item) for item in records], total=total)


@router.post(
    "/question-bank", response_model=AdminTaskResponse, status_code=status.HTTP_201_CREATED
)
async def create_question(
    data: AdminTaskCreate, session: DatabaseSession, admin: AdminUser
) -> AdminTaskResponse:
    del admin
    try:
        return _response(await create_admin_task(session, data))
    except DuplicateTaskError:
        raise HTTPException(
            status_code=409, detail="An exercise with the same prompt already exists"
        ) from None


@router.put("/question-bank/{task_id}", response_model=AdminTaskResponse)
async def update_question(
    task_id: uuid.UUID,
    data: AdminTaskUpdate,
    session: DatabaseSession,
    admin: AdminUser,
) -> AdminTaskResponse:
    del admin
    try:
        return _response(await update_admin_task(session, task_id, data))
    except AdminTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Exercise not found") from None
    except DuplicateTaskError:
        raise HTTPException(
            status_code=409, detail="An exercise with the same prompt already exists"
        ) from None


@router.post("/question-bank/{task_id}/status", response_model=AdminTaskResponse)
async def update_question_status(
    task_id: uuid.UUID,
    data: AdminTaskStatusUpdate,
    session: DatabaseSession,
    admin: AdminUser,
) -> AdminTaskResponse:
    try:
        return _response(
            await change_admin_task_status(
                session, task_id=task_id, status=data.status, admin=admin
            )
        )
    except AdminTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Exercise not found") from None
    except TaskStyleValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": "CELPIP-style validation failed", "issues": exc.issues},
        ) from None


@router.post("/question-bank/generate", response_model=AdminGenerateTasksResponse)
async def generate_questions(
    data: AdminGenerateTasksRequest,
    session: DatabaseSession,
    admin: AdminUser,
    generator: QuestionGeneratorDependency,
) -> AdminGenerateTasksResponse:
    if generator is None:
        raise HTTPException(status_code=503, detail="OpenAI draft generation is not configured")
    existing = tuple(
        value
        for value in (
            await session.scalars(
                select(WritingTask.scenario_key).where(WritingTask.scenario_key.is_not(None))
            )
        ).all()
        if value
    )
    try:
        generated = await generator.generate(
            task_type=data.task_type,
            count=data.count,
            category=data.category,
            existing_scenarios=existing,
        )
        records = []
        for question in generated.questions:
            records.append(
                await create_task_with_source(
                    session,
                    AdminTaskCreate(
                        task_type=data.task_type,
                        category=question.category,
                        difficulty=Difficulty.INTERMEDIATE,
                        prompt=question.prompt,
                        scenario_key=question.scenario_key,
                        focus_tags=question.focus_tags,
                        target_score_min=question.target_score_min,
                        target_score_max=question.target_score_max,
                    ),
                    source=WritingTaskSource.AI,
                    commit=False,
                )
            )
        session.add(
            AIUsage(
                user_id=admin.id,
                model=generated.model,
                input_tokens=generated.input_tokens,
                output_tokens=generated.output_tokens,
                estimated_cost=generated.estimated_cost,
                request_type="question_generation",
            )
        )
        await session.commit()
        return AdminGenerateTasksResponse(
            items=[_response(item) for item in records],
            model=generated.model,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            estimated_cost_usd=float(generated.estimated_cost),
        )
    except DuplicateTaskError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Generated drafts duplicated existing exercises",
        ) from None
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail="AI draft generation failed") from exc
