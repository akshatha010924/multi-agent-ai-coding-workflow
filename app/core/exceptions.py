"""Application exception hierarchy. `message` is always safe to show to API clients."""


class AppError(Exception):
    code = "app_error"
    status_code = 500

    def __init__(self, message: str = "Internal error"):
        super().__init__(message)
        self.message = message


class ConfigurationError(AppError):
    code = "configuration_error"


class GuardrailViolationError(AppError):
    code = "guardrail_violation"
    status_code = 422


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class LLMError(AppError):
    code = "llm_error"
    status_code = 502


class LLMAuthError(LLMError):
    code = "llm_auth_error"


class LLMRateLimitError(LLMError):
    code = "llm_rate_limited"
    status_code = 429


class LLMTimeoutError(LLMError):
    code = "llm_timeout"
    status_code = 504


class LLMOutputError(LLMError):
    code = "llm_invalid_output"


class ToolError(AppError):
    """MCP / external tool failure."""

    code = "tool_error"
    status_code = 502


class WorkflowError(AppError):
    code = "workflow_error"
