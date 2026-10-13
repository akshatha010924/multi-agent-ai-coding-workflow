"""Output guardrails: applied to LLM-generated code BEFORE it is executed or written anywhere."""
import ast
import posixpath
from pathlib import PurePosixPath

from app.domain.models import ImplementationResult
from app.guardrails.base import Guardrail, GuardrailChain, Violation
from app.guardrails.patterns import SECRET_PATTERNS

ALLOWED_EXTENSIONS = {".py", ".md", ".txt", ".toml", ".json", ".yaml", ".yml", ".cfg", ".ini"}
FORBIDDEN_FILENAMES = {".env", "id_rsa", "id_ed25519", "credentials", "credentials.json"}
FORBIDDEN_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ssh"}
BANNED_MODULES = {
    "subprocess", "socket", "ctypes", "shutil", "requests", "httpx", "urllib", "http", "ftplib",
    "smtplib", "telnetlib", "multiprocessing", "pickle", "marshal", "importlib", "pty", "signal",
}
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint"}
BANNED_ATTR_CALLS = {
    "os.system", "os.popen", "os.remove", "os.unlink", "os.rmdir", "os.removedirs", "os.kill",
    "os.fork", "os.execv", "os.execve", "os.execl", "os.spawnl", "os.spawnv", "sys.exit",
}
MAX_FILE_BYTES = 100_000


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


class FileScopeGuard(Guardrail[ImplementationResult]):
    """Paths must be relative, inside the workspace, non-sensitive, and of an allowed type."""

    def check(self, target: ImplementationResult) -> list[Violation]:
        out: list[Violation] = []
        seen: set[str] = set()
        for f in target.files:
            p = f.path
            norm = posixpath.normpath(p.replace("\\", "/"))
            parts = PurePosixPath(norm).parts
            if p in seen:
                out.append(Violation("duplicate_path", f"Duplicate file path '{p}'"))
            seen.add(p)
            if p.startswith(("/", "~")) or ":" in p or ".." in parts or "\x00" in p:
                out.append(Violation("path_traversal", f"Path '{p}' escapes the workspace"))
                continue
            if any(part in FORBIDDEN_DIRS for part in parts) or parts[-1] in FORBIDDEN_FILENAMES or parts[-1].startswith(".env"):
                out.append(Violation("forbidden_path", f"Path '{p}' targets a protected location"))
            if PurePosixPath(norm).suffix.lower() not in ALLOWED_EXTENSIONS:
                out.append(Violation("file_type", f"File type of '{p}' is not allowed"))
            if len(f.content.encode()) > MAX_FILE_BYTES:
                out.append(Violation("file_size", f"'{p}' exceeds {MAX_FILE_BYTES} bytes"))
        return out


class CodeSafetyGuard(Guardrail[ImplementationResult]):
    """AST scan for dangerous imports/calls. Unparseable files are reported by the syntax check instead."""

    def check(self, target: ImplementationResult) -> list[Violation]:
        out: list[Violation] = []
        for f in target.files:
            if not f.path.endswith(".py"):
                continue
            try:
                tree = ast.parse(f.content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module.split(".")[0]]
                else:
                    mods = []
                for m in mods:
                    if m in BANNED_MODULES:
                        out.append(Violation("banned_import", f"{f.path}:{node.lineno} imports banned module '{m}'"))
                if isinstance(node, ast.Call):
                    name = _dotted(node.func)
                    if name in BANNED_CALLS or name in BANNED_ATTR_CALLS:
                        out.append(Violation("banned_call", f"{f.path}:{node.lineno} calls banned function '{name}'"))
        return out


class HardcodedSecretGuard(Guardrail[ImplementationResult]):
    def check(self, target: ImplementationResult) -> list[Violation]:
        return [
            Violation("hardcoded_secret", f"{f.path} appears to contain a hardcoded secret ({name})")
            for f in target.files
            for name, p in SECRET_PATTERNS.items()
            if p.search(f.content)
        ]


def build_output_guardrails() -> GuardrailChain[ImplementationResult]:
    return GuardrailChain([FileScopeGuard(), CodeSafetyGuard(), HardcodedSecretGuard()])
