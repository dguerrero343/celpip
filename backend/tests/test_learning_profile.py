import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.enums import WritingAttemptType
from app.services.learning_profile_service import build_consistency_metrics


def test_consistency_metrics_keep_attempt_types_and_prompt_versions_separate() -> None:
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    metrics = build_consistency_metrics(
        [
            (
                "2026-08-02.v2",
                WritingAttemptType.TEST_SIMULATION,
                user_id,
                now,
                Decimal("8.0"),
            ),
            (
                "2026-08-02.v2",
                WritingAttemptType.TEST_SIMULATION,
                user_id,
                now + timedelta(days=1),
                Decimal("9.0"),
            ),
            (
                "2026-08-02.v2",
                WritingAttemptType.GUIDED_PRACTICE,
                user_id,
                now,
                Decimal("10.0"),
            ),
        ]
    )

    test_metric = next(
        item for item in metrics if item.attempt_type == WritingAttemptType.TEST_SIMULATION
    )
    guided_metric = next(
        item for item in metrics if item.attempt_type == WritingAttemptType.GUIDED_PRACTICE
    )
    assert test_metric.evaluation_count == 2
    assert test_metric.average_score == 8.5
    assert test_metric.score_standard_deviation == 0.5
    assert test_metric.average_change_from_prior == 1.0
    assert guided_metric.evaluation_count == 1
    assert guided_metric.average_change_from_prior is None
