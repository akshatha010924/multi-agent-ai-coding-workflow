"""Graph nodes. Each node: explicit input (state slice) -> explicit output (state update). Errors never escape."""
import functools
import logging
from collections.abc import Callable
from typing import Any

from app.agents.coder import CoderAgent, CodingInput
from app.agents.researcher import ResearcherAgent, ResearchInput
from app.agents.reviewer import ReviewerAgent, ReviewInput
from app.core.exceptions import AppError
from app.domain.models import ReviewStatus, WorkflowStatus
from app.domain.state import WorkflowState
from app.services.verification_service import VerificationService

logger = logging.getLogger(__name__)


def _guarded(name: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(self: "WorkflowNodes", state: WorkflowState) -> dict[str, Any]:
            try:
                return fn(self, state)
            except AppError as exc:
                logger.warning("node %s failed: %s (%s)", name, exc.message, exc.code)
                return {"errors": [f"{name}: {exc.message}"], "trace": [f"{name}: FAILED ({exc.code})"]}
            except Exception:
                logger.exception("node %s crashed", name)  # full detail in logs only
                return {"errors": [f"{name}: unexpected internal error"], "trace": [f"{name}: FAILED (internal)"]}

        return wrapper

    return deco


class WorkflowNodes:
    def __init__(self, researcher: ResearcherAgent, coder: CoderAgent, reviewer: ReviewerAgent, verifier: VerificationService):
        self._researcher, self._coder, self._reviewer, self._verifier = researcher, coder, reviewer, verifier

    @_guarded("research")
    def research(self, state: WorkflowState) -> dict[str, Any]:
        report = self._researcher.run(ResearchInput(task=state["user_request"], context=state.get("context", "")))
        return {
            "research_findings": report,
            "implementation_plan": report.recommended_approach,
            "trace": [f"research: done (docs_consulted={report.docs_consulted})"],
        }

    @_guarded("code")
    def code(self, state: WorkflowState) -> dict[str, Any]:
        attempt = state.get("iteration_count", 0) + 1
        impl = self._coder.run(CodingInput(
            task=state["user_request"],
            context=state.get("context", ""),
            research=state["research_findings"],
            previous=state.get("proposed_changes"),
            feedback=state.get("review_findings"),
            validation=state.get("validation"),
        ))
        return {"proposed_changes": impl, "iteration_count": attempt,
                "trace": [f"code: attempt {attempt} proposed {len(impl.files)} file(s)"]}

    @_guarded("verify")
    def verify(self, state: WorkflowState) -> dict[str, Any]:
        report = self._verifier.verify(state["proposed_changes"])
        outcome = ("guardrail violations" if report.guardrail_violations else
                   "syntax errors" if report.syntax_errors else
                   f"tests_passed={report.tests_passed}")
        return {"validation": report, "trace": [f"verify: {outcome}"]}

    @_guarded("review")
    def review(self, state: WorkflowState) -> dict[str, Any]:
        result = self._reviewer.run(ReviewInput(
            task=state["user_request"], implementation=state["proposed_changes"], validation=state["validation"]
        ))
        return {"review_findings": result, "review_status": result.status,
                "trace": [f"review: {result.status.value} ({len(result.issues)} issue(s))"]}

    def finalize(self, state: WorkflowState) -> dict[str, Any]:
        errors = state.get("errors", [])
        review = state.get("review_findings")
        iters, limit = state.get("iteration_count", 0), state.get("max_iterations", 0)

        if errors:
            status, text = WorkflowStatus.FAILED, "Workflow failed: " + "; ".join(errors)
        elif review and review.status == ReviewStatus.APPROVED:
            status = WorkflowStatus.COMPLETED
            impl = state["proposed_changes"]
            text = f"Approved after {iters} attempt(s). {impl.summary} Files: " + ", ".join(f.path for f in impl.files)
        else:
            status = WorkflowStatus.BLOCKED
            why = ("reviewer BLOCKED the change" if review and review.status == ReviewStatus.BLOCKED
                   else f"iteration limit ({limit}) reached with unresolved issues")
            n = len(review.issues) if review else 0
            text = f"Workflow blocked: {why}. {n} unresolved issue(s). Result is NOT approved."
        return {"workflow_status": status, "final_response": text, "trace": [f"finalize: {status.value}"]}
