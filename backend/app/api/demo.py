from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import DatabaseSession
from app.core.config import settings
from app.schemas.demo import (
    DemoDashboardResponse,
    DemoScorePointResponse,
    DemoStudentResponse,
)
from app.schemas.writing import (
    WritingProgressResponse,
    WritingSubmissionResponse,
    WritingTaskResponse,
)
from app.services.demo_service import DemoDataNotFoundError, get_demo_dashboard

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/dashboard", response_model=DemoDashboardResponse)
async def dashboard(session: DatabaseSession) -> DemoDashboardResponse:
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    try:
        data = await get_demo_dashboard(session)
    except DemoDataNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo data is not loaded",
        ) from None

    return DemoDashboardResponse(
        student=DemoStudentResponse(
            first_name=data.user.first_name,
            current_score=float(data.context.current_score),
            target_score=float(data.context.target_score),
            recommended_strategy=data.context.recommended_strategy,
            focus_areas=[
                *data.context.grammar_focus,
                *data.context.vocabulary_focus,
            ],
        ),
        progress=WritingProgressResponse.model_validate(data.progress, from_attributes=True),
        exercises=[WritingTaskResponse.model_validate(item) for item in data.exercises],
        submissions=[WritingSubmissionResponse.model_validate(item) for item in data.submissions],
        score_history=[
            DemoScorePointResponse(date=item.date, score=float(item.score))
            for item in data.score_history
        ],
    )
