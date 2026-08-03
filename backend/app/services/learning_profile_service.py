import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ai_provider import EvaluationOutput
from app.models.ai_student_context import AIStudentContext
from app.models.enums import (
    LearningObjectiveStatus,
    WeaknessTrend,
    WritingAttemptType,
)
from app.models.writing_learning_objective import WritingLearningObjective
from app.models.writing_weakness_observation import WritingWeaknessObservation

PROFILE_HISTORY_LIMIT = 200
PERSISTENT_WEAKNESS_LIMIT = 3
TEST_SIMULATION_WEIGHT = 1.0
GUIDED_PRACTICE_WEIGHT = 0.4
RECENCY_DECAY = 0.88


@dataclass(frozen=True, slots=True)
class PersistentWeakness:
    key: str
    label: str
    skill: str
    weighted_score: float
    total_frequency: int
    test_simulation_frequency: int
    guided_practice_frequency: int
    trend: WeaknessTrend


def _attempt_weight(attempt_type: WritingAttemptType) -> float:
    return (
        TEST_SIMULATION_WEIGHT
        if attempt_type == WritingAttemptType.TEST_SIMULATION
        else GUIDED_PRACTICE_WEIGHT
    )


async def get_pending_objective(
    session: AsyncSession, *, user_id: uuid.UUID, attempt_type: WritingAttemptType
) -> WritingLearningObjective | None:
    return await session.scalar(
        select(WritingLearningObjective)
        .where(
            WritingLearningObjective.user_id == user_id,
            WritingLearningObjective.status == LearningObjectiveStatus.PENDING,
            WritingLearningObjective.attempt_type == attempt_type,
        )
        .order_by(WritingLearningObjective.created_at.desc())
        .limit(1)
    )


async def get_persistent_weaknesses(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    fallback_context: AIStudentContext | None = None,
) -> tuple[PersistentWeakness, ...]:
    observations = list(
        (
            await session.scalars(
                select(WritingWeaknessObservation)
                .where(WritingWeaknessObservation.user_id == user_id)
                .order_by(
                    WritingWeaknessObservation.created_at.desc(),
                    WritingWeaknessObservation.id.desc(),
                )
                .limit(PROFILE_HISTORY_LIMIT)
            )
        ).all()
    )
    if not observations:
        if fallback_context is None:
            return ()
        return tuple(
            PersistentWeakness(
                key=f"legacy_{index}",
                label=label,
                skill="legacy",
                weighted_score=1.0,
                total_frequency=1,
                test_simulation_frequency=1,
                guided_practice_frequency=0,
                trend=WeaknessTrend.STABLE,
            )
            for index, label in enumerate(fallback_context.main_weaknesses[:3])
        )

    frequency_rows = (
        await session.execute(
            select(
                WritingWeaknessObservation.weakness_key,
                WritingWeaknessObservation.attempt_type,
                func.count(WritingWeaknessObservation.id),
            )
            .where(
                WritingWeaknessObservation.user_id == user_id,
                WritingWeaknessObservation.is_present.is_(True),
            )
            .group_by(
                WritingWeaknessObservation.weakness_key,
                WritingWeaknessObservation.attempt_type,
            )
        )
    ).all()
    exact_frequency: dict[str, dict[WritingAttemptType, int]] = defaultdict(dict)
    for key, attempt_type, count in frequency_rows:
        exact_frequency[key][attempt_type] = int(count)

    submission_ranks: dict[uuid.UUID, int] = {}
    aggregate: dict[str, dict[str, object]] = {}
    for item in observations:
        if item.submission_id not in submission_ranks:
            submission_ranks[item.submission_id] = len(submission_ranks)
        recency = RECENCY_DECAY ** submission_ranks[item.submission_id]
        base_weight = _attempt_weight(item.attempt_type) * recency
        state = aggregate.setdefault(
            item.weakness_key,
            {
                "label": item.weakness_label,
                "skill": item.skill,
                "score": 0.0,
                "trend": item.trend,
            },
        )
        if item.is_present:
            trend_multiplier = 1.2 if item.trend == WeaknessTrend.WORSENED else 1.0
            state["score"] = float(state["score"]) + base_weight * trend_multiplier
        else:
            state["score"] = float(state["score"]) - base_weight * 0.75

    ranked = sorted(
        (
            PersistentWeakness(
                key=key,
                label=str(value["label"]),
                skill=str(value["skill"]),
                weighted_score=round(float(value["score"]), 4),
                total_frequency=sum(exact_frequency[key].values()),
                test_simulation_frequency=exact_frequency[key].get(
                    WritingAttemptType.TEST_SIMULATION, 0
                ),
                guided_practice_frequency=exact_frequency[key].get(
                    WritingAttemptType.GUIDED_PRACTICE, 0
                ),
                trend=value["trend"],  # type: ignore[arg-type]
            )
            for key, value in aggregate.items()
            if float(value["score"]) > 0
        ),
        key=lambda item: (-item.weighted_score, -item.test_simulation_frequency, item.key),
    )
    return tuple(ranked[:PERSISTENT_WEAKNESS_LIMIT])


