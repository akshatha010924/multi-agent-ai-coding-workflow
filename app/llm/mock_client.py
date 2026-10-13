"""Deterministic OFFLINE provider (LLM_PROVIDER=mock) for demos and CI. It only knows the email-validator demo.

It is selected explicitly via configuration and is never a silent fallback for a failed real call.
"""
from typing import TypeVar

from pydantic import BaseModel

from app.core.exceptions import LLMError
from app.domain.models import (
    FileChange,
    ImplementationResult,
    LibraryLookup,
    LookupPlan,
    ResearchDraft,
    ReviewResult,
    ReviewStatus,
)
from app.llm import _mock_fixtures as fx
from app.llm.base import LLMClient

T = TypeVar("T", bound=BaseModel)


class MockLLMClient(LLMClient):
    def generate_structured(self, *, system: str, user: str, schema: type[T], agent: str = "") -> T:
        if schema is LookupPlan:
            out: BaseModel = LookupPlan(lookups=[LibraryLookup(library="python re", question="regular expression syntax")])
        elif schema is ResearchDraft:
            out = ResearchDraft(
                task_summary="Validate email addresses with a small pure-Python utility plus pytest tests.",
                findings=["Python's stdlib `re` is sufficient for a pragmatic validator."],
                assumptions=["[mock provider] findings are canned, not researched."],
                recommended_approach="Split local part and domain; validate each with anchored regexes; never raise.",
                dependencies=[],
                risks=["Full RFC 5322 compliance is impractical with a regex."],
                open_questions=["Should internationalised (IDN) addresses be supported?"],
            )
        elif schema is ImplementationResult:
            revising = "REVIEWER FEEDBACK" in user
            impl = fx.FIXED_IMPL if revising else fx.FLAWED_IMPL
            out = ImplementationResult(
                summary="Add `is_valid_email` and parametrised tests." + (" Revised per review." if revising else ""),
                files=[
                    FileChange(path="email_validator_util.py", content=impl, description="Validator"),
                    FileChange(path="test_email_validator_util.py", content=fx.TESTS, description="Tests"),
                ],
                design_decisions=["Pure stdlib; function never raises on bad input."],
                limitations=["Does not support IDN/quoted local parts."],
            )
        elif schema is ReviewResult:
            out = ReviewResult(status=ReviewStatus.APPROVED, summary="[mock reviewer] No additional concerns.", issues=[])
        else:
            raise LLMError(f"MockLLMClient does not support schema {schema.__name__}")
        return out  # type: ignore[return-value]
