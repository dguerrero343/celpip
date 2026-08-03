import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.ai.dependencies import EvaluationProvider
from app.ai.help_generator import HELP_CONTENT_VERSION, HelpGeneratorDependency
from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.enums import Difficulty, WritingTaskType
from app.schemas.writing import (
    WritingAttemptAutosave,
    WritingAttemptCreate,
    WritingAttemptModeUpdate,
    WritingAttemptResponse,
    WritingAttemptSubmit,
    WritingEvaluationResponse,
    WritingHelpResponse,
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
from app.services.writing_attempt_service import (
    ActiveWritingAttemptError,
    WritingAttemptAlreadyFinishedError,
    WritingAttemptModeLockedError,
    WritingAttemptNotFoundError,
    WritingAttemptNotReadyError,
    WritingHelpUnavailableError,
    autosave_attempt,
    create_attempt,
    get_active_attempt,
    get_attempt,
    get_or_generate_help,
    set_attempt_mode,
    submit_attempt,
    utc_now,
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


def attempt_response(attempt) -> WritingAttemptResponse:
    submission = None
    if attempt.submission is not None:
        submission = WritingSubmissionResponse.model_validate(
            {
                "id": attempt.submission.id,
                "task": WritingTaskResponse.model_validate(attempt.submission.task),
                "answer_text": attempt.submission.answer_text,
                "word_count": attempt.submission.word_count,
                "submitted_at": attempt.submission.submitted_at,
                "evaluation": attempt.submission.evaluation,
                "attempt_type": attempt.attempt_type,
            }
        )
    return WritingAttemptResponse.model_validate(
        {
            "id": attempt.id,
            "task": WritingTaskResponse.model_validate(attempt.task),
            "help_mode_enabled": attempt.help_mode_enabled,
            "attempt_type": attempt.attempt_type,
            "status": attempt.status,
            "preparation_started_at": attempt.preparation_started_at,
            "preparation_expires_at": attempt.preparation_expires_at,
            "writing_started_at": attempt.writing_started_at,
            "writing_expires_at": attempt.writing_expires_at,
            "submitted_at": attempt.submitted_at,
            "answer_text": attempt.answer_text,
            "word_count": attempt.word_count,
            "help_sections_opened": attempt.help_sections_opened,
            "help_panel_open_count": attempt.help_panel_open_count,
            "help_visible_seconds": attempt.help_visible_seconds,
            "last_saved_at": attempt.last_saved_at,
            "server_time": utc_now(),
            "submission": submission,
        }
    )


@router.post(
    "/attempts", response_model=WritingAttemptResponse, status_code=status.HTTP_201_CREATED
)
async def start_attempt(
    data: WritingAttemptCreate, session: DatabaseSession, current_user: CurrentUser
) -> WritingAttemptResponse:
    try:
        return attempt_response(
            await create_attempt(session, user=current_user, task_type=data.task_type)
        )
    except NoUnseenWritingTaskError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No unseen approved exercises are currently available for this task type",
        ) from None
    except ActiveWritingAttemptError as exc:
        task_number = 1 if exc.attempt.task.task_type == WritingTaskType.EMAIL else 2
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Task {task_number} is already in progress. "
                "Finish or let that attempt expire before starting another task."
            ),
        ) from None


@router.get("/attempts/active", response_model=WritingAttemptResponse | None)
async def active_attempt(
    task_type: WritingTaskType, session: DatabaseSession, current_user: CurrentUser
) -> WritingAttemptResponse | None:
    attempt = await get_active_attempt(session, user_id=current_user.id, task_type=task_type)
    return attempt_response(attempt) if attempt else None


@router.get("/attempts/{attempt_id}", response_model=WritingAttemptResponse)
async def writing_attempt(
    attempt_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> WritingAttemptResponse:
    try:
        return attempt_response(
            await get_attempt(session, user_id=current_user.id, attempt_id=attempt_id)
        )
    except WritingAttemptNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing attempt not found"
        ) from None


@router.patch("/attempts/{attempt_id}/mode", response_model=WritingAttemptResponse)
async def update_attempt_mode(
    attempt_id: uuid.UUID,
    data: WritingAttemptModeUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> WritingAttemptResponse:
    try:
        return attempt_response(
            await set_attempt_mode(
                session,
                user_id=current_user.id,
                attempt_id=attempt_id,
                enabled=data.help_mode_enabled,
            )
        )
    except WritingAttemptNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing attempt not found"
        ) from None
    except WritingAttemptModeLockedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Help Mode is locked after the writing period begins",
        ) from None


@router.patch("/attempts/{attempt_id}/autosave", response_model=WritingAttemptResponse)
async def save_attempt(
    attempt_id: uuid.UUID,
    data: WritingAttemptAutosave,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> WritingAttemptResponse:
    try:
        attempt = await autosave_attempt(
            session,
            user_id=current_user.id,
            attempt_id=attempt_id,
            answer_text=data.answer_text,
            sections=data.help_sections_opened,
            open_count=data.help_panel_open_count,
            visible_seconds=data.help_visible_seconds,
        )
        return attempt_response(attempt)
    except WritingAttemptNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing attempt not found"
        ) from None
    except WritingAttemptNotReadyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="The writing period has not started"
        ) from None
    except WritingAttemptAlreadyFinishedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This writing attempt is already complete"
        ) from None


@router.get("/attempts/{attempt_id}/help", response_model=WritingHelpResponse)
async def attempt_help(
    attempt_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
    generator: HelpGeneratorDependency,
) -> WritingHelpResponse:
    try:
        content, is_demo = await get_or_generate_help(
            session, user=current_user, attempt_id=attempt_id, generator=generator
        )
        return WritingHelpResponse(
            content=content, content_version=HELP_CONTENT_VERSION, is_demo=is_demo
        )
    except WritingAttemptNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Help content is not available for this attempt",
        ) from None
    except WritingAttemptNotReadyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Help content becomes available when the writing period begins",
        ) from None
    except WritingHelpUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Guided help is temporarily unavailable. You can continue writing in standard mode."
            ),
        ) from None


@router.post("/attempts/{attempt_id}/submit", response_model=WritingAttemptResponse)
async def finish_attempt(
    attempt_id: uuid.UUID,
    data: WritingAttemptSubmit,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> WritingAttemptResponse:
    try:
        attempt = await submit_attempt(
            session,
            user_id=current_user.id,
            attempt_id=attempt_id,
            answer_text=data.answer_text,
            sections=data.help_sections_opened,
            open_count=data.help_panel_open_count,
            visible_seconds=data.help_visible_seconds,
        )
        return attempt_response(attempt)
    except WritingAttemptNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Writing attempt not found"
        ) from None
    except WritingAttemptNotReadyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="The writing period has not started"
        ) from None


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
    return WritingSubmissionListResponse(items=list(items), total=total, limit=limit, offset=offset)


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
async def progress(session: DatabaseSession, current_user: CurrentUser) -> WritingProgressResponse:
    return WritingProgressResponse.model_validate(
        await get_writing_progress(session, current_user), from_attributes=True
    )
