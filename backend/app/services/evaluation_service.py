import hashlib
import re
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ai_provider import AIProvider, EvaluationInput, EvaluationOutput
from app.models.ai_student_context import AIStudentContext
from app.models.ai_usage import AIUsage
from app.models.enums import LearningObjectiveStatus, Skill
from app.models.user import User
from app.models.user_score_history import UserScoreHistory
from app.models.writing_evaluation import WritingEvaluation
from app.services.learning_profile_service import (
    get_pending_objective,
    get_persistent_weaknesses,
    record_learning_result,
)
from app.services.writing_service import get_writing_submission

SCORE_QUANTUM = Decimal("0.1")
GRAMMAR_TERMS = ("grammar", "sentence", "punctuation", "verb", "article", "agreement")
VOCABULARY_TERMS = ("vocabulary", "word", "lexical", "repetition", "idiom")
ISSUE_KEY_PATTERN = re.compile(r"^[a-z0-9_]{2,80}$")
WRITING_SKILLS = {
    "task_fulfillment",
    "organization",
    "vocabulary",
    "grammar",
    "tone",
    "idea_development",
}


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
    if not output.evaluator_prompt_version.strip():
        raise InvalidEvaluationOutputError
    if output.next_objective is None or output.previous_objective_assessment is None:
        raise InvalidEvaluationOutputError
    required_objective = {"skill", "objective", "success_criteria"}
    if set(output.next_objective) != required_objective:
        raise InvalidEvaluationOutputError
    if str(output.next_objective["skill"]) not in WRITING_SKILLS:
        raise InvalidEvaluationOutputError
    if not str(output.next_objective["objective"]).strip() or not str(
        output.next_objective["success_criteria"]
    ).strip():
        raise InvalidEvaluationOutputError
    required_assessment = {"status", "explanation"}
    if set(output.previous_objective_assessment) != required_assessment:
        raise InvalidEvaluationOutputError
    signal_keys: set[str] = set()
    if len(output.weakness_signals) > 5:
        raise InvalidEvaluationOutputError
    for signal in output.weakness_signals:
        if set(signal) != {"skill", "issue_key", "label"}:
            raise InvalidEvaluationOutputError
        key = str(signal["issue_key"])
        if (
            not ISSUE_KEY_PATTERN.fullmatch(key)
            or key in signal_keys
            or str(signal["skill"]) not in WRITING_SKILLS
            or not str(signal["label"]).strip()
        ):
            raise InvalidEvaluationOutputError
        signal_keys.add(key)
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
    submission = await get_writing_submission(session, user_id=user.id, submission_id=submission_id)
    if submission.evaluation is not None:
        return submission.evaluation
    if provider is None:
        raise EvaluationProviderNotConfiguredError
    if user.target_celpip_score is None:
        raise TargetScoreRequiredError

    context = await session.get(AIStudentContext, user.id)
    persistent_before = await get_persistent_weaknesses(
        session, user_id=user.id, fallback_context=context
    )
    prior_objective = await get_pending_objective(
        session, user_id=user.id, attempt_type=submission.attempt_type
    )
    request = EvaluationInput(
        task_prompt=submission.task.prompt,
        answer_text=submission.answer_text,
        current_score=(
            float(context.current_score)
            if context is not None
            else float(user.current_celpip_score)
            if user.current_celpip_score
            else None
        ),
        target_score=float(user.target_celpip_score),
        weaknesses=tuple(item.label for item in persistent_before),
        safety_identifier=hashlib.sha256(str(user.id).encode("utf-8")).hexdigest(),
        previous_objective=(
            {
                "skill": prior_objective.skill,
                "objective": prior_objective.objective,
                "success_criteria": prior_objective.success_criteria,
            }
            if prior_objective is not None
            else None
        ),
    )
    try:
        output = await provider.evaluate_writing(request)
    except Exception as exc:
        raise EvaluationProviderError from exc

    scores = _validate_output(output)
    assessment_status = str(output.previous_objective_assessment["status"])
    if prior_objective is None and assessment_status != "NOT_APPLICABLE":
        raise InvalidEvaluationOutputError
    if prior_objective is not None and assessment_status == "NOT_APPLICABLE":
        raise InvalidEvaluationOutputError
    if prior_objective is not None:
        try:
            LearningObjectiveStatus(assessment_status)
        except ValueError as exc:
            raise InvalidEvaluationOutputError from exc
    target_score = Decimal(user.target_celpip_score).quantize(SCORE_QUANTUM)
    score_gap = target_score - scores["estimated_score"]
    evaluation = WritingEvaluation(
        submission_id=submission.id,
        score_gap=score_gap,
        strengths=list(output.strengths),
        weaknesses=list(output.weaknesses),
        corrections=list(output.corrections),
        recommended_exercises=list(output.recommended_next_steps),
        weakness_signals=list(output.weakness_signals),
        next_objective=output.next_objective,
        previous_objective_assessment=output.previous_objective_assessment,
        evaluator_prompt_version=output.evaluator_prompt_version,
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
            attempt_type=submission.attempt_type,
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

    await record_learning_result(
        session,
        user_id=user.id,
        submission_id=submission.id,
        attempt_type=submission.attempt_type,
        output=output,
        prior_objective=prior_objective,
        persistent_before=persistent_before,
    )
    persistent_after = await get_persistent_weaknesses(
        session, user_id=user.id, fallback_context=context
    )
    persistent_labels = [item.label for item in persistent_after]

    strategy = str(output.next_objective["objective"]).strip()
    is_test_simulation = submission.attempt_type.value == "TEST_SIMULATION"
    profile_score = (
        scores["estimated_score"]
        if is_test_simulation
        else context.current_score
        if context is not None
        else Decimal(user.current_celpip_score)
        if user.current_celpip_score is not None
        else scores["estimated_score"]
    )
    context_values = {
        "current_score": profile_score,
        "target_score": target_score,
        "score_gap": target_score - profile_score,
        "main_weaknesses": persistent_labels,
        "grammar_focus": _focus_items(tuple(persistent_labels), GRAMMAR_TERMS),
        "vocabulary_focus": _focus_items(tuple(persistent_labels), VOCABULARY_TERMS),
        "recommended_strategy": strategy or "Continue targeted CELPIP writing practice.",
    }
    if context is None:
        session.add(AIStudentContext(user_id=user.id, **context_values))
    else:
        for field, value in context_values.items():
            setattr(context, field, value)

    if is_test_simulation:
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
