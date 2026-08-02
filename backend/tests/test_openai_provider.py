import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.ai_provider import EvaluationInput
from app.ai.openai_provider import (
    IncompleteEvaluationResponseError,
    OpenAIWritingProvider,
)
from app.ai.openai_schema import StructuredWritingEvaluation, WritingCorrection
from app.ai.token_budget import TokenBudgetExceededError, build_optimized_prompt


class FakeResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.parameters: dict[str, Any] | None = None

    async def parse(self, **kwargs: Any) -> object:
        self.parameters = kwargs
        return self.response


class FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.responses = FakeResponses(response)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.headers = {"x-request-id": "req_recovered"}

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeRawResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.http_response = FakeHTTPResponse(payload)

    def parse(self) -> object:
        raise ValueError("Simulated SDK response-model incompatibility")


class FakeRawResponses:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.parameters: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> FakeRawResponse:
        self.parameters = kwargs
        return FakeRawResponse(self.payload)


class FakeRawResponsesResource:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.with_raw_response = FakeRawResponses(payload)


class FakeRawOpenAIClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.responses = FakeRawResponsesResource(payload)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _provider(client: FakeOpenAIClient) -> OpenAIWritingProvider:
    return OpenAIWritingProvider(
        api_key="test-key",
        model="gpt-5-mini",
        reasoning_effort="low",
        max_input_tokens=6000,
        max_history_items=2,
        max_output_tokens=900,
        timeout_seconds=15,
        max_retries=1,
        input_cost_per_million=Decimal("0.25"),
        cached_input_cost_per_million=Decimal("0.025"),
        output_cost_per_million=Decimal("2.00"),
        client=client,
    )


@pytest.mark.asyncio
async def test_openai_provider_uses_structured_response_and_tracks_cached_cost() -> None:
    parsed = StructuredWritingEvaluation(
        score=8,
        task_fulfillment=8,
        organization=7,
        vocabulary=8,
        grammar=7,
        strengths=["Clear purpose"],
        weaknesses=["Article usage"],
        corrections=[
            WritingCorrection(
                original="I request flexible schedule",
                revised="I am requesting a flexible schedule",
                explanation="Adds the article and a natural verb form.",
            )
        ],
        recommended_next_steps=["Review article use"],
    )
    response = SimpleNamespace(
        id="resp_123",
        model="gpt-5-mini-2025-08-07",
        output_parsed=parsed,
        usage=SimpleNamespace(
            input_tokens=1200,
            output_tokens=300,
            input_tokens_details=SimpleNamespace(cached_tokens=200),
        ),
        _request_id="req_123",
    )
    client = FakeOpenAIClient(response)
    provider = _provider(client)

    output = await provider.evaluate_writing(
        EvaluationInput(
            task_prompt="Write an email requesting a flexible schedule.",
            answer_text="I request flexible schedule because commuting is difficult.",
            current_score=7,
            target_score=10,
            weaknesses=("Article usage", "Sentence variety", "Unused third item"),
            safety_identifier="hashed-user-id",
        )
    )

    assert output.score == 8
    assert output.corrections[0]["revised"].startswith("I am requesting")
    assert output.input_tokens == 1200
    assert output.output_tokens == 300
    assert output.estimated_cost == Decimal("0.000855")
    assert output.raw_response["request_id"] == "req_123"
    assert "commuting is difficult" not in repr(output.raw_response)

    assert client.responses.parameters is not None
    parameters = client.responses.parameters
    assert parameters["model"] == "gpt-5-mini"
    assert parameters["text_format"] is StructuredWritingEvaluation
    assert parameters["max_output_tokens"] == 900
    assert parameters["reasoning"] == {"effort": "low"}
    assert parameters["store"] is False
    assert parameters["safety_identifier"] == "hashed-user-id"
    assert parameters["input"][0]["role"] == "developer"
    assert parameters["input"][1]["role"] == "user"
    assert "Unused third item" not in parameters["input"][1]["content"]


