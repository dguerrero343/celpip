import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    Difficulty,
    UserRole,
    WritingAttemptStatus,
    WritingAttemptType,
    WritingTaskSource,
    WritingTaskStatus,
    WritingTaskType,
)


class AdminTaskCreate(BaseModel):
    task_type: WritingTaskType
    category: str = Field(min_length=2, max_length=100)
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    prompt: str = Field(min_length=80, max_length=4000)
    scenario_key: str | None = Field(default=None, max_length=160)
    focus_tags: list[str] = Field(default_factory=list, max_length=12)
    target_score_min: int = Field(default=1, ge=1, le=12)
    target_score_max: int = Field(default=12, ge=1, le=12)

    @field_validator("category", "prompt")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("scenario_key")
    @classmethod
    def normalize_scenario_key(cls, value: str | None) -> str | None:
        return value.strip().lower() if value and value.strip() else None

    @field_validator("focus_tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return list(
            dict.fromkeys(item.strip().upper().replace(" ", "_") for item in value if item.strip())
        )

    @model_validator(mode="after")
    def validate_score_band(self) -> "AdminTaskCreate":
        if self.target_score_min > self.target_score_max:
            raise ValueError("target_score_min must not exceed target_score_max")
        return self


class AdminTaskUpdate(AdminTaskCreate):
    pass


class AdminTaskStatusUpdate(BaseModel):
    status: WritingTaskStatus


class AdminGenerateTasksRequest(BaseModel):
    task_type: WritingTaskType
    count: int = Field(default=3, ge=1, le=5)
    category: str | None = Field(default=None, max_length=100)


class AdminGenerateTasksResponse(BaseModel):
    items: list["AdminTaskResponse"]
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class AdminTaskResponse(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    task_type: WritingTaskType
    category: str
    difficulty: Difficulty
    prompt: str
    status: WritingTaskStatus
    source: WritingTaskSource
    scenario_key: str | None
    focus_tags: list[str]
    target_score_min: int
    target_score_max: int
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    assignment_count: int = 0
    submission_count: int = 0
    style_issues: list[str] = Field(default_factory=list)


class AdminTaskListResponse(BaseModel):
    items: list[AdminTaskResponse]
    total: int


class AdminQuestionBankSummary(BaseModel):
    total_tasks: int
    approved_tasks: int
    draft_tasks: int
    in_review_tasks: int
    retired_tasks: int
    email_tasks: int
    survey_tasks: int
    total_assignments: int
    total_submissions: int
    unique_students: int


class EvaluationConsistencyMetricResponse(BaseModel):
    prompt_version: str
    attempt_type: WritingAttemptType
    evaluation_count: int
    average_score: float
    score_standard_deviation: float
    average_change_from_prior: float | None


class EvaluationConsistencyResponse(BaseModel):
    metrics: list[EvaluationConsistencyMetricResponse]
    guidance: str


class AdminUserSummaryResponse(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    role: UserRole
    current_score: int | None
    target_score: int | None
    registered_at: datetime
    last_activity_at: datetime
    assigned_exercises: int
    attempts_started: int
    active_attempts: int
    exercises_completed: int
    guided_practice_completed: int
    test_simulation_completed: int
    total_practice_seconds: int
    average_test_score: float | None
    average_guided_score: float | None
    ai_request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class AdminUserSummaryListResponse(BaseModel):
    items: list[AdminUserSummaryResponse]
    total: int
    limit: int
    offset: int


class AdminUserAttemptResponse(BaseModel):
    id: uuid.UUID
    task_type: WritingTaskType
    category: str
    status: WritingAttemptStatus
    attempt_type: WritingAttemptType
    help_mode_enabled: bool
    started_at: datetime
    submitted_at: datetime | None
    elapsed_seconds: int
    word_count: int
    estimated_score: float | None


class AdminUserUsageBreakdownResponse(BaseModel):
    request_type: str
    model: str
    request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class AdminUserDetailResponse(BaseModel):
    summary: AdminUserSummaryResponse
    recent_attempts: list[AdminUserAttemptResponse]
    ai_usage_breakdown: list[AdminUserUsageBreakdownResponse]
