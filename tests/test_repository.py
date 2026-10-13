import pytest

from app.core.exceptions import GuardrailViolationError
from app.domain.models import FileChange, WorkflowResult, WorkflowStatus
from app.repositories.db import create_db_engine, init_db, make_session_factory
from app.repositories.workflow_repository import SqlAlchemyWorkflowRepository
from app.repositories.workspace_repository import FileSystemWorkspaceRepository


@pytest.fixture
def repo():
    e = create_db_engine("sqlite://")
    init_db(e)
    return SqlAlchemyWorkflowRepository(make_session_factory(e))


def test_workflow_lifecycle_and_events(repo):
    rec = repo.create("t1", "task", "ctx")
    assert rec.status == WorkflowStatus.PENDING and repo.ping()
    repo.update_progress("t1", WorkflowStatus.RUNNING, "code", 1)
    repo.add_event("t1", "first"); repo.add_event("t1", "second")
    assert [e.message for e in repo.list_events("t1")] == ["first", "second"]
    repo.save_result(WorkflowResult(task_id="t1", workflow_status=WorkflowStatus.COMPLETED, iterations=2, final_response="done"))
    got = repo.get("t1")
    assert got.status == WorkflowStatus.COMPLETED and got.result.final_response == "done" and got.iteration_count == 2
    assert repo.get("missing") is None and [r.task_id for r in repo.list_recent()] == ["t1"]


def test_workspace_path_jail_and_atomic_validation(tmp_path):
    ws = FileSystemWorkspaceRepository(tmp_path / "ws")
    with pytest.raises(GuardrailViolationError):
        ws.write_files([FileChange(path="ok.py", content="x"), FileChange(path="../escape.py", content="y")])
    assert not (tmp_path / "ws" / "ok.py").exists()  # nothing written because one path was bad
    assert ws.write_files([FileChange(path="pkg/mod.py", content="x = 1")]) == ["pkg/mod.py"]


def test_snapshot_skips_secrets_and_junk(tmp_path):
    root = tmp_path / "ws"; (root / ".git").mkdir(parents=True); (root / "__pycache__").mkdir()
    (root / "a.py").write_text("x"); (root / ".env").write_text("KEY=1"); (root / ".git" / "c.txt").write_text("z")
    (root / "bin.dat").write_bytes(b"\x00\x01")
    assert list(FileSystemWorkspaceRepository(root).snapshot()) == ["a.py"]
