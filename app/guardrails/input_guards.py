"""Input guardrails (applied to user text before any agent sees it)."""
from dataclasses import dataclass

from app.guardrails.base import Guardrail, GuardrailChain, Violation
from app.guardrails.patterns import DESTRUCTIVE_PATTERNS, INJECTION_PATTERNS, SECRET_PATTERNS


@dataclass(frozen=True)
class UserInput:
    task: str
    context: str = ""

    @property
    def combined(self) -> str:
        return f"{self.task}\n{self.context}"


class PromptInjectionGuard(Guardrail[UserInput]):
    """Heuristic only: reduces obvious injection; the real defence is delimiting + output validation."""

    def check(self, target: UserInput) -> list[Violation]:
        return [
            Violation("prompt_injection", f"Input matches injection pattern '{name}'")
            for name, p in INJECTION_PATTERNS.items()
            if p.search(target.combined)
        ]


class SecretLeakGuard(Guardrail[UserInput]):
    def check(self, target: UserInput) -> list[Violation]:
        return [
            Violation("secret_in_input", f"Input appears to contain a secret ({name}); remove it and retry")
            for name, p in SECRET_PATTERNS.items()
            if p.search(target.combined)
        ]


class DestructiveIntentGuard(Guardrail[UserInput]):
    def check(self, target: UserInput) -> list[Violation]:
        return [
            Violation("unsafe_request", f"Request matches disallowed intent '{name}'")
            for name, p in DESTRUCTIVE_PATTERNS.items()
            if p.search(target.combined)
        ]


class ControlCharacterGuard(Guardrail[UserInput]):
    def check(self, target: UserInput) -> list[Violation]:
        if any(ord(c) < 32 and c not in "\n\r\t" for c in target.combined):
            return [Violation("control_chars", "Input contains non-printable control characters")]
        return []


def build_input_guardrails() -> GuardrailChain[UserInput]:
    return GuardrailChain(
        [ControlCharacterGuard(), PromptInjectionGuard(), SecretLeakGuard(), DestructiveIntentGuard()]
    )
