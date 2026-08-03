import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Protocol

from fastapi import Depends
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings
from app.models.enums import WritingTaskType
from app.services.task_quality_service import task_style_issues

ONE_MILLION = Decimal("1000000")
QUESTION_GENERATOR_PROMPT_VERSION = "celpip-question-generator.v4"

COMMON_GENERATION_RULES = """You are an expert CELPIP test developer. Create original,
realistic CELPIP Writing practice prompts that match the public test's style, balance,
accessibility, and difficulty without copying or closely paraphrasing official questions.

For every draft:
- Use one believable everyday situation for adult English learners targeting CELPIP levels 7–12.
- Test organization, tone, grammar, vocabulary, task fulfillment, and reasoning—not
  reading, memory, research, or specialized knowledge.
- Avoid political, religious, highly emotional, controversial, or sensitive scenarios.
- Never invent or include personal names. Refer to people and organizations only by a
  generic relationship or role, such as your neighbour, the building manager, your
  supervisor, the service department, or the community centre.
- Do not use parentheses, square brackets, braces, or parenthetical asides in the
  candidate-facing prompt.
- Do not tell candidates to be clear, specific, reasonable, concise, or otherwise coach
  the quality of their response.
- Do not ask candidates to provide, include, mention, or invent dates or times.
- Use a distinct setting, recipient or decision maker, purpose, and requested action.
  Do not reuse or closely resemble the supplied scenario keys or another batch draft.
- Prefer Canadian everyday contexts such as housing, employment, education, community,
  transportation, appointments, services, volunteering, events, neighbourhoods,
  shopping, travel, banking, insurance, utilities, childcare, pets, public services,
  technology, work-life balance, or personal development.
- Keep the situation focused and free of unnecessary details.
- Put only the candidate-facing question in the prompt field. Do not include explanations,
  notes, scoring criteria, sample answers, or instructions to the AI.
- Supply concise metadata in the other schema fields. Use a unique lowercase hyphenated
  scenario_key and 2–6 relevant uppercase focus_tags.
"""

TASK_1_GENERATION_RULES = """Generate CELPIP Writing Task 1 email prompts.

Each prompt must have one clear communication purpose and exactly this structure:
You [brief situation].
Write an email to [clearly identified recipient and purpose].
Use a [polite, professional, friendly, formal, or respectful] tone.
In your email, address all three points below:
• [one primary objective]
• [one primary objective]
• [one primary objective]
Write approximately 150–200 words.

Use exactly three bullet points marked with the `•` character. Make every point distinct
and limited to one primary objective. Do not hide several requests inside one point. The
scenario must naturally support all three points and must not combine unrelated
situations. A strong candidate
should have enough scope to develop ideas at Level 12, while a Level 7 candidate can
still understand the task immediately.
"""

TASK_2_GENERATION_RULES = """Generate CELPIP Writing Task 2 opinion prompts.

For each prompt, randomly select exactly one format: choose the better option, agree or
disagree, which is more important, recommendation, or preference. Vary the format across
a multi-draft batch.

Each prompt must:
- Begin with short, realistic background information.
- Present a balanced everyday issue with multiple defensible positions and no obvious
  correct answer.
- Clearly ask the candidate to choose one option, state an opinion, or make a recommendation.
- Invite comparison, reasons, and examples without requiring expert knowledge.
- End with "Support your answer with reasons and examples." and "Write approximately 150–200 words."

Do not make the issue overly broad, vague, answerable in one sentence, or dependent on
unnecessary details.
"""


