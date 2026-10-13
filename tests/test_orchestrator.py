import pytest

from app.core.exceptions import LLMAuthError
from app.domain.models import (
    FileChange,
    ReviewResult,
    ReviewStatus,
    WorkflowStatus,
)
from app.services.workflow_service import SubmitWorkflowCommand
from tests.conftest import TASK, FakeRunner, ScriptedLLM, impl


def run(container, **kw):
    return container.service.run(SubmitWorkflowCommand(TASK, **kw))


@pytest.mark.integration
def test_success_flow_with_real_sandbox(container_factory):
    r = run(container_factory(ScriptedLLM(impl=impl(True))))
    assert r.workflow_status == WorkflowStatus.COMPLETED and r.iterations == 1
    assert r.review.status == ReviewStatus.APPROVED and r.validation.tests_passed is True
    assert [t.split(":")[0] for t in r.trace] == ["research", "code", "verify", "review", "finalize"]


@pytest.mark.integration
def test_revision_flow_review_rejects_coder_revises_reviewer_rechecks(container_factory):
    llm = ScriptedLLM(impl=[impl(False), impl(True)])  # LLM reviewer says APPROVED both times
    r = run(container_factory(llm))
    assert r.workflow_status == WorkflowStatus.COMPLETED and r.iterations == 2
    statuses = [t for t in r.trace if t.startswith("review")]
    assert "CHANGES_REQUIRED" in statuses[0] and "APPROVED" in statuses[1]
    coder_prompts = [u for s, u in llm.calls if s == "ImplementationResult"]
    assert "REVIEWER FEEDBACK" not in coder_prompts[0] and "Tests FAILED" in coder_prompts[1]


def test_max_iterations_enforced_and_blocked_is_not_success(container_factory):
    runner = FakeRunner(exit_code=1, output="1 failed")
    llm = ScriptedLLM(impl=impl(False))
    r = run(container_factory(llm, runner, max_review_iterations=2))
    assert r.workflow_status == WorkflowStatus.BLOCKED and r.iterations == 2 and runner.calls == 2
    assert r.review.status == ReviewStatus.CHANGES_REQUIRED
    assert "iteration limit" in r.final_response and "NOT approved" in r.final_response
    assert sum(1 for s, _ in llm.calls if s == "ImplementationResult") == 2


def test_request_level_iteration_cap_cannot_exceed_server_cap(container_factory):
    c = container_factory(ScriptedLLM(impl=impl(False)), FakeRunner(1, "failed"), max_review_iterations=2)
    assert run(c, max_iterations=5).iterations == 2
    assert run(c, max_iterations=1).iterations == 1


def test_agent_failure_is_handled_without_corrupting_state(container_factory):
    llm = ScriptedLLM(impl=LLMAuthError("LLM authentication failed; check ANTHROPIC_API_KEY"))
    runner = FakeRunner()
    r = run(container_factory(llm, runner))
    assert r.workflow_status == WorkflowStatus.FAILED
    assert r.errors == ["code: LLM authentication failed; check ANTHROPIC_API_KEY"]
    assert r.research is not None and r.implementation is None and r.review is None  # earlier work preserved, no fabrication
    assert runner.calls == 0 and "Workflow failed" in r.final_response


def test_unexpected_exception_does_not_leak_internals(container_factory):
    llm = ScriptedLLM(research=lambda u: (_ for _ in ()).throw(RuntimeError("secret internal path /srv/x")))
    r = run(container_factory(llm))
    assert r.workflow_status == WorkflowStatus.FAILED
    assert r.errors == ["research: unexpected internal error"] and "secret" not in r.final_response


def test_reviewer_block_ends_workflow_as_blocked(container_factory):
    llm = ScriptedLLM(impl=impl(True), review=ReviewResult(status=ReviewStatus.BLOCKED, summary="unsafe task"))
    r = run(container_factory(llm, FakeRunner()))
    assert r.workflow_status == WorkflowStatus.BLOCKED and r.iterations == 1 and "BLOCKED" in r.final_response


def test_unsafe_generated_code_is_never_executed(container_factory):
    evil = impl(True, extra=[FileChange(path="evil.py", content="import subprocess\nsubprocess.run(['id'])\n")])
    runner = FakeRunner()
    r = run(container_factory(ScriptedLLM(impl=evil), runner, max_review_iterations=2))
    assert runner.calls == 0
    assert r.workflow_status == WorkflowStatus.BLOCKED
    assert any("banned_import" in v for v in r.validation.guardrail_violations)
    assert r.review.status == ReviewStatus.CHANGES_REQUIRED


def test_apply_changes_only_when_approved_and_enabled(container_factory, tmp_path):
    ok = container_factory(ScriptedLLM(impl=impl(True)), FakeRunner(), apply_changes_enabled=True)
    r = run(ok, apply_changes=True)
    assert r.applied_files == ["email_validator_util.py", "test_email_validator_util.py"]
    assert (tmp_path / "ws" / "email_validator_util.py").exists()

    off = container_factory(ScriptedLLM(impl=impl(True)), FakeRunner(), apply_changes_enabled=False)
    r2 = run(off, apply_changes=True)
    assert r2.applied_files == [] and "disabled" in r2.warnings[0]

    bad = container_factory(ScriptedLLM(impl=impl(False)), FakeRunner(1, "failed"), apply_changes_enabled=True, max_review_iterations=1)
    r3 = run(bad, apply_changes=True)
    assert r3.applied_files == [] and "not approved" in r3.warnings[0]
