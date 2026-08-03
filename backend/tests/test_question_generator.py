import pytest

from app.ai.question_generator import (
    GeneratedQuestion,
    GeneratedQuestionBatch,
    question_generation_instructions,
    validate_generated_questions,
)
from app.models.enums import WritingTaskType
from app.services.task_quality_service import task_style_issues

TASK_1_PROMPT = (
    "You recently joined a neighbourhood gardening group, but the shared tool shed is "
    "often disorganized.\n"
    "Write an email to the volunteer coordinator to request improvements to the "
    "tool-storage system.\n"
    "Use a polite tone.\n"
    "In your email, address all three points below:\n"
    "• Describe the problem you have noticed.\n"
    "• Explain how the problem affects volunteers.\n"
    "• Suggest one practical improvement.\n"
    "Write approximately 150–200 words."
)

TASK_2_PROMPT = (
    "A community centre has funding for either a quiet study room or a larger fitness "
    "area. Both facilities would serve local residents, but only one can be built this "
    "year.\n"
    "Choose the better option for the community.\n"
    "Support your answer with reasons and examples.\n"
    "Write approximately 150–200 words."
)


def _question(prompt: str, scenario_key: str = "community-tool-storage") -> GeneratedQuestion:
    return GeneratedQuestion(
        category="Community",
        scenario_key=scenario_key,
        prompt=prompt,
        focus_tags=["TASK_FULFILLMENT", "ORGANIZATION"],
        target_score_min=7,
        target_score_max=12,
    )


def test_task_1_generation_instructions_encode_required_candidate_format() -> None:
    instructions = question_generation_instructions(WritingTaskType.EMAIL)

    assert "one clear communication purpose" in instructions
    assert "Write an email to [clearly identified recipient and purpose]." in instructions
    assert "Use a [polite, professional, friendly, formal, or respectful] tone." in instructions
    assert "exactly three bullet points" in instructions
    assert instructions.count("• [one primary objective]") == 3
    assert "one primary objective" in instructions
    assert "150–200 words" in instructions
    assert "sample answers" in instructions
    assert "Never invent or include personal names" in instructions
    assert "Do not use parentheses" in instructions
    assert (
        "Do not ask candidates to provide, include, mention, or invent dates or times"
        in instructions
    )


def test_task_2_generation_instructions_allow_five_balanced_formats() -> None:
    instructions = " ".join(
        question_generation_instructions(WritingTaskType.SURVEY).split()
    )

    for question_type in (
        "choose the better option",
        "agree or disagree",
        "which is more important",
        "recommendation",
        "preference",
    ):
        assert question_type in instructions
    assert "multiple defensible positions" in instructions
    assert "Support your answer with reasons and examples." in instructions


def test_generated_task_formats_pass_quality_validation() -> None:
    assert task_style_issues(WritingTaskType.EMAIL, TASK_1_PROMPT) == []
    assert task_style_issues(WritingTaskType.SURVEY, TASK_2_PROMPT) == []


def test_task_1_recipient_can_follow_the_situation_on_the_same_line() -> None:
    inline_recipient = TASK_1_PROMPT.replace(
        "group, but the shared tool shed is often disorganized.\nWrite an email",
        "group, but the shared tool shed is often disorganized. Write an email",
    )

    assert task_style_issues(WritingTaskType.EMAIL, inline_recipient) == []


def test_invalid_task_1_output_is_rejected_before_saving() -> None:
    invalid = TASK_1_PROMPT.replace("• Suggest one practical improvement.\n", "")
    batch = GeneratedQuestionBatch(questions=[_question(invalid)])

    with pytest.raises(RuntimeError, match="exactly three bullet points"):
        validate_generated_questions(
            batch,
            task_type=WritingTaskType.EMAIL,
            count=1,
            existing_scenarios=(),
        )


def test_numbered_task_1_points_are_rejected() -> None:
    numbered = TASK_1_PROMPT.replace("• Describe", "1. Describe")
    numbered = numbered.replace("• Explain", "2. Explain")
    numbered = numbered.replace("• Suggest", "3. Suggest")

    assert "exactly three bullet points" in " ".join(
        task_style_issues(WritingTaskType.EMAIL, numbered)
    )


def test_named_recipient_is_rejected() -> None:
    named = TASK_1_PROMPT.replace(
        "the volunteer coordinator",
        "your volunteer coordinator, Alex Chen",
    )

    assert "invented personal name" in " ".join(
        task_style_issues(WritingTaskType.EMAIL, named)
    )


def test_parenthetical_coaching_is_rejected() -> None:
    coached = TASK_1_PROMPT.replace(
        "Suggest one practical improvement.",
        "Suggest one practical improvement (be clear and reasonable).",
    )
    issues = " ".join(task_style_issues(WritingTaskType.EMAIL, coached))

    assert "parenthetical hints" in issues
    assert "Do not coach the candidate" in issues


def test_response_quality_instruction_is_rejected() -> None:
    coached = TASK_1_PROMPT.replace(
        "Write approximately 150–200 words.",
        "Keep your email focused and concise.\nWrite approximately 150–200 words.",
    )

    assert "Do not coach the candidate" in " ".join(
        task_style_issues(WritingTaskType.EMAIL, coached)
    )


def test_date_or_time_requirement_is_rejected() -> None:
    timed = TASK_1_PROMPT.replace(
        "Describe the problem you have noticed.",
        "Describe the problem and include dates or times.",
    )

    assert "provide dates or times" in " ".join(
        task_style_issues(WritingTaskType.EMAIL, timed)
    )


def test_repeated_scenario_is_rejected_before_saving() -> None:
    batch = GeneratedQuestionBatch(questions=[_question(TASK_1_PROMPT)])

    with pytest.raises(RuntimeError, match="repeated scenario"):
        validate_generated_questions(
            batch,
            task_type=WritingTaskType.EMAIL,
            count=1,
            existing_scenarios=("community-tool-storage",),
        )