@pytest.mark.asyncio
async def test_provider_recovers_valid_output_when_sdk_response_validation_fails() -> None:
    evaluation = {
        "score": 8,
        "task_fulfillment": 8,
        "organization": 7,
        "vocabulary": 8,
        "grammar": 7,
        "strengths": ["Clear purpose"],
        "weaknesses": ["Article usage"],
        "corrections": [
            {
                "original": "I request flexible schedule",
                "revised": "I am requesting a flexible schedule",
                "explanation": "Adds the article and a natural verb form.",
            }
        ],
        "recommended_next_steps": ["Review article use"],
    }
    payload = {
        "id": "resp_recovered",
        "model": "gpt-5-mini-2025-08-07",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(evaluation)}],
            }
        ],
        "usage": {
            "input_tokens": 600,
            "output_tokens": 200,
            "input_tokens_details": {"cached_tokens": 100},
        },
    }
    client = FakeRawOpenAIClient(payload)
    provider = _provider(client)  # type: ignore[arg-type]

    output = await provider.evaluate_writing(
        EvaluationInput(
            task_prompt="Write an email requesting a flexible schedule.",
            answer_text="I request flexible schedule because commuting is difficult.",
            current_score=7,
            target_score=10,
            weaknesses=(),
            safety_identifier="hashed-user-id",
        )
    )

    assert output.score == 8
    assert output.model == "gpt-5-mini-2025-08-07"
    assert output.input_tokens == 600
    assert output.output_tokens == 200
    assert output.raw_response["response_id"] == "resp_recovered"
    assert output.raw_response["request_id"] == "req_recovered"
    parameters = client.responses.with_raw_response.parameters
    assert parameters is not None
    assert "text_format" not in parameters
    assert parameters["text"]["format"]["type"] == "json_schema"
    assert parameters["text"]["format"]["strict"] is True
    assert parameters["reasoning"] == {"effort": "low"}


@pytest.mark.asyncio
async def test_provider_reports_output_token_exhaustion_before_parsing() -> None:
    client = FakeRawOpenAIClient(
        {
            "id": "resp_incomplete",
            "model": "gpt-5-mini-2025-08-07",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [],
            "usage": {
                "input_tokens": 600,
                "output_tokens": 900,
                "input_tokens_details": {"cached_tokens": 0},
            },
        }
    )
    provider = _provider(client)  # type: ignore[arg-type]

    with pytest.raises(IncompleteEvaluationResponseError, match="max_output_tokens"):
        await provider.evaluate_writing(
            EvaluationInput(
                task_prompt="Write an email.",
                answer_text="A complete student response.",
                current_score=None,
                target_score=9,
                weaknesses=(),
                safety_identifier="hashed-user-id",
            )
        )


def test_prompt_optimizer_deduplicates_and_caps_history() -> None:
    prompt = build_optimized_prompt(
        task_prompt="Write an email.",
        answer_text="This is my response.",
        current_score=6,
        target_score=9,
        weaknesses=("Grammar", " grammar ", "Vocabulary", "Organization"),
        model="gpt-5-mini",
        max_input_tokens=4000,
        max_history_items=2,
    )

    payload = json.loads(prompt.user_message.removeprefix("Evaluate this JSON payload:\n"))
    assert payload["student_context"]["recent_weaknesses"] == ["Grammar", "Vocabulary"]
    assert prompt.included_history_items == 2
    assert prompt.estimated_input_tokens <= 4000


def test_prompt_optimizer_omits_all_history_when_limit_is_zero() -> None:
    prompt = build_optimized_prompt(
        task_prompt="Write an email.",
        answer_text="This is my response.",
        current_score=6,
        target_score=9,
        weaknesses=("Grammar", "Vocabulary"),
        model="gpt-5-mini",
        max_input_tokens=4000,
        max_history_items=0,
    )

    payload = json.loads(prompt.user_message.removeprefix("Evaluate this JSON payload:\n"))
    assert payload["student_context"]["recent_weaknesses"] == []
    assert prompt.included_history_items == 0


def test_prompt_optimizer_rejects_required_content_over_budget() -> None:
    with pytest.raises(TokenBudgetExceededError):
        build_optimized_prompt(
            task_prompt="Write an email.",
            answer_text="word " * 5000,
            current_score=None,
            target_score=9,
            weaknesses=(),
            model="gpt-5-mini",
            max_input_tokens=700,
            max_history_items=0,
        )


@pytest.mark.asyncio
async def test_provider_closes_injected_async_client() -> None:
    client = FakeOpenAIClient(response=object())
    provider = _provider(client)

    await provider.close()

    assert client.closed is True
