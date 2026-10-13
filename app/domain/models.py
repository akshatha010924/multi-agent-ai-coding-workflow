"""Domain models: the structured contracts exchanged between agents (all validated by Pydantic)."""
from enum import StrEnum

from pydantic import BaseModel, Field


class WorkflowStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"  # reviewer blocked it, or iteration limit reached with open issues
    FAILED = "FAILED"  # fatal error (LLM/tool/internal)


class ReviewStatus(StrEnum):
    APPROVED = "APPROVED"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    BLOCKED = "BLOCKED"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


# ---------- Researcher ----------
class LibraryLookup(BaseModel):
    library: str = Field(max_length=80, description="Library/framework name, e.g. 'fastapi'")
    question: str = Field(max_length=300, description="What to look up in its documentation")


class LookupPlan(BaseModel):
    lookups: list[LibraryLookup] = Field(default_factory=list, max_length=2)


class ResearchDraft(BaseModel):
    """What the LLM produces. References are NOT LLM-authored (prevents invented citations)."""

    task_summary: str
    findings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    recommended_approach: str
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ResearchReport(ResearchDraft):
    references: list[str] = Field(default_factory=list)
    docs_consulted: bool = False
    tool_notes: list[str] = Field(default_factory=list)


# ---------- Coder ----------
class FileChange(BaseModel):
    path: str = Field(min_length=1, max_length=200, description="Relative path inside the workspace")
    content: str = Field(max_length=100_000, description="COMPLETE new content of the file")
    description: str = ""


class ImplementationResult(BaseModel):
    summary: str
    files: list[FileChange] = Field(min_length=1, max_length=10)
    design_decisions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


# ---------- Verification (tool-derived facts, never LLM opinions) ----------
class ValidationReport(BaseModel):
    guardrail_violations: list[str] = Field(default_factory=list)
    syntax_errors: list[str] = Field(default_factory=list)
    tests_run: bool = False
    tests_passed: bool | None = None
    test_output: str = ""
    lint_passed: bool | None = None
    lint_output: str = ""
    skipped_reason: str | None = None


# ---------- Reviewer ----------
class ReviewIssue(BaseModel):
    severity: Severity
    description: str
    file: str | None = None
    line: int | None = None
    verified: bool = Field(False, description="True only if proven by a tool result, not by opinion")
    recommendation: str = ""


class ReviewResult(BaseModel):
    status: ReviewStatus
    summary: str
    issues: list[ReviewIssue] = Field(default_factory=list)


# ---------- Final result ----------
class WorkflowResult(BaseModel):
    task_id: str
    workflow_status: WorkflowStatus
    research: ResearchReport | None = None
    implementation: ImplementationResult | None = None
    validation: ValidationReport | None = None
    review: ReviewResult | None = None
    iterations: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    applied_files: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    final_response: str = ""
