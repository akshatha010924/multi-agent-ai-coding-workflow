from typing import Any

from pydantic import BaseModel

from app.agents.base import BaseAgent, tag
from app.domain.models import (
    ImplementationResult,
    ReviewIssue,
    ReviewResult,
    ReviewStatus,
    Severity,
    ValidationReport,
)
from app.llm.base import LLMClient
from app.services.verification_service import is_test_file

_RANK = {ReviewStatus.APPROVED: 0, ReviewStatus.CHANGES_REQUIRED: 1, ReviewStatus.BLOCKED: 2}


class ReviewInput(BaseModel):
    task: str
    implementation: ImplementationResult
    validation: ValidationReport


class ReviewerAgent(BaseAgent[ReviewInput, ReviewResult]):
    name = "reviewer"
    output_schema = ReviewResult

    def __init__(self, llm: LLMClient):
        super().__init__(llm)

    def system_prompt(self) -> str:
        return (
            "You are an independent, skeptical Code Reviewer. Review the ACTUAL code in <file> tags (not the coder's "
            "claims) against the task. Check correctness, edge cases, error handling, input validation, security, "
            "readability and whether tests meaningfully cover the requirements. Return status APPROVED, "
            "CHANGES_REQUIRED or BLOCKED (BLOCKED only if the task is unsafe/impossible). Never approve just because "
            "another agent wrote it. Give file and line when known and an actionable recommendation. "
            "Your own findings are opinions: you cannot run code; tool results provided under TOOL FACTS are verified."
        )

    def build_user_prompt(self, data: ReviewInput, extras: dict[str, Any]) -> str:
        v = data.validation
        facts = [
            f"guardrail_violations: {v.guardrail_violations or 'none'}",
            f"syntax_errors: {v.syntax_errors or 'none'}",
            f"tests_run: {v.tests_run}; tests_passed: {v.tests_passed}; skipped: {v.skipped_reason or 'no'}",
            f"lint_passed: {v.lint_passed}",
            f"test_output_tail:\n{v.test_output[-1500:]}",
        ]
        files = "\n\n".join(
            f'<file path="{f.path}">\n' + "\n".join(f"{n}: {line}" for n, line in enumerate(f.content.splitlines(), 1))
            .replace("</", "<\\/") + "\n</file>"
            for f in data.implementation.files
        )
        return "\n\n".join(["Review this change.", tag("task", data.task), "TOOL FACTS:\n" + "\n".join(facts), files])

    def postprocess(self, data: ReviewInput, llm_output: ReviewResult, extras: dict[str, Any]) -> ReviewResult:
        """Deterministic enforcement: the LLM can be stricter than the tools but NEVER more lenient."""
        issues = [i.model_copy(update={"verified": False}) for i in llm_output.issues]  # opinions are never 'verified'
        v = data.validation
        facts: list[ReviewIssue] = []
        facts += [ReviewIssue(severity=Severity.CRITICAL, verified=True, description=m,
                              recommendation="Remove the unsafe construct and re-implement safely.")
                  for m in v.guardrail_violations]
        facts += [ReviewIssue(severity=Severity.CRITICAL, verified=True, description=f"Syntax error: {m}",
                              recommendation="Fix the syntax error.") for m in v.syntax_errors]
        if not any(is_test_file(f.path) for f in data.implementation.files):
            facts.append(ReviewIssue(severity=Severity.MAJOR, verified=True, description="No test file was provided.",
                                     recommendation="Add pytest tests covering success and failure cases."))
        elif not v.guardrail_violations and not v.syntax_errors:
            if not v.tests_run or v.tests_passed is None:
                facts.append(ReviewIssue(severity=Severity.MAJOR, verified=True,
                                         description=f"Tests could not be executed: {v.skipped_reason or v.test_output[-300:]}",
                                         recommendation="Make the tests runnable (importable module names, no hangs)."))
            elif not v.tests_passed:
                facts.append(ReviewIssue(severity=Severity.MAJOR, verified=True,
                                         description="Tests FAILED when executed:\n" + v.test_output[-1200:],
                                         recommendation="Fix the implementation (or incorrect tests) so all tests pass."))
        if v.lint_passed is False:
            facts.append(ReviewIssue(severity=Severity.MINOR, verified=True,
                                     description="Static analysis (ruff E9,F) reported problems:\n" + v.lint_output[-600:],
                                     recommendation="Resolve the reported lint findings."))

        all_issues = facts + issues
        computed = ReviewStatus.APPROVED
        if any(i.severity in (Severity.CRITICAL, Severity.MAJOR) for i in all_issues):
            computed = ReviewStatus.CHANGES_REQUIRED
        status = max(llm_output.status, computed, key=lambda s: _RANK[s])
        summary = llm_output.summary
        if status != llm_output.status:
            summary = f"[auto-corrected from {llm_output.status.value}: tool-verified problems exist] {summary}"
        return ReviewResult(status=status, summary=summary, issues=all_issues)
