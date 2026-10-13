"""Produces tool-derived FACTS about a proposal: guardrails -> syntax -> sandboxed tests -> lint."""
import ast
import logging
from pathlib import PurePosixPath

from app.domain.models import ImplementationResult, ValidationReport
from app.guardrails.base import GuardrailChain
from app.repositories.workspace_repository import WorkspaceReader
from app.services.sandbox import CodeRunner

logger = logging.getLogger(__name__)


def is_test_file(path: str) -> bool:
    p = PurePosixPath(path)
    return p.suffix == ".py" and (p.name.startswith("test_") or p.name.endswith("_test.py") or "tests" in p.parts)


class VerificationService:
    def __init__(self, guardrails: GuardrailChain[ImplementationResult], runner: CodeRunner, workspace: WorkspaceReader):
        self._guardrails = guardrails
        self._runner = runner
        self._workspace = workspace

    def verify(self, impl: ImplementationResult) -> ValidationReport:
        report = ValidationReport()
        report.guardrail_violations = [str(v) for v in self._guardrails.evaluate(impl) if v.severity == "block"]

        for f in impl.files:
            if f.path.endswith(".py"):
                try:
                    ast.parse(f.content)
                except SyntaxError as e:
                    report.syntax_errors.append(f"{f.path}:{e.lineno}: {e.msg}")

        if report.guardrail_violations:
            report.skipped_reason = "Execution skipped: guardrail violations (unsafe code is never executed)"
            return report
        if report.syntax_errors:
            report.skipped_reason = "Execution skipped: syntax errors"
            return report
        if not any(is_test_file(f.path) for f in impl.files):
            report.skipped_reason = "Execution skipped: proposal contains no test files"
            return report

        files = {**self._workspace.snapshot(max_files=100, max_chars=200_000), **{f.path: f.content for f in impl.files}}
        result = self._runner.execute(files)

        t = result.tests
        report.tests_run = not (t.timed_out or t.unavailable)
        report.tests_passed = t.exit_code == 0
        report.test_output = t.output
        if t.exit_code == 5:
            report.tests_run, report.tests_passed = False, False
            report.skipped_reason = "pytest collected no tests"
        if result.lint and not result.lint.unavailable:
            report.lint_passed = result.lint.exit_code == 0
            report.lint_output = result.lint.output
        logger.info("verification: tests_passed=%s lint_passed=%s", report.tests_passed, report.lint_passed)
        return report
