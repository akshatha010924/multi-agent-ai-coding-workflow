"""Factory: single place where the concrete LLM strategy is chosen."""
from app.config import Settings
from app.core.exceptions import ConfigurationError
from app.llm.base import LLMClient


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "mock":
        from app.llm.mock_client import MockLLMClient

        return MockLLMClient()
    if not settings.anthropic_api_key or not settings.anthropic_api_key.get_secret_value():
        raise ConfigurationError("ANTHROPIC_API_KEY is not set (or use LLM_PROVIDER=mock for offline demos)")
    from app.llm.anthropic_client import AnthropicLLMClient

    return AnthropicLLMClient(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
