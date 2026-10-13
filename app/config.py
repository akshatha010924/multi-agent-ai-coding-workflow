"""Centralised, validated configuration. Every tunable lives here (no scattered os.getenv)."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/workflows.db"

    # LLM
    llm_provider: Literal["anthropic", "mock"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = Field(4096, ge=256, le=32000)
    llm_timeout_seconds: float = Field(120, gt=0)
    llm_max_retries: int = Field(2, ge=0, le=5)

    # Workflow
    max_review_iterations: int = Field(3, ge=1, le=5)
    workspace_dir: Path = Path("./workspace")
    apply_changes_enabled: bool = False
    sandbox_timeout_seconds: int = Field(30, ge=1, le=300)
    sandbox_memory_mb: int = Field(1024, ge=128, le=8192)

    # MCP
    mcp_enabled: bool = False
    mcp_server_command: str = "npx -y @upstash/context7-mcp"
    mcp_timeout_seconds: float = Field(30, gt=0)
    mcp_resolve_tool: str = "resolve-library-id"
    mcp_docs_tool: str = "query-docs"
    context7_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
