import pytest

from app.domain.models import FileChange, ImplementationResult
from app.guardrails.output_guards import build_output_guardrails
from app.repositories.workspace_repository import FileSystemWorkspaceRepository
from app.services.sandbox import SubprocessSandboxRunner
from app.services.verification_service import VerificationService
from tests.conftest import impl

pytestmark = pytest.mark.integration


@pytest.fixture
def verifier(tmp_path):
    return VerificationService(build_output_guardrails(), SubprocessSandboxRunner(timeout_seconds=5), FileSystemWorkspaceRepository(tmp_path))


def test_good_code_passes_real_pytest(verifier):
    r = verifier.verify(impl(True))
    assert r.tests_run and r.tests_passed and r.lint_passed in (True, None) and "passed" in r.test_output


def test_defective_code_is_detected_by_real_execution(verifier):
    r = verifier.verify(impl(False))
    assert r.tests_run and r.tests_passed is False and "failed" in r.test_output


def test_syntax_error_skips_execution(verifier):
    bad = ImplementationResult(summary="s", files=[FileChange(path="a.py", content="def (:\n"), FileChange(path="test_a.py", content="x=1")])
    r = verifier.verify(bad)
    assert r.syntax_errors and not r.tests_run and "syntax" in r.skipped_reason


def test_missing_tests_reported(verifier):
    r = verifier.verify(ImplementationResult(summary="s", files=[FileChange(path="a.py", content="x = 1\n")]))
    assert not r.tests_run and "no test files" in r.skipped_reason


def test_infinite_loop_is_killed_by_timeout(verifier):
    hang = ImplementationResult(summary="s", files=[FileChange(path="test_h.py", content="def test_h():\n    while True:\n        pass\n")])
    r = verifier.verify(hang)
    assert r.tests_run is False and r.tests_passed is False


def test_sandbox_does_not_inherit_secrets(verifier, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak-1234567890")
    probe = ImplementationResult(summary="s", files=[FileChange(
        path="test_env.py", content="import os\n\ndef test_env():\n    assert 'ANTHROPIC_API_KEY' not in os.environ\n")])
    assert verifier.verify(probe).tests_passed is True


def test_existing_workspace_files_are_importable_by_new_tests(tmp_path):
    (tmp_path / "helper.py").write_text("def two():\n    return 2\n")
    v = VerificationService(build_output_guardrails(), SubprocessSandboxRunner(timeout_seconds=5), FileSystemWorkspaceRepository(tmp_path))
    r = v.verify(ImplementationResult(summary="s", files=[FileChange(path="test_h.py", content="from helper import two\n\ndef test_t():\n    assert two() == 2\n")]))
    assert r.tests_passed is True
