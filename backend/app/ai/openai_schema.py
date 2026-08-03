from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WritingSkillArea(StrEnum):
    TASK_FULFILLMENT = "task_fulfillment"
    ORGANIZATION = "organization"
    VOCABULARY = "vocabulary"
    GRAMMAR = "grammar"
    TONE = "tone"
    IDEA_DEVELOPMENT = "idea_development"


class ObjectiveAssessmentStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ACHIEVED = "ACHIEVED"
    PARTIALLY_ACHIEVED = "PARTIALLY_ACHIEVED"
    NOT_ACHIEVED = "NOT_ACHIEVED"


class WritingCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: str
    revised: str
    explanation: str


class WeaknessSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: WritingSkillArea
    issue_key: str = Field(pattern=r"^[a-z0-9_]{2,80}$")
    label: str = Field(min_length=3, max_length=240)


class NextLearningObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: WritingSkillArea
    objective: str = Field(min_length=10, max_length=300)
    success_criteria: str = Field(min_length=10, max_length=300)


class PreviousObjectiveAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ObjectiveAssessmentStatus
    explanation: str = Field(min_length=3, max_length=300)


class StructuredWritingEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    task_fulfillment: float
    organization: float
    vocabulary: float
    grammar: float
    strengths: list[str]
    weaknesses: list[str]
    weakness_signals: list[WeaknessSignal] = Field(max_length=5)
    corrections: list[WritingCorrection]
    recommended_next_steps: list[str]
    next_objective: NextLearningObjective
    previous_objective_assessment: PreviousObjectiveAssessment

    @field_validator("score", "task_fulfillment", "organization", "vocabulary", "grammar")
    @classmethod
    def score_is_on_celpip_scale(cls, value: float) -> float:
        if not 1 <= value <= 12:
            raise ValueError("CELPIP scores must be between 1 and 12")
        return value
