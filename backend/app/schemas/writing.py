import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.help_generator import WritingHelpContent
from app.models.enums import Difficulty, WritingAttemptStatus, WritingAttemptType, WritingTaskType


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
    weakness_signals: list[dict[str, str]] = Field(default_factory=list)
    next_objective: dict[str, str] = Field(default_factory=dict)
    previous_objective_assessment: dict[str, str] = Field(default_factory=dict)
    evaluator_prompt_version: str = "legacy"
    created_at: datetime


class WritingSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task: WritingTaskResponse
    answer_text: str
    word_count: int
    submitted_at: datetime
    evaluation: WritingEvaluationResponse | None
    attempt_type: WritingAttemptType = WritingAttemptType.TEST_SIMULATION


class WritingSubmissionListResponse(BaseModel):
    items: list[WritingSubmissionResponse]
    total: int
    limit: int
    offset: int


class WritingProgressSummary(BaseModel):
    total_submissions: int
    evaluated_submissions: int
    average_score: float | None
    best_score: float | None
    last_evaluated_at: datetime | None


class WritingProgressResponse(WritingProgressSummary):
    current_score: float | None
    target_score: float | None
    test_simulation: WritingProgressSummary
    guided_practice: WritingProgressSummary


class WritingAttemptCreate(BaseModel):
    task_type: WritingTaskType


class WritingAttemptModeUpdate(BaseModel):
    help_mode_enabled: bool


class WritingAttemptAutosave(BaseModel):
    answer_text: str = Field(max_length=20_000)
    help_sections_opened: list[str] = Field(default_factory=list, max_length=5)
    help_panel_open_count: int = Field(default=0, ge=0, le=10_000)
    help_visible_seconds: int = Field(default=0, ge=0, le=100_000)

    @field_validator("help_sections_opened")
    @classmethod
    def normalize_sections(cls, value: list[str]) -> list[str]:
        allowed = {"structure", "frameworks", "vocabulary", "task_checklist", "quality_checklist"}
        return sorted(set(value) & allowed)


class WritingAttemptSubmit(WritingAttemptAutosave):
    pass


class WritingAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task: WritingTaskResponse
    help_mode_enabled: bool
    attempt_type: WritingAttemptType
    status: WritingAttemptStatus
    preparation_started_at: datetime
    preparation_expires_at: datetime
    writing_started_at: datetime
    writing_expires_at: datetime
    submitted_at: datetime | None
    answer_text: str
    word_count: int
    help_sections_opened: list[str]
    help_panel_open_count: int
    help_visible_seconds: int
    last_saved_at: datetime | None
    server_time: datetime
    submission: WritingSubmissionResponse | None = None


class WritingHelpResponse(BaseModel):
    content: WritingHelpContent
    content_version: str
    is_demo: bool
