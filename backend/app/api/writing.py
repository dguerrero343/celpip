import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.ai.dependencies import EvaluationProvider
from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.enums import Difficulty, WritingTaskType
from app.schemas.writing import (
    WritingEvaluationResponse,
    WritingProgressResponse,
    WritingSubmissionCreate,
    WritingSubmissionListResponse,
    WritingSubmissionResponse,
    WritingTaskAssignmentResponse,
    WritingTaskListResponse,
    WritingTaskNextRequest,
    WritingTaskResponse,
)
from app.services.evaluation_service import (
    EvaluationProviderError,
    EvaluationProviderNotConfiguredError,
    InvalidEvaluationOutputError,
    TargetScoreRequiredError,
    evaluate_writing_submission,
)
from app.services.writing_service import (
    NoUnseenWritingTaskError,
    WritingSubmissionNotFoundError,
    WritingTaskNotFoundError,
    assign_next_writing_task,
    create_writing_submission,
    get_writing_progress,
    get_writing_submission,
    get_writing_task,
    list_writing_submissions,
    list_writing_tasks,
)

router = APIRouter(prefix="/writing", tags=["writing"])


@router.post("/tasks/next", response_model=WritingTaskAssignmentResponse)
async def next_task(
    data: WritingTaskNextRequest, session: DatabaseSession, current_user: CurrentUser
) -> WritingTaskAssignmentResponse:
    try:
        assignment, task = await assign_next_writing_task(
            session, user=current_user, task_type=data.task_type
        )
    except NoUnseenWritingTaskError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No unseen approved exercises are currently available for this task type",
        ) from None
    return WritingTaskAssignmentResponse(
        assignment_id=assignment.id,
        task=WritingTaskResponse.model_validate(task),
    )


@router.get("/tasks", response_model=WritingTaskListResponse)
async def tasks(
    session: DatabaseSession,
    current_user: CurrentUser,
    task_type: WritingTaskType | None = None,
    difficulty: Difficulty | None = None,
    category: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> WritingTaskListResponse:
    del current_user
    items, total = await list_writing_tasks(
        session,
        task_type=task_type,
        difficulty=difficulty,
        category=category,
        limit=limit,
        offset=offset,
    )
    return WritingTaskListResponse(items=list(items), total=total, limit=limit, offset=offset)


@router.get("/tasks/{task_id}", response_model=WritingTaskResponse)
async def task(
    task_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> WritingTaskResponse:
    del current_user
    try:
        return WritingTaskResponse.model_validate(await get_writing_task(session, task_id))
    except WritingTaskNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing task not found"
        ) from None


@router.post(
    "/submissions",
    response_model=WritingSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_writing(
    data: WritingSubmissionCreate, session: DatabaseSession, current_user: CurrentUser
) -> WritingSubmissionResponse:
    try:
        submission = await create_writing_submission(
            session,
            user_id=current_user.id,
            task_id=data.task_id,
            answer_text=data.answer_text,
        )
    except WritingTaskNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing task not found"
        ) from None
    return WritingSubmissionResponse.model_validate(submission)


@router.get("/submissions", response_model=WritingSubmissionListResponse)
async def submissions(
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> WritingSubmissionListResponse:
    items, total = await list_writing_submissions(
        session, user_id=current_user.id, limit=limit, offset=offset
    )
    return WritingSubmissionListResponse(
        items=list(items), total=total, limit=limit, offset=offset
    )


@router.get("/submissions/{submission_id}", response_model=WritingSubmissionResponse)
async def submission(
    submission_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> WritingSubmissionResponse:
    try:
        item = await get_writing_submission(
            session, user_id=current_user.id, submission_id=submission_id
        )
    except WritingSubmissionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing submission not found"
        ) from None
    return WritingSubmissionResponse.model_validate(item)


@router.post(
    "/submissions/{submission_id}/evaluation",
    response_model=WritingEvaluationResponse,
)
async def evaluate_submission(
    submission_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
    provider: EvaluationProvider,
) -> WritingEvaluationResponse:
    try:
        evaluation = await evaluate_writing_submission(
            session,
            user=current_user,
            submission_id=submission_id,
            provider=provider,
        )
    except WritingSubmissionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing submission not found"
        ) from None
    except TargetScoreRequiredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Set a target CELPIP score before requesting an evaluation",
        ) from None
    except EvaluationProviderNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Writing evaluation provider is not configured",
            headers={"Retry-After": "60"},
        ) from None
    except (EvaluationProviderError, InvalidEvaluationOutputError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Writing evaluation failed",
        ) from None
    return WritingEvaluationResponse.model_validate(evaluation)


@router.get("/progress", response_model=WritingProgressResponse)
async def progress(
    session: DatabaseSession, current_user: CurrentUser
) -> WritingProgressResponse:
    return WritingProgressResponse.model_validate(
        await get_writing_progress(session, current_user), from_attributes=True
    )
