"""Service layer: business logic for running/inspecting workflows. No HTTP, no SQL, no vendor SDKs in here."""
import logging
import uuid
from dataclasses import dataclass

from app.core.exceptions import NotFoundError
from app.domain.models import WorkflowResult, WorkflowStatus
from app.domain.state import WorkflowState
from app.repositories.workflow_repository import WorkflowEventRecord, WorkflowRecord, WorkflowRepository
from app.repositories.workspace_repository import WorkspaceWriter
from app.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubmitWorkflowCommand:
    task: str
    context: str = ""
    apply_changes: bool = False
    max_iterations: int | None = None


class WorkflowService:
    def __init__(
        self,
        repository: WorkflowRepository,
        engine: WorkflowEngine,
        workspace_writer: WorkspaceWriter,
        max_iterations: int,
        apply_changes_enabled: bool = False,
    ):
        self._repo = repository
        self._engine = engine
        self._writer = workspace_writer
        self._max_iterations = max_iterations
        self._apply_enabled = apply_changes_enabled

    def run(self, cmd: SubmitWorkflowCommand) -> WorkflowResult:
        task_id = uuid.uuid4().hex
        max_iter = min(cmd.max_iterations or self._max_iterations, self._max_iterations)
        self._repo.create(task_id, cmd.task, cmd.context)

        initial: WorkflowState = {
            "task_id": task_id,
            "user_request": cmd.task,
            "context": cmd.context,
            "iteration_count": 0,
            "max_iterations": max_iter,
            "workflow_status": WorkflowStatus.RUNNING,
            "errors": [],
            "trace": [],
        }
        self._repo.update_progress(task_id, WorkflowStatus.RUNNING, "start", 0)

        final: WorkflowState = initial
        seen = 0
        try:
            for snapshot in self._engine.stream(initial):
                final = snapshot
                trace = snapshot.get("trace", [])
                for line in trace[seen:]:  # persist progress as it happens (pollable via GET /events)
                    self._repo.add_event(task_id, line)
                if len(trace) > seen:
                    self._repo.update_progress(
                        task_id, WorkflowStatus.RUNNING, trace[-1].split(":")[0], snapshot.get("iteration_count", 0)
                    )
                seen = len(trace)
        except Exception:  # engine-level failure (e.g. recursion limit): never lose the run
            logger.exception("workflow engine crashed task_id=%s", task_id)
            final = {**final, "workflow_status": WorkflowStatus.FAILED,
                     "errors": final.get("errors", []) + ["workflow engine failure"]}

        result = self._build_result(final)
        self._maybe_apply(cmd, result)
        self._repo.save_result(result)
        logger.info("workflow %s finished status=%s iterations=%s", task_id, result.workflow_status, result.iterations)
        return result

    def get(self, task_id: str) -> WorkflowRecord:
        record = self._repo.get(task_id)
        if record is None:
            raise NotFoundError(f"Workflow '{task_id}' not found")
        return record

    def events(self, task_id: str) -> list[WorkflowEventRecord]:
        self.get(task_id)
        return self._repo.list_events(task_id)

    def recent(self, limit: int = 20) -> list[WorkflowRecord]:
        return self._repo.list_recent(limit)

    # ------------------------------------------------------------------------------------------
    @staticmethod
    def _build_result(state: WorkflowState) -> WorkflowResult:
        status = state.get("workflow_status", WorkflowStatus.FAILED)
        if status == WorkflowStatus.RUNNING:  # graph ended without finalize => treat as failure, never success
            status = WorkflowStatus.FAILED
        return WorkflowResult(
            task_id=state["task_id"],
            workflow_status=status,
            research=state.get("research_findings"),
            implementation=state.get("proposed_changes"),
            validation=state.get("validation"),
            review=state.get("review_findings"),
            iterations=state.get("iteration_count", 0),
            errors=state.get("errors", []),
            trace=state.get("trace", []),
            final_response=state.get("final_response", ""),
        )

    def _maybe_apply(self, cmd: SubmitWorkflowCommand, result: WorkflowResult) -> None:
        if not cmd.apply_changes:
            return
        if result.workflow_status != WorkflowStatus.COMPLETED or not result.implementation:
            result.warnings.append("apply_changes ignored: workflow was not approved")
        elif not self._apply_enabled:
            result.warnings.append("apply_changes ignored: disabled on this server (APPLY_CHANGES_ENABLED=false)")
        else:
            result.applied_files = self._writer.write_files(result.implementation.files)
