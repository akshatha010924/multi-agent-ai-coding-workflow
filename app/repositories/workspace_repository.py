"""Repository for the on-disk workspace. Segregated reader/writer ports (ISP); every path is jailed to the root."""
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.exceptions import GuardrailViolationError
from app.domain.models import FileChange

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "data"}
_TEXT_EXT = {".py", ".md", ".txt", ".toml", ".json", ".yaml", ".yml", ".cfg", ".ini"}


class WorkspaceReader(ABC):
    @abstractmethod
    def snapshot(self, max_files: int = 20, max_chars: int = 20_000) -> dict[str, str]:
        """Relative-path -> content of small text files (bounded)."""


class WorkspaceWriter(ABC):
    @abstractmethod
    def write_files(self, changes: list[FileChange]) -> list[str]: ...


class FileSystemWorkspaceRepository(WorkspaceReader, WorkspaceWriter):
    def __init__(self, root: Path):
        self._root = Path(root).resolve()

    def _resolve(self, rel: str) -> Path:
        target = (self._root / rel).resolve()
        if not target.is_relative_to(self._root) or target == self._root:
            raise GuardrailViolationError(f"Path '{rel}' escapes the workspace")
        return target

    def snapshot(self, max_files: int = 20, max_chars: int = 20_000) -> dict[str, str]:
        if not self._root.is_dir():
            return {}
        out: dict[str, str] = {}
        budget = max_chars
        for p in sorted(self._root.rglob("*")):
            rel = p.relative_to(self._root)
            if (
                not p.is_file()
                or p.is_symlink()
                or any(part in _SKIP_DIRS for part in rel.parts)
                or p.name.startswith(".env")
                or p.suffix.lower() not in _TEXT_EXT
            ):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if len(out) >= max_files or len(text) > budget:
                continue
            out[rel.as_posix()] = text
            budget -= len(text)
        return out

    def write_files(self, changes: list[FileChange]) -> list[str]:
        targets = [(self._resolve(c.path), c) for c in changes]  # validate ALL paths before writing ANY
        written: list[str] = []
        for target, change in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")
            written.append(change.path)
        return written
