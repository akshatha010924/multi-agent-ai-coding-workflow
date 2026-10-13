"""Executes generated tests in an isolated temp dir with a scrubbed env, resource limits and a hard timeout.

HONEST LIMITATION: this is process-level isolation, not a container. Generated code is AST-screened first
(see guardrails), but for hostile multi-tenant use run this inside a container / gVisor / Firecracker.
"""
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
_MAX_OUTPUT = 4000

# Applies resource limits, then hands control to pytest. Done in-process (no preexec_fn => thread-safe).
_PYTEST_BOOTSTRAP = """
import resource, sys
cpu, mem = {cpu}, {mem}
resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
resource.setrlimit(resource.RLIMIT_FSIZE, (10_000_000, 10_000_000))
import pytest
sys.exit(pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", "-c", ".sandbox_pytest.ini", "-W", "ignore"]))
"""


@dataclass
class CommandResult:
    exit_code: int | None
    output: str
    timed_out: bool = False
    unavailable: bool = False


@dataclass
class SandboxReport:
    tests: CommandResult
    lint: CommandResult | None


class CodeRunner(ABC):
    @abstractmethod
    def execute(self, files: Mapping[str, str]) -> SandboxReport: ...


class SubprocessSandboxRunner(CodeRunner):
    def __init__(self, timeout_seconds: int = 30, memory_mb: int = 1024, run_lint: bool = True):
        self._timeout = timeout_seconds
        self._memory = memory_mb * 1024 * 1024
        self._ruff = shutil.which("ruff") if run_lint else None  # resolved once, absolute path
        self._run_lint = run_lint

    def _env(self, root: Path) -> dict[str, str]:
        return {  # no inherited secrets (API keys etc.)
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(root),
            "PYTHONPATH": os.pathsep.join([str(root), str(root / "src")]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "C.UTF-8",
        }

    def _run(self, cmd: list[str], root: Path, timeout: int) -> CommandResult:
        try:
            proc = subprocess.run(  # noqa: S603
                cmd, cwd=root, env=self._env(root), capture_output=True, text=True, timeout=timeout, check=False
            )
            return CommandResult(proc.returncode, (proc.stdout + proc.stderr)[-_MAX_OUTPUT:])
        except subprocess.TimeoutExpired:
            return CommandResult(None, f"Timed out after {timeout}s", timed_out=True)
        except OSError as e:
            return CommandResult(None, f"Could not start process: {e}", unavailable=True)

    def execute(self, files: Mapping[str, str]) -> SandboxReport:
        with tempfile.TemporaryDirectory(prefix="mac_sandbox_") as tmp:
            root = Path(tmp).resolve()
            for rel, content in files.items():
                target = (root / rel).resolve()
                if not target.is_relative_to(root):
                    raise ValueError(f"unsafe path rejected by sandbox: {rel}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            (root / ".sandbox_pytest.ini").write_text("[pytest]\n", encoding="utf-8")  # ignore project pytest config

            boot = _PYTEST_BOOTSTRAP.format(cpu=self._timeout + 5, mem=self._memory)
            tests = self._run([sys.executable, "-c", boot], root, self._timeout)
            lint = None
            if self._run_lint:
                if self._ruff is None:
                    lint = CommandResult(None, "ruff not installed", unavailable=True)
                else:
                    lint = self._run(
                        [self._ruff, "check", "--isolated", "--no-cache", "--select", "E9,F", "."], root, self._timeout
                    )
            return SandboxReport(tests=tests, lint=lint)
