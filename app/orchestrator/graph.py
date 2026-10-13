"""LangGraph state machine (bounded). Routing depends ONLY on explicit state.

  START -> research -> code -> verify -> review -> {APPROVED|BLOCKED|limit} -> finalize -> END
                         ^                           |
                         +---- CHANGES_REQUIRED -----+   (only while iteration_count < max_iterations)
Any node error routes straight to finalize (status FAILED).
"""
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.domain.models import ReviewStatus
from app.domain.state import WorkflowState
from app.orchestrator.nodes import WorkflowNodes


def _after(next_node: str):
    def route(state: WorkflowState) -> str:
        return "finalize" if state.get("errors") else next_node

    return route


def route_after_review(state: WorkflowState) -> str:
    if state.get("errors"):
        return "finalize"
    status = state.get("review_status")
    if status == ReviewStatus.CHANGES_REQUIRED and state.get("iteration_count", 0) < state.get("max_iterations", 1):
        return "code"
    return "finalize"  # APPROVED, BLOCKED, or iteration limit reached


def build_workflow_graph(nodes: WorkflowNodes) -> Any:
    g = StateGraph(WorkflowState)
    g.add_node("research", nodes.research)
    g.add_node("code", nodes.code)
    g.add_node("verify", nodes.verify)
    g.add_node("review", nodes.review)
    g.add_node("finalize", nodes.finalize)

    g.add_edge(START, "research")
    g.add_conditional_edges("research", _after("code"), {"code": "code", "finalize": "finalize"})
    g.add_conditional_edges("code", _after("verify"), {"verify": "verify", "finalize": "finalize"})
    g.add_conditional_edges("verify", _after("review"), {"review": "review", "finalize": "finalize"})
    g.add_conditional_edges("review", route_after_review, {"code": "code", "finalize": "finalize"})
    g.add_edge("finalize", END)
    return g.compile()
