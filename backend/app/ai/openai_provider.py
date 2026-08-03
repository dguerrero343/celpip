import logging
from decimal import Decimal
from typing import Any, Protocol

from openai import AsyncOpenAI
from pydantic import ValidationError as PydanticValidationError

from app.ai.ai_provider import EvaluationInput, EvaluationOutput
from app.ai.openai_schema import StructuredWritingEvaluation
from app.ai.token_budget import EVALUATOR_PROMPT_VERSION, build_optimized_prompt

logger = logging.getLogger(__name__)
ONE_MILLION = Decimal("1000000")
COST_QUANTUM = Decimal("0.000001")


class _ResponsesAPI(Protocol):
    async def parse(self, **kwargs: Any) -> Any: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesAPI

    async def close(self) -> None: ...


class EmptyEvaluationResponseError(RuntimeError):
    """Raised when OpenAI returns no parsed structured evaluation."""


class IncompleteEvaluationResponseError(RuntimeError):
    """Raised when OpenAI stops before completing the structured evaluation."""


class RefusedEvaluationResponseError(RuntimeError):
    """Raised when OpenAI refuses to evaluate the submitted content."""


def _output_text(payload: dict[str, Any]) -> str | None:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    return None


def _refusal_reason(payload: dict[str, Any]) -> str | None:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                return "content_refusal"
    return None


def _usage_from_payload(payload: dict[str, Any]) -> tuple[int, int, int]:
    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    input_details = usage.get("input_tokens_details") or {}
    cached_tokens = int(input_details.get("cached_tokens") or 0)
    return input_tokens, output_tokens, cached_tokens


class OpenAIWritingProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str = "low",
        max_input_tokens: int,
        max_history_items: int,
        max_output_tokens: int,
        timeout_seconds: float,
        max_retries: int,
        input_cost_per_million: Decimal,
        cached_input_cost_per_million: Decimal,
        output_cost_per_million: Decimal,
        client: _OpenAIClient | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_input_tokens = max_input_tokens
        self.max_history_items = max_history_items
        self.max_output_tokens = max_output_tokens
        self.input_cost_per_million = input_cost_per_million
        self.cached_input_cost_per_million = cached_input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self._client: _OpenAIClient = client or AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    async def close(self) -> None:
        await self._client.close()

    def _estimated_cost(self, input_tokens: int, output_tokens: int, cached_tokens: int) -> Decimal:
        cached_tokens = min(max(cached_tokens, 0), input_tokens)
        uncached_tokens = input_tokens - cached_tokens
        cost = (
            Decimal(uncached_tokens) * self.input_cost_per_million
            + Decimal(cached_tokens) * self.cached_input_cost_per_million
            + Decimal(output_tokens) * self.output_cost_per_million
        ) / ONE_MILLION
        return cost.quantize(COST_QUANTUM)

    async def evaluate_writing(self, request: EvaluationInput) -> EvaluationOutput:
        prompt = build_optimized_prompt(
            task_prompt=request.task_prompt,
            answer_text=request.answer_text,
            current_score=request.current_score,
            target_score=request.target_score,
            weaknesses=request.weaknesses,
            model=self.model,
            max_input_tokens=self.max_input_tokens,
            max_history_items=self.max_history_items,
            previous_objective=request.previous_objective,
        )
        parameters: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "developer", "content": prompt.developer_message},
                {"role": "user", "content": prompt.user_message},
            ],
            "text_format": StructuredWritingEvaluation,
            "max_output_tokens": self.max_output_tokens,
            "reasoning": {"effort": self.reasoning_effort},
            "store": False,
        }
        if request.safety_identifier:
            parameters["safety_identifier"] = request.safety_identifier

        try:
            raw_api = getattr(self._client.responses, "with_raw_response", None)
            if raw_api is None:
                response = await self._client.responses.parse(**parameters)
                parsed: StructuredWritingEvaluation | None = response.output_parsed
                usage = getattr(response, "usage", None)
                input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
                input_details = getattr(usage, "input_tokens_details", None)
                cached_tokens = int(getattr(input_details, "cached_tokens", 0) or 0)
                response_model = str(getattr(response, "model", None) or self.model)
                response_id = getattr(response, "id", None)
                request_id = getattr(response, "_request_id", None)
            else:
                raw_parameters = dict(parameters)
                raw_parameters.pop("text_format", None)
                raw_parameters["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "celpip_writing_evaluation",
                        "schema": StructuredWritingEvaluation.model_json_schema(),
                        "strict": True,
                    }
                }
                raw_response = await raw_api.create(**raw_parameters)
                payload = raw_response.http_response.json()
                status = str(payload.get("status") or "unknown")
                incomplete_details = payload.get("incomplete_details") or {}
                incomplete_reason = str(incomplete_details.get("reason") or "unknown")
                refusal_reason = _refusal_reason(payload)
                if refusal_reason is not None:
                    raise RefusedEvaluationResponseError(refusal_reason)
                if status == "incomplete":
                    raise IncompleteEvaluationResponseError(incomplete_reason)
                try:
                    text = _output_text(payload)
                    if text is None:
                        raise EmptyEvaluationResponseError(
                            "OpenAI returned no structured evaluation"
                        )
                    parsed = StructuredWritingEvaluation.model_validate_json(text)
                except PydanticValidationError as validation_error:
                    issues = ",".join(
                        f"{'.'.join(str(part) for part in issue['loc'])}:{issue['type']}"
                        for issue in validation_error.errors(include_input=False, include_url=False)
                    )
                    logger.warning("OpenAI evaluation schema mismatch issues=%s", issues)
                    raise
                input_tokens, output_tokens, cached_tokens = _usage_from_payload(payload)
                response_model = str(payload.get("model") or self.model)
                response_id = payload.get("id")
                request_id = raw_response.http_response.headers.get("x-request-id")
        except Exception as exc:
            logger.warning(
                "OpenAI writing evaluation failed error_type=%s request_id=%s",
                type(exc).__name__,
                getattr(exc, "request_id", None),
            )
            raise

        if parsed is None:
            raise EmptyEvaluationResponseError("OpenAI returned no structured evaluation")

        structured_result = parsed.model_dump(mode="json")
        raw_response: dict[str, object] = {
            "provider": "openai",
            "response_id": response_id,
            "request_id": request_id,
            "model": response_model,
            "usage": {
                "input_tokens": input_tokens,
                "cached_input_tokens": min(cached_tokens, input_tokens),
                "output_tokens": output_tokens,
            },
            "optimization": {
                "preflight_input_tokens": prompt.estimated_input_tokens,
                "included_history_items": prompt.included_history_items,
            },
            "evaluation": structured_result,
        }
        return EvaluationOutput(
            model=response_model,
            score=parsed.score,
            task_fulfillment=parsed.task_fulfillment,
            organization=parsed.organization,
            vocabulary=parsed.vocabulary,
            grammar=parsed.grammar,
            strengths=tuple(parsed.strengths),
            weaknesses=tuple(parsed.weaknesses),
            corrections=tuple(correction.model_dump() for correction in parsed.corrections),
            recommended_next_steps=tuple(parsed.recommended_next_steps),
            raw_response=raw_response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=self._estimated_cost(input_tokens, output_tokens, cached_tokens),
            weakness_signals=tuple(
                item.model_dump(mode="json") for item in parsed.weakness_signals
            ),
            next_objective=parsed.next_objective.model_dump(mode="json"),
            previous_objective_assessment=parsed.previous_objective_assessment.model_dump(
                mode="json"
            ),
            evaluator_prompt_version=EVALUATOR_PROMPT_VERSION,
        )
