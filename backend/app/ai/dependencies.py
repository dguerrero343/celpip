from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.ai.ai_provider import AIProvider
from app.ai.openai_provider import OpenAIWritingProvider
from app.core.config import settings


@lru_cache
def _configured_provider() -> OpenAIWritingProvider | None:
    secret = settings.openai_api_key
    api_key = secret.get_secret_value().strip() if secret is not None else ""
    if not api_key:
        return None
    return OpenAIWritingProvider(
        api_key=api_key,
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
        max_input_tokens=settings.max_ai_context_tokens,
        max_history_items=settings.max_history_items,
        max_output_tokens=settings.max_response_tokens,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
        input_cost_per_million=settings.openai_input_cost_per_million,
        cached_input_cost_per_million=settings.openai_cached_input_cost_per_million,
        output_cost_per_million=settings.openai_output_cost_per_million,
    )


def get_ai_provider() -> AIProvider | None:
    """Return one process-wide async OpenAI client when a server-side key exists."""
    return _configured_provider()


async def close_ai_provider() -> None:
    provider = _configured_provider()
    if provider is not None:
        await provider.close()
    _configured_provider.cache_clear()


EvaluationProvider = Annotated[AIProvider | None, Depends(get_ai_provider)]
