import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Protocol

from fastapi import Depends
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai.question_generator import ONE_MILLION, _output_text
from app.core.config import settings
from app.models.enums import WritingTaskType

HELP_CONTENT_VERSION = "2026-08-02.v1"
HTML_PATTERN = re.compile(r"<[^>]+>")


class PlainTextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def reject_html(cls, value: object) -> object:
        if isinstance(value, str) and HTML_PATTERN.search(value):
            raise ValueError("HTML is not allowed")
        return value


class StructureItem(PlainTextModel):
    section: str = Field(min_length=1, max_length=80)
    guidance: str = Field(min_length=1, max_length=240)


class SentenceFramework(PlainTextModel):
    purpose: str = Field(min_length=1, max_length=80)
    framework: str = Field(min_length=1, max_length=200)


class VocabularyItem(PlainTextModel):
    phrase: str = Field(min_length=1, max_length=100)
    meaning: str = Field(min_length=1, max_length=180)
    example: str = Field(min_length=1, max_length=240)
    usage_note: str = Field(min_length=1, max_length=180)


class VocabularyGroup(PlainTextModel):
    category: str = Field(min_length=1, max_length=80)
    items: list[VocabularyItem] = Field(min_length=1, max_length=8)


class ChecklistItem(PlainTextModel):
    label: str = Field(min_length=1, max_length=220)


class WritingHelpContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommended_structure: list[StructureItem] = Field(min_length=4, max_length=10)
    sentence_frameworks: list[SentenceFramework] = Field(min_length=6, max_length=10)
    vocabulary_groups: list[VocabularyGroup] = Field(min_length=2, max_length=8)
    task_completion_checklist: list[ChecklistItem] = Field(min_length=1, max_length=12)
    level_12_quality_checklist: list[ChecklistItem] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_vocabulary_total(self) -> "WritingHelpContent":
        total = sum(len(group.items) for group in self.vocabulary_groups)
        if not 12 <= total <= 18:
            raise ValueError("vocabulary must contain 12 to 18 items")
        return self


@dataclass(frozen=True)
class HelpGenerationOutput:
    content: WritingHelpContent
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal


class HelpGenerator(Protocol):
    async def generate(
        self,
        *,
        task_type: WritingTaskType,
        instructions: str,
        topic: str,
        target_score: int,
        weaknesses: tuple[str, ...],
    ) -> HelpGenerationOutput: ...


class OpenAIHelpGenerator:
    async def generate(
        self,
        *,
        task_type: WritingTaskType,
        instructions: str,
        topic: str,
        target_score: int,
        weaknesses: tuple[str, ...],
    ) -> HelpGenerationOutput:
        secret = settings.openai_api_key
        if secret is None or not secret.get_secret_value().strip():
            raise RuntimeError("OpenAI is not configured")
        developer = (
            "Create concise guided-practice support for one CELPIP-style writing exercise. "
            "Never write a complete answer, paragraph, or copy-ready response. "
            "Frameworks must use blanks such as ______. Infer the intended reader, purpose, "
            "and tone from the instructions. Make every section specific to the supplied task. "
            "Represent every explicit task requirement separately in the task checklist. "
            "Use natural Canadian English. Return exactly 6-10 frameworks, 12-18 vocabulary "
            "items total, and exactly 10 quality checklist items covering task completion, idea "
            "development, organization, transitions, vocabulary, sentence variety, tone, "
            "accuracy, word range, and conclusion."
        )
        payload = json.dumps(
            {
                "task_type": task_type.value,
                "instructions": instructions,
                "topic": topic,
                "target_score": target_score,
                "main_weaknesses": list(weaknesses[:3]),
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
                    {"role": "user", "content": payload},
                ],
                reasoning={"effort": settings.openai_reasoning_effort},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "celpip_writing_help",
                        "schema": WritingHelpContent.model_json_schema(),
                        "strict": True,
                    }
                },
                max_output_tokens=max(settings.max_response_tokens, 2800),
                store=False,
            )
            response = raw.http_response.json()
            if response.get("status") != "completed":
                raise RuntimeError("Help generation was incomplete")
            output_text = _output_text(response)
            if output_text is None:
                raise RuntimeError("Help generation returned no content")
            content = WritingHelpContent.model_validate_json(output_text)
            usage = response.get("usage") or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            cost = (
                (
                    Decimal(input_tokens) * settings.openai_input_cost_per_million
                    + Decimal(output_tokens) * settings.openai_output_cost_per_million
                )
                / ONE_MILLION
            ).quantize(Decimal("0.000001"))
            return HelpGenerationOutput(
                content,
                str(response.get("model") or settings.openai_model),
                input_tokens,
                output_tokens,
                cost,
            )
        finally:
            await client.close()


