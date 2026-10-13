"""Engine port so the service doesn't know about LangGraph (DIP) + the LangGraph adapter."""
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from app.domain.state import WorkflowState


class WorkflowEngine(ABC):
    @abstractmethod
    def stream(self, initial: WorkflowState) -> Iterator[WorkflowState]:
        """Yield the full state after every step; the last item is the final state."""


class LangGraphWorkflowEngine(WorkflowEngine):
    def __init__(self, compiled_graph: Any):
        self._graph = compiled_graph

    def stream(self, initial: WorkflowState) -> Iterator[WorkflowState]:
        # Hard cap on supersteps regardless of routing bugs: 3 setup nodes + 4 per coder iteration + finalize.
        limit = 8 + 4 * initial.get("max_iterations", 3)
        yield from self._graph.stream(initial, config={"recursion_limit": limit}, stream_mode="values")
