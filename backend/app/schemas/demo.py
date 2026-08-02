from datetime import date

from pydantic import BaseModel

from app.schemas.writing import (
    WritingProgressResponse,
    WritingSubmissionResponse,
    WritingTaskResponse,
)


class DemoStudentResponse(BaseModel):
    first_name: str
    current_score: float
    target_score: float
    recommended_strategy: str
    focus_areas: list[str]


class DemoScorePointResponse(BaseModel):
    date: date
    score: float


class DemoDashboardResponse(BaseModel):
    student: DemoStudentResponse
    progress: WritingProgressResponse
    exercises: list[WritingTaskResponse]
    submissions: list[WritingSubmissionResponse]
    score_history: list[DemoScorePointResponse]
