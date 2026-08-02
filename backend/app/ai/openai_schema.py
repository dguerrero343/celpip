from pydantic import BaseModel, ConfigDict, field_validator


class WritingCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: str
    revised: str
    explanation: str


class StructuredWritingEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    task_fulfillment: float
    organization: float
    vocabulary: float
    grammar: float
    strengths: list[str]
    weaknesses: list[str]
    corrections: list[WritingCorrection]
    recommended_next_steps: list[str]

    @field_validator(
        "score", "task_fulfillment", "organization", "vocabulary", "grammar"
    )
    @classmethod
    def score_is_on_celpip_scale(cls, value: float) -> float:
        if not 1 <= value <= 12:
            raise ValueError("CELPIP scores must be between 1 and 12")
        return value
