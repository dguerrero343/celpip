import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Difficulty, WritingTaskType


class WritingTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_type: WritingTaskType
    category: str
    difficulty: Difficulty
    prompt: str
    created_at: datetime


class WritingTaskListResponse(BaseModel):
    items: list[WritingTaskResponse]
    total: int
    limit: int
    offset: int


class WritingTaskNextRequest(BaseModel):
    task_type: WritingTaskType


class WritingTaskAssignmentResponse(BaseModel):
    assignment_id: uuid.UUID
    task: WritingTaskResponse


class WritingSubmissionCreate(BaseModel):
    task_id: uuid.UUID
    answer_text: str = Field(min_length=1, max_length=20_000)

    @field_validator("answer_text")
    @classmethod
    def normalize_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer_text cannot be blank")
        return value


class WritingEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estimated_score: float
    task_fulfillment_score: float
    organization_score: float
    vocabulary_score: float
    grammar_score: float
    score_gap: float
    strengths: list[str]
    weaknesses: list[str]
    corrections: list[dict[str, str]]
    recommended_exercises: list[str]
    created_at: datetime


class WritingSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task: WritingTaskResponse
    answer_text: str
    word_count: int
    submitted_at: datetime
    evaluation: WritingEvaluationResponse | None


class WritingSubmissionListResponse(BaseModel):
    items: list[WritingSubmissionResponse]
    total: int
    limit: int
    offset: int


class WritingProgressResponse(BaseModel):
    total_submissions: int
    evaluated_submissions: int
    current_score: float | None
    target_score: float | None
    average_score: float | None
    best_score: float | None
    last_evaluated_at: datetime | None
