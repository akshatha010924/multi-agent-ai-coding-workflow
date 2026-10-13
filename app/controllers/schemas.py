"""API contracts. Request validation (syntax) + response shaping/redaction live in the controller layer."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models import ReviewStatus, Severity, ValidationReport, WorkflowResult, WorkflowStatus
from app.guardrails.patterns import redact


class WorkflowCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task: str = Field(
        min_length=10, max_length=4000, examples=["Implement a Python function that validates an email address, with tests"]
    )
    context: str = Field("", max_length=8000)
    apply_changes: bool = Field(False, description="Write approved files into the server workspace (if enabled server-side)")
    max_iterations: int | None = Field(None, ge=1, le=5, description="Cap on coder attempts (server max still applies)")

    @field_validator("task")
    @classmethod
    def _task_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("task must not be blank")
        return v


class TestResultsSchema(BaseModel):
    tests_run: bool
    tests_passed: bool | None
    lint_passed: bool | None
    summary: str


class IssueSchema(BaseModel):
    severity: Severity
    description: str
    file: str | None = None
    line: int | None = None
    verified: bool
    recommendation: str = ""


class FileSchema(BaseModel):
    path: str
    content: str


def _test_summary(v: ValidationReport) -> str:
    """One-line, redacted human summary: why tests were skipped, else pytest's final line."""
    if v.skipped_reason:
        return redact(v.skipped_reason)
    lines = v.test_output.strip().splitlines()
    return redact(lines[-1]) if lines else ""


class WorkflowResponse(BaseModel):
    task_id: str
    workflow_status: WorkflowStatus
    research_summary: str | None
    research_references: list[str]
    implementation_summary: str | None
    files: list[FileSchema]
    review_status: ReviewStatus | None
    test_results: TestResultsSchema | None
    unresolved_issues: list[IssueSchema]
    iterations: int
    applied_files: list[str]
    warnings: list[str]
    errors: list[str]
    final_response: str

    @classmethod
    def from_result(cls, r: WorkflowResult) -> "WorkflowResponse":
        """Output validation: shape the domain result and redact anything secret-looking."""
        v = r.validation
        files = r.implementation.files if r.implementation else []
        approved = r.review is not None and r.review.status == ReviewStatus.APPROVED
        issues = [] if approved else [IssueSchema(**{**i.model_dump(), "description": redact(i.description)})
                                      for i in (r.review.issues if r.review else [])]
        tests = None
        if v:
            tests = TestResultsSchema(
                tests_run=v.tests_run, tests_passed=v.tests_passed, lint_passed=v.lint_passed, summary=_test_summary(v)
            )
        return cls(
            task_id=r.task_id,
            workflow_status=r.workflow_status,
            research_summary=r.research.task_summary if r.research else None,
            research_references=r.research.references if r.research else [],
            implementation_summary=redact(r.implementation.summary) if r.implementation else None,
            files=[FileSchema(path=f.path, content=redact(f.content)) for f in files],
            review_status=r.review.status if r.review else None,
            test_results=tests,
            unresolved_issues=issues,
            iterations=r.iterations,
            applied_files=r.applied_files,
            warnings=r.warnings,
            errors=[redact(e) for e in r.errors],
            final_response=redact(r.final_response),
        )


class WorkflowStatusResponse(BaseModel):
    task_id: str
    workflow_status: WorkflowStatus
    current_step: str
    iteration_count: int
    created_at: datetime
    updated_at: datetime
    result: WorkflowResponse | None = None


class EventSchema(BaseModel):
    message: str
    created_at: datetime


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
