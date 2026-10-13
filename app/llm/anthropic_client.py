"""Anthropic implementation. Structured output = forced tool call whose input_schema is the Pydantic schema."""
import logging
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.core.exceptions import (
    LLMAuthError,
    LLMError,
    LLMOutputError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.base import LLMClient

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)
_TOOL = "submit_result"


class AnthropicLLMClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout: float,
        max_retries: int,
        client: Any | None = None,
    ):
        self._model = model
        self._max_tokens = max_tokens
        # SDK-level bounded retries (429/5xx/connection) with backoff.
        self._client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)

    def generate_structured(self, *, system: str, user: str, schema: type[T], agent: str = "") -> T:
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[{
                    "name": _TOOL,
                    "description": "Submit your final structured answer.",
                    "input_schema": schema.model_json_schema(),
                }],
                tool_choice={"type": "tool", "name": _TOOL},
            )
        except anthropic.AuthenticationError as e:
            raise LLMAuthError("LLM authentication failed; check ANTHROPIC_API_KEY") from e
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError("LLM rate limit exceeded; retry later") from e
        except anthropic.APITimeoutError as e:  # must precede APIConnectionError (its parent)
            raise LLMTimeoutError("LLM request timed out") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the LLM provider") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"LLM provider returned HTTP {e.status_code}") from e

        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise LLMOutputError("LLM output was truncated (max_tokens); simplify the task or raise LLM_MAX_TOKENS")
        block = next((b for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
        if block is None:
            raise LLMOutputError(f"{agent or 'agent'}: model returned no structured output")
        try:
            return schema.model_validate(block.input)
        except ValidationError as e:
            logger.warning("%s produced invalid structured output: %s", agent, e.error_count())
            raise LLMOutputError(f"{agent or 'agent'}: model output failed schema validation") from e
