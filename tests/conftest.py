from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.container import build_container
from app.domain.models import (
    FileChange,
    ImplementationResult,
    LookupPlan,
    ResearchDraft,
    ReviewResult,
    ReviewStatus,
)
from app.llm import _mock_fixtures as fx
from app.llm.base import LLMClient
from app.services.sandbox import CodeRunner, CommandResult, SandboxReport
from app.tools.docs_provider import NullDocsProvider


class ScriptedLLM(LLMClient):
    """TEST DOUBLE. Per-schema script: a value, a list (consumed in order, last repeats), or a callable(user)."""

    def __init__(self, **script: Any):
        self.script = {
            LookupPlan: LookupPlan(),
            ResearchDraft: ResearchDraft(task_summary="summary", recommended_approach="approach", findings=["f"]),
            ReviewResult: ReviewResult(status=ReviewStatus.APPROVED, summary="ok"),
        }
        for k, v in script.items():
            self.script[{"impl": ImplementationResult, "review": ReviewResult, "research": ResearchDraft, "plan": LookupPlan}[k]] = v
        self.calls: list[tuple[str, str]] = []

    def generate_structured(self, *, system: str, user: str, schema: type[BaseModel], agent: str = "") -> Any:
        self.calls.append((schema.__name__, user))
        item = self.script[schema]
        if isinstance(item, list):
            item = item.pop(0) if len(item) > 1 else item[0]
        if callable(item):
            item = item(user)
        if isinstance(item, Exception):
            raise item
        return item


class FakeRunner(CodeRunner):
    """TEST DOUBLE for the sandbox: scripted pass/fail, counts executions."""

    def __init__(self, exit_code: int = 0, output: str = "1 passed"):
        self.exit_code, self.output, self.calls = exit_code, output, 0

    def execute(self, files) -> SandboxReport:
        self.calls += 1
        return SandboxReport(CommandResult(self.exit_code, self.output), CommandResult(0, "ok"))


def impl(good: bool = True, extra: list[FileChange] | None = None) -> ImplementationResult:
    return ImplementationResult(
        summary="email validator",
        files=[
            FileChange(path="email_validator_util.py", content=fx.FIXED_IMPL if good else fx.FLAWED_IMPL),
            FileChange(path="test_email_validator_util.py", content=fx.TESTS),
            *(extra or []),
        ],
    )


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(_env_file=None, database_url="sqlite://", llm_provider="mock", workspace_dir=tmp_path / "ws",
                    max_review_iterations=kw.pop("max_review_iterations", 3), **kw)


@pytest.fixture
def container_factory(tmp_path) -> Callable:
    def make(llm: LLMClient, runner: CodeRunner | None = None, docs=None, **settings_kw):
        return build_container(make_settings(tmp_path, **settings_kw), llm=llm, docs=docs or NullDocsProvider(), runner=runner)
    return make


TASK = "Implement a small Python utility that validates an email address and add tests."
