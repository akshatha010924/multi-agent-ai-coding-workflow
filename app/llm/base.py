"""LLM abstraction (Strategy pattern). Agents depend on this, never on a vendor SDK (DIP)."""
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(ABC):
    @abstractmethod
    def generate_structured(self, *, system: str, user: str, schema: type[T], agent: str = "") -> T:
        """Return an instance of `schema`, or raise an LLMError subclass. Never fabricate output."""
