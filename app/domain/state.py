"""Explicit LangGraph workflow state. `errors` and `trace` use append reducers; all else is overwritten."""
import operator
from typing import Annotated, TypedDict

from app.domain.models import (
    ImplementationResult,
    ResearchReport,
    ReviewResult,
    ReviewStatus,
    ValidationReport,
    WorkflowStatus,
)


class WorkflowState(TypedDict, total=False):
    task_id: str
    user_request: str
    context: str
    research_findings: ResearchReport | None
    implementation_plan: str
    proposed_changes: ImplementationResult | None
    validation: ValidationReport | None
    review_findings: ReviewResult | None
    review_status: ReviewStatus | None
    iteration_count: int
    max_iterations: int
    workflow_status: WorkflowStatus
    errors: Annotated[list[str], operator.add]
    trace: Annotated[list[str], operator.add]
    final_response: str
