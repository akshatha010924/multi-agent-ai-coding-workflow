"""Guardrail abstractions: Chain of Responsibility over independent, single-purpose checks (SRP/OCP)."""
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from app.core.exceptions import GuardrailViolationError

T = TypeVar("T")


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    severity: Literal["block", "warn"] = "block"

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}"


class Guardrail(ABC, Generic[T]):
    @abstractmethod
    def check(self, target: T) -> list[Violation]: ...


class GuardrailChain(Generic[T]):
    def __init__(self, guards: Sequence[Guardrail[T]]):
        self._guards = list(guards)

    def evaluate(self, target: T) -> list[Violation]:
        found: list[Violation] = []
        for guard in self._guards:
            found.extend(guard.check(target))
        return found

    def enforce(self, target: T) -> None:
        blocking = [v for v in self.evaluate(target) if v.severity == "block"]
        if blocking:
            raise GuardrailViolationError("; ".join(str(v) for v in blocking))
