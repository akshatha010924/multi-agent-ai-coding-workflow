from typing import Any

from pydantic import BaseModel

from app.agents.base import BaseAgent, tag
from app.domain.models import ImplementationResult, ResearchReport, ReviewResult, ValidationReport
from app.llm.base import LLMClient
from app.repositories.workspace_repository import WorkspaceReader


class CodingInput(BaseModel):
    task: str
    context: str = ""
    research: ResearchReport
    previous: ImplementationResult | None = None
    feedback: ReviewResult | None = None
    validation: ValidationReport | None = None


class CoderAgent(BaseAgent[CodingInput, ImplementationResult]):
    name = "coder"
    output_schema = ImplementationResult

    def __init__(self, llm: LLMClient, workspace: WorkspaceReader):
        super().__init__(llm)
        self._workspace = workspace

    def system_prompt(self) -> str:
        return (
            "You are the Coder in a multi-agent coding workflow. Implement the task using the research report.\n"
            "Rules:\n"
            "- Return the COMPLETE content of every file you create or change (no diffs, no placeholders, no TODOs).\n"
            "- Use relative paths only. Only touch files needed for the task; do not modify unrelated existing files.\n"
            "- Follow the conventions of the existing files shown in <file> tags.\n"
            "- ALWAYS include pytest tests (file name starting with `test_`) that import your module by its top-level name.\n"
            "- Prefer the standard library. Handle bad input without crashing. No secrets in code.\n"
            "- FORBIDDEN (code is rejected before execution): subprocess, socket, network libraries, eval/exec/compile, "
            "os.system, deleting files, pickle, importlib.\n"
            "- If REVIEWER FEEDBACK is present, fix every listed problem and re-verify your tests mentally before answering."
        )

    def prepare(self, data: CodingInput) -> dict[str, Any]:
        return {"workspace": self._workspace.snapshot(max_files=12, max_chars=16_000)}

    def build_user_prompt(self, data: CodingInput, extras: dict[str, Any]) -> str:
        r = data.research
        parts = [
            "Implement this task.",
            tag("task", data.task),
            tag("context", data.context or "(none)"),
            "Research summary:",
            f"Approach: {r.recommended_approach}",
            "Findings: " + "; ".join(r.findings),
            "Risks: " + "; ".join(r.risks),
            "Dependencies: " + (", ".join(r.dependencies) or "none"),
        ]
        ws: dict[str, str] = extras["workspace"]
        parts.append("Existing workspace files:" if ws else "The workspace is empty (new project).")
        parts += [f'<file path="{p}">\n{c.replace("</", "<\\/")}\n</file>' for p, c in ws.items()]
        if data.feedback:
            lines = [f"status={data.feedback.status.value}; {data.feedback.summary}"]
            lines += [
                f"- [{i.severity.value}{'/VERIFIED' if i.verified else '/suspected'}] {i.file or ''}:{i.line or ''} "
                f"{i.description} -> {i.recommendation}"
                for i in data.feedback.issues
            ]
            parts.append("REVIEWER FEEDBACK (fix all):")
            parts.append(tag("review_feedback", "\n".join(lines)))
            if data.validation and data.validation.test_output:
                parts.append(tag("review_feedback", "Test output:\n" + data.validation.test_output))
            if data.previous:
                parts.append("Your previous attempt (revise it):")
                parts += [f'<file path="{f.path}">\n{f.content.replace("</", "<\\/")}\n</file>' for f in data.previous.files]
        return "\n\n".join(parts)

    def postprocess(self, data: CodingInput, llm_output: ImplementationResult, extras: dict[str, Any]) -> ImplementationResult:
        return llm_output  # guardrails + verification run in the dedicated verify node
