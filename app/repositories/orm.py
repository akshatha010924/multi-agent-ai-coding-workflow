from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class WorkflowRunORM(Base):
    __tablename__ = "workflow_runs"

    task_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    task: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), index=True)
    current_step: Mapped[str] = mapped_column(String(40), default="")
    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class WorkflowEventORM(Base):
    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.task_id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_now)
