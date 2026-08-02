import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Protocol

from fastapi import Depends
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.models.enums import WritingTaskType

ONE_MILLION = Decimal("1000000")


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    scenario_key: str
    prompt: str
    focus_tags: list[str]
    target_score_min: int = Field(ge=1, le=12)
    target_score_max: int = Field(ge=1, le=12)


class GeneratedQuestionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[GeneratedQuestion]


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
        task_rules = (
            "Task 1: an everyday email to a defined recipient, about three explicit points to "
            "address, balanced professional tone, and a 150–200 word instruction."
            if task_type == WritingTaskType.EMAIL
            else "Task 2: an opinion survey with exactly two realistic options, a clear request "
            "to choose one and explain why it is better, and a 150–200 word instruction."
        )
        developer = (
            "Create original practice exercises that follow the public CELPIP Writing format. "
            "Do not copy, quote, paraphrase, or claim to reproduce official test questions. "
            "Use Canadian everyday, workplace, community, education, or public-service contexts. "
            "Every scenario must be distinct from the supplied existing scenario keys. "
            f"{task_rules} Return exactly the requested number of questions."
        )
        user = json.dumps(
            {
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
            if len(batch.questions) != count:
                raise RuntimeError("Question generation returned an unexpected number of drafts")
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
