"""Repository layer: ALL database access lives here. Services see only the abstract interface + domain types."""
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.domain.models import WorkflowResult, WorkflowStatus
from app.repositories.orm import WorkflowEventORM, WorkflowRunORM


class WorkflowRecord(BaseModel):
    task_id: str
    task: str
    context: str
    status: WorkflowStatus
    current_step: str
    iteration_count: int
    result: WorkflowResult | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowEventRecord(BaseModel):
    message: str
    created_at: datetime


class WorkflowRepository(ABC):
    @abstractmethod
    def create(self, task_id: str, task: str, context: str) -> WorkflowRecord: ...

    @abstractmethod
    def update_progress(self, task_id: str, status: WorkflowStatus, current_step: str, iteration_count: int) -> None: ...

    @abstractmethod
    def save_result(self, result: WorkflowResult) -> None: ...

    @abstractmethod
    def get(self, task_id: str) -> WorkflowRecord | None: ...

    @abstractmethod
    def list_recent(self, limit: int = 20) -> list[WorkflowRecord]: ...

    @abstractmethod
    def add_event(self, task_id: str, message: str) -> None: ...

    @abstractmethod
    def list_events(self, task_id: str) -> list[WorkflowEventRecord]: ...

    @abstractmethod
    def ping(self) -> bool: ...


class SqlAlchemyWorkflowRepository(WorkflowRepository):
    def __init__(self, session_factory: sessionmaker):
        self._sf = session_factory

    @staticmethod
    def _to_record(row: WorkflowRunORM) -> WorkflowRecord:
        return WorkflowRecord(
            task_id=row.task_id,
            task=row.task,
            context=row.context,
            status=WorkflowStatus(row.status),
            current_step=row.current_step,
            iteration_count=row.iteration_count,
            result=WorkflowResult.model_validate_json(row.result_json) if row.result_json else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def create(self, task_id: str, task: str, context: str) -> WorkflowRecord:
        with self._sf() as s, s.begin():
            row = WorkflowRunORM(task_id=task_id, task=task, context=context, status=WorkflowStatus.PENDING.value)
            s.add(row)
            s.flush()
            return self._to_record(row)

    def update_progress(self, task_id: str, status: WorkflowStatus, current_step: str, iteration_count: int) -> None:
        with self._sf() as s, s.begin():
            row = s.get(WorkflowRunORM, task_id)
            if row:
                row.status, row.current_step, row.iteration_count = status.value, current_step, iteration_count

    def save_result(self, result: WorkflowResult) -> None:
        with self._sf() as s, s.begin():
            row = s.get(WorkflowRunORM, result.task_id)
            if row:
                row.status = result.workflow_status.value
                row.iteration_count = result.iterations
                row.current_step = "finalize"
                row.result_json = result.model_dump_json()

    def get(self, task_id: str) -> WorkflowRecord | None:
        with self._sf() as s:
            row = s.get(WorkflowRunORM, task_id)
            return self._to_record(row) if row else None

    def list_recent(self, limit: int = 20) -> list[WorkflowRecord]:
        with self._sf() as s:
            rows = s.scalars(select(WorkflowRunORM).order_by(WorkflowRunORM.created_at.desc()).limit(limit)).all()
            return [self._to_record(r) for r in rows]

    def add_event(self, task_id: str, message: str) -> None:
        with self._sf() as s, s.begin():
            s.add(WorkflowEventORM(task_id=task_id, message=message))

    def list_events(self, task_id: str) -> list[WorkflowEventRecord]:
        with self._sf() as s:
            rows = s.scalars(
                select(WorkflowEventORM).where(WorkflowEventORM.task_id == task_id).order_by(WorkflowEventORM.id)
            ).all()
            return [WorkflowEventRecord(message=r.message, created_at=r.created_at) for r in rows]

    def ping(self) -> bool:
        try:
            with self._sf() as s:
                s.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