def _rubric_score(output: EvaluationOutput, skill: str) -> float:
    return {
        "task_fulfillment": output.task_fulfillment,
        "organization": output.organization,
        "vocabulary": output.vocabulary,
        "grammar": output.grammar,
        "tone": output.task_fulfillment,
        "idea_development": output.task_fulfillment,
    }.get(skill, output.score)


async def record_learning_result(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    submission_id: uuid.UUID,
    attempt_type: WritingAttemptType,
    output: EvaluationOutput,
    prior_objective: WritingLearningObjective | None,
    persistent_before: tuple[PersistentWeakness, ...],
) -> None:
    signals = {str(item["issue_key"]): item for item in output.weakness_signals}
    previous_rows = list(
        (
            await session.scalars(
                select(WritingWeaknessObservation)
                .where(
                    WritingWeaknessObservation.user_id == user_id,
                    WritingWeaknessObservation.attempt_type == attempt_type,
                    WritingWeaknessObservation.weakness_key.in_(signals),
                )
                .order_by(WritingWeaknessObservation.created_at.desc())
            )
        ).all()
    )
    previous_by_key: dict[str, WritingWeaknessObservation] = {}
    for row in previous_rows:
        previous_by_key.setdefault(row.weakness_key, row)

    for key, signal in signals.items():
        skill = str(signal["skill"])
        score = _rubric_score(output, skill)
        previous = previous_by_key.get(key)
        if previous is None:
            trend = WeaknessTrend.NEW
        elif not previous.is_present or score <= float(previous.rubric_score) - 0.5:
            trend = WeaknessTrend.WORSENED
        elif score >= float(previous.rubric_score) + 0.5:
            trend = WeaknessTrend.IMPROVED
        else:
            trend = WeaknessTrend.STABLE
        session.add(
            WritingWeaknessObservation(
                user_id=user_id,
                submission_id=submission_id,
                weakness_key=key,
                weakness_label=str(signal["label"]),
                skill=skill,
                trend=trend,
                is_present=True,
                attempt_type=attempt_type,
                rubric_score=score,
            )
        )

    for prior in persistent_before:
        if prior.key.startswith("legacy_") or prior.key in signals:
            continue
        session.add(
            WritingWeaknessObservation(
                user_id=user_id,
                submission_id=submission_id,
                weakness_key=prior.key,
                weakness_label=prior.label,
                skill=prior.skill,
                trend=WeaknessTrend.IMPROVED,
                is_present=False,
                attempt_type=attempt_type,
                rubric_score=_rubric_score(output, prior.skill),
            )
        )

    assessment = output.previous_objective_assessment or {}
    if prior_objective is not None:
        prior_objective.status = LearningObjectiveStatus(str(assessment["status"]))
        prior_objective.assessment_explanation = str(assessment["explanation"])
        prior_objective.assessed_submission_id = submission_id
        prior_objective.assessed_at = datetime.now(UTC)

    objective = output.next_objective or {}
    session.add(
        WritingLearningObjective(
            user_id=user_id,
            source_submission_id=submission_id,
            attempt_type=attempt_type,
            skill=str(objective["skill"]),
            objective=str(objective["objective"]),
            success_criteria=str(objective["success_criteria"]),
        )
    )


@dataclass(frozen=True, slots=True)
class ConsistencyMetric:
    prompt_version: str
    attempt_type: WritingAttemptType
    evaluation_count: int
    average_score: float
    score_standard_deviation: float
    average_change_from_prior: float | None


def build_consistency_metrics(
    rows: list[tuple[str, WritingAttemptType, uuid.UUID, datetime, Decimal]],
) -> list[ConsistencyMetric]:
    grouped: dict[tuple[str, WritingAttemptType], list[tuple[uuid.UUID, datetime, float]]] = (
        defaultdict(list)
    )
    for version, attempt_type, user_id, created_at, score in rows:
        grouped[(version, attempt_type)].append((user_id, created_at, float(score)))

    metrics: list[ConsistencyMetric] = []
    for (version, attempt_type), values in sorted(grouped.items(), key=lambda item: item[0]):
        scores = [value[2] for value in values]
        average = sum(scores) / len(scores)
        variance = sum((score - average) ** 2 for score in scores) / len(scores)
        changes: list[float] = []
        by_user: dict[uuid.UUID, list[tuple[datetime, float]]] = defaultdict(list)
        for user_id, created_at, score in values:
            by_user[user_id].append((created_at, score))
        for user_scores in by_user.values():
            ordered = sorted(user_scores)
            changes.extend(
                abs(current[1] - previous[1])
                for previous, current in zip(ordered, ordered[1:], strict=False)
            )
        metrics.append(
            ConsistencyMetric(
                prompt_version=version,
                attempt_type=attempt_type,
                evaluation_count=len(scores),
                average_score=round(average, 2),
                score_standard_deviation=round(math.sqrt(variance), 2),
                average_change_from_prior=(
                    round(sum(changes) / len(changes), 2) if changes else None
                ),
            )
        )
    return metrics
