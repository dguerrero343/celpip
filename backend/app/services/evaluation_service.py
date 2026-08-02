import hashlib
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ai_provider import AIProvider, EvaluationInput, EvaluationOutput
from app.models.ai_student_context import AIStudentContext
from app.models.ai_usage import AIUsage
from app.models.enums import Skill
from app.models.user import User
from app.models.user_score_history import UserScoreHistory
from app.models.writing_evaluation import WritingEvaluation
from app.services.writing_service import get_writing_submission

SCORE_QUANTUM = Decimal("0.1")
GRAMMAR_TERMS = ("grammar", "sentence", "punctuation", "verb", "article", "agreement")
VOCABULARY_TERMS = ("vocabulary", "word", "lexical", "repetition", "idiom")


class TargetScoreRequiredError(Exception):
    """Raised when evaluation cannot calculate progress toward a target score."""


class EvaluationProviderError(Exception):
    """Raised when the configured evaluator fails."""


class EvaluationProviderNotConfiguredError(Exception):
    """Raised when an unevaluated submission has no configured evaluator."""


class InvalidEvaluationOutputError(Exception):
    """Raised when an evaluator returns values outside the persistence contract."""


def _decimal(value: float | Decimal) -> Decimal:
    try:
        return Decimal(str(value)).quantize(SCORE_QUANTUM)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidEvaluationOutputError from exc


def _validate_output(output: EvaluationOutput) -> dict[str, Decimal]:
    scores = {
        "estimated_score": _decimal(output.score),
        "task_fulfillment_score": _decimal(output.task_fulfillment),
        "organization_score": _decimal(output.organization),
        "vocabulary_score": _decimal(output.vocabulary),
        "grammar_score": _decimal(output.grammar),
    }
    if any(score < 1 or score > 12 for score in scores.values()):
        raise InvalidEvaluationOutputError
    try:
        estimated_cost = Decimal(str(output.estimated_cost))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidEvaluationOutputError from exc
    if output.input_tokens < 0 or output.output_tokens < 0 or estimated_cost < 0:
        raise InvalidEvaluationOutputError
    if not output.model.strip():
        raise InvalidEvaluationOutputError
    return scores


def _focus_items(weaknesses: tuple[str, ...], terms: tuple[str, ...]) -> list[str]:
    return [item for item in weaknesses if any(term in item.lower() for term in terms)]


async def evaluate_writing_submission(
    session: AsyncSession,
    *,
    user: User,
    submission_id: uuid.UUID,
    provider: AIProvider | None,
) -> WritingEvaluation:
    submission = await get_writing_submission(
        session, user_id=user.id, submission_id=submission_id
    )
    if submission.evaluation is not None:
        return submission.evaluation
    if provider is None:
        raise EvaluationProviderNotConfiguredError
    if user.target_celpip_score is None:
        raise TargetScoreRequiredError

    context = await session.get(AIStudentContext, user.id)
    request = EvaluationInput(
        task_prompt=submission.task.prompt,
        answer_text=submission.answer_text,
        current_score=(
            float(context.current_score)
            if context is not None
            else float(user.current_celpip_score) if user.current_celpip_score else None
        ),
        target_score=float(user.target_celpip_score),
        weaknesses=tuple(context.main_weaknesses) if context is not None else (),
        safety_identifier=hashlib.sha256(str(user.id).encode("utf-8")).hexdigest(),
    )
    try:
        output = await provider.evaluate_writing(request)
    except Exception as exc:
        raise EvaluationProviderError from exc

    scores = _validate_output(output)
    target_score = Decimal(user.target_celpip_score).quantize(SCORE_QUANTUM)
    score_gap = target_score - scores["estimated_score"]
    evaluation = WritingEvaluation(
        submission_id=submission.id,
        score_gap=score_gap,
        strengths=list(output.strengths),
        weaknesses=list(output.weaknesses),
        corrections=list(output.corrections),
        recommended_exercises=list(output.recommended_next_steps),
        ai_raw_response=output.raw_response,
        **scores,
    )
    session.add(evaluation)
    session.add(
        UserScoreHistory(
            user_id=user.id,
            skill=Skill.WRITING,
            score=scores["estimated_score"],
            date=datetime.now(UTC).date(),
        )
    )
    session.add(
        AIUsage(
            user_id=user.id,
            model=output.model,
            input_tokens=output.input_tokens,
            output_tokens=output.output_tokens,
            estimated_cost=Decimal(str(output.estimated_cost)),
            request_type="writing_evaluation",
        )
    )

    strategy = " ".join(output.recommended_next_steps).strip()
    context_values = {
        "current_score": scores["estimated_score"],
        "target_score": target_score,
        "score_gap": score_gap,
        "main_weaknesses": list(output.weaknesses),
        "grammar_focus": _focus_items(output.weaknesses, GRAMMAR_TERMS),
        "vocabulary_focus": _focus_items(output.weaknesses, VOCABULARY_TERMS),
        "recommended_strategy": strategy or "Continue targeted CELPIP writing practice.",
    }
    if context is None:
        session.add(AIStudentContext(user_id=user.id, **context_values))
    else:
        for field, value in context_values.items():
            setattr(context, field, value)

    user.current_celpip_score = int(
        scores["estimated_score"].to_integral_value(rounding=ROUND_HALF_UP)
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_writing_submission(
            session, user_id=user.id, submission_id=submission_id
        )
        if existing.evaluation is not None:
            return existing.evaluation
        raise
    await session.refresh(evaluation)
    return evaluation