def get_help_generator() -> HelpGenerator | None:
    secret = settings.openai_api_key
    return (
        OpenAIHelpGenerator() if secret is not None and secret.get_secret_value().strip() else None
    )


HelpGeneratorDependency = Annotated[HelpGenerator | None, Depends(get_help_generator)]


def demo_help_content(
    task_type: WritingTaskType, topic: str, instructions: str
) -> WritingHelpContent:
    email = task_type == WritingTaskType.EMAIL
    structure = (
        [
            (
                "Subject and greeting",
                "Name the purpose and address the intended reader appropriately.",
            ),
            ("Opening", f"State why you are writing about {topic.lower()}."),
            ("Required details", "Use one focused paragraph for each instruction in the task."),
            ("Follow-up", "Make the requested action or next step explicit."),
            ("Closing", "End politely with an appropriate sign-off."),
        ]
        if email
        else [
            ("Position", "Choose one option and state your position clearly."),
            ("First reason", f"Explain one practical reason connected to {topic.lower()}."),
            ("Example", "Support the reason with a specific but concise example."),
            ("Second reason", "Develop a distinct second reason and consequence."),
            ("Conclusion", "Restate the recommendation and its main benefit."),
        ]
    )
    framework_values = (
        [
            ("State purpose", "I am writing to ______ regarding ______."),
            ("Explain context", "The main reason for this request is ______."),
            ("Add a detail", "In particular, ______ would allow us to ______."),
            ("Polite request", "Could you please confirm whether ______?"),
            ("Offer help", "I would be willing to assist by ______."),
            ("Follow up", "I would appreciate your response by ______."),
        ]
        if email
        else [
            ("State position", "I strongly support ______ because ______."),
            ("First reason", "The first major advantage is ______."),
            ("Explain impact", "This would benefit ______ by ______."),
            ("Give example", "For example, ______ could ______."),
            ("Contrast", "Although ______, the stronger option is ______."),
            ("Conclude", "For these reasons, I recommend ______."),
        ]
    )
    phrases = [
        "regarding",
        "a practical solution",
        "would enable",
        "a key benefit",
        "a potential concern",
        "in addition",
        "as a result",
        "for instance",
        "on balance",
        "I would appreciate",
        "please confirm whether",
        "a suitable alternative",
    ]
    groups = []
    for category, subset in (
        ("Purpose and requests", phrases[:6]),
        ("Reasons and conclusions", phrases[6:]),
    ):
        groups.append(
            VocabularyGroup(
                category=category,
                items=[
                    VocabularyItem(
                        phrase=p,
                        meaning=f"A useful phrase for {category.lower()}.",
                        example=f"Use “{p}” naturally when discussing {topic.lower()}.",
                        usage_note="Adapt the phrase to your sentence and intended tone.",
                    )
                    for p in subset
                ],
            )
        )
    requirements = [
        part.strip(" .")
        for part in re.split(r"(?:\d+[.)]|[;•])", instructions)
        if len(part.strip()) > 8
    ][:8]
    if not requirements:
        requirements = ["Address every required point in the exercise instructions"]
    quality = [
        "Address all task requirements",
        "Develop each main idea sufficiently",
        "Organize paragraphs logically",
        "Connect ideas with natural transitions",
        "Use varied and accurate vocabulary",
        "Vary sentence structures",
        "Match the reader, purpose, and tone",
        "Keep grammar and punctuation errors minimal",
        "Stay within the recommended word range",
        "End with a clear action, request, or position",
    ]
    return WritingHelpContent(
        recommended_structure=[StructureItem(section=a, guidance=b) for a, b in structure],
        sentence_frameworks=[
            SentenceFramework(purpose=a, framework=b) for a, b in framework_values
        ],
        vocabulary_groups=groups,
        task_completion_checklist=[ChecklistItem(label=x) for x in requirements],
        level_12_quality_checklist=[ChecklistItem(label=x) for x in quality],
    )
