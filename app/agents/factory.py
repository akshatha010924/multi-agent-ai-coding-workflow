"""Factory for the agent trio (single wiring point; keeps the container thin)."""
from dataclasses import dataclass

from app.agents.coder import CoderAgent
from app.agents.researcher import ResearcherAgent
from app.agents.reviewer import ReviewerAgent
from app.llm.base import LLMClient
from app.repositories.workspace_repository import WorkspaceReader
from app.tools.docs_provider import DocsProvider


@dataclass(frozen=True)
class AgentSet:
    researcher: ResearcherAgent
    coder: CoderAgent
    reviewer: ReviewerAgent


def build_agents(llm: LLMClient, docs: DocsProvider, workspace: WorkspaceReader) -> AgentSet:
    return AgentSet(ResearcherAgent(llm, docs), CoderAgent(llm, workspace), ReviewerAgent(llm))
