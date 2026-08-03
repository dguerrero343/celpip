from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    task_prompt: str
    answer_text: str
    current_score: float | None
    target_score: float
    weaknesses: tuple[str, ...]
    safety_identifier: str | None = None
    previous_objective: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class EvaluationOutput:
    model: str
    score: float
    task_fulfillment: float
    organization: float
    vocabulary: float
    grammar: float
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    corrections: tuple[dict[str, str], ...]
    recommended_next_steps: tuple[str, ...]
    raw_response: dict[str, object]
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    weakness_signals: tuple[dict[str, str], ...] = ()
    next_objective: dict[str, str] | None = None
    previous_objective_assessment: dict[str, str] | None = None
    evaluator_prompt_version: str = "legacy"


class AIProvider(Protocol):
    """Provider-neutral contract. HTTP controllers must never depend on vendor SDKs."""

    async def evaluate_writing(self, request: EvaluationInput) -> EvaluationOutput: ...