def question_generation_instructions(task_type: WritingTaskType) -> str:
    task_rules = (
        TASK_1_GENERATION_RULES
        if task_type == WritingTaskType.EMAIL
        else TASK_2_GENERATION_RULES
    )
    return f"{COMMON_GENERATION_RULES}\n{task_rules}".strip()


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=2, max_length=100)
    scenario_key: str = Field(
        min_length=4,
        max_length=160,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    prompt: str = Field(min_length=100, max_length=4000)
    focus_tags: list[str] = Field(min_length=2, max_length=6)
    target_score_min: int = Field(ge=1, le=12)
    target_score_max: int = Field(ge=1, le=12)

    @field_validator("category", "prompt")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("focus_tags")
    @classmethod
    def normalize_focus_tags(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper().replace(" ", "_") for item in value]
        result = list(dict.fromkeys(item for item in normalized if item))
        if len(result) < 2:
            raise ValueError("At least two distinct focus tags are required")
        return result

    @model_validator(mode="after")
    def validate_score_range(self) -> "GeneratedQuestion":
        if self.target_score_min > self.target_score_max:
            raise ValueError("target_score_min must not exceed target_score_max")
        return self


class GeneratedQuestionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[GeneratedQuestion]


def validate_generated_questions(
    batch: GeneratedQuestionBatch,
    *,
    task_type: WritingTaskType,
    count: int,
    existing_scenarios: tuple[str, ...],
) -> None:
    if len(batch.questions) != count:
        raise RuntimeError("Question generation returned an unexpected number of drafts")
    existing_keys = {item.casefold() for item in existing_scenarios}
    generated_keys: set[str] = set()
    generated_prompts: set[str] = set()
    for question in batch.questions:
        key = question.scenario_key.casefold()
        normalized_prompt = " ".join(question.prompt.split()).casefold()
        if key in existing_keys or key in generated_keys:
            raise RuntimeError("Question generation returned a repeated scenario")
        if normalized_prompt in generated_prompts:
            raise RuntimeError("Question generation returned a duplicate prompt")
        if issues := task_style_issues(task_type, question.prompt):
            raise RuntimeError(
                "Question generation returned an invalid CELPIP-style prompt: "
                + "; ".join(issues)
            )
        generated_keys.add(key)
        generated_prompts.add(normalized_prompt)


@dataclass(frozen=True)
class QuestionGenerationOutput:
    questions: tuple[GeneratedQuestion, ...]
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal


class QuestionGenerator(Protocol):
    async def generate(
        self,
        *,
        task_type: WritingTaskType,
        count: int,
        category: str | None,
        existing_scenarios: tuple[str, ...],
    ) -> QuestionGenerationOutput: ...


def _output_text(payload: dict[str, Any]) -> str | None:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    return None


class OpenAIQuestionGenerator:
    async def generate(
        self,
        *,
        task_type: WritingTaskType,
        count: int,
        category: str | None,
        existing_scenarios: tuple[str, ...],
    ) -> QuestionGenerationOutput:
        secret = settings.openai_api_key
        if secret is None or not secret.get_secret_value().strip():
            raise RuntimeError("OpenAI is not configured")
        developer = question_generation_instructions(task_type)
        user = json.dumps(
            {
                "prompt_version": QUESTION_GENERATOR_PROMPT_VERSION,
                "task_type": task_type.value,
                "count": count,
                "preferred_category": category,
                "existing_scenario_keys": existing_scenarios[-200:],
            },
            separators=(",", ":"),
        )
        client = AsyncOpenAI(
            api_key=secret.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
        try:
            raw = await client.responses.with_raw_response.create(
                model=settings.openai_model,
                input=[
                    {"role": "developer", "content": developer},
                    {"role": "user", "content": user},
                ],
                reasoning={"effort": settings.openai_reasoning_effort},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "celpip_question_drafts",
                        "schema": GeneratedQuestionBatch.model_json_schema(),
                        "strict": True,
                    }
                },
                max_output_tokens=max(settings.max_response_tokens, count * 1200),
                store=False,
            )
            payload = raw.http_response.json()
            if payload.get("status") != "completed":
                reason = (payload.get("incomplete_details") or {}).get("reason") or "unknown"
                raise RuntimeError(f"Question generation incomplete: {reason}")
            text = _output_text(payload)
            if text is None:
                raise RuntimeError("Question generation returned no content")
            batch = GeneratedQuestionBatch.model_validate_json(text)
            validate_generated_questions(
                batch,
                task_type=task_type,
                count=count,
                existing_scenarios=existing_scenarios,
            )
            usage = payload.get("usage") or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            input_cost = Decimal(input_tokens) * settings.openai_input_cost_per_million
            output_cost = Decimal(output_tokens) * settings.openai_output_cost_per_million
            estimated_cost = ((input_cost + output_cost) / ONE_MILLION).quantize(
                Decimal("0.000001")
            )
            return QuestionGenerationOutput(
                questions=tuple(batch.questions),
                model=str(payload.get("model") or settings.openai_model),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
            )
        finally:
            await client.close()


def get_question_generator() -> QuestionGenerator | None:
    secret = settings.openai_api_key
    if secret is None or not secret.get_secret_value().strip():
        return None
    return OpenAIQuestionGenerator()


QuestionGeneratorDependency = Annotated[
    QuestionGenerator | None, Depends(get_question_generator)
]
