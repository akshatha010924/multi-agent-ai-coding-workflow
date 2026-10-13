"""Composition root: the ONLY place concrete classes are wired together (Dependency Injection)."""
from dataclasses import dataclass

from app.agents.factory import build_agents
from app.config import Settings, get_settings
from app.core.logging import configure_logging
from app.domain.models import ImplementationResult
from app.guardrails.base import GuardrailChain
from app.guardrails.input_guards import UserInput, build_input_guardrails
from app.guardrails.output_guards import build_output_guardrails
from app.llm.base import LLMClient
from app.llm.factory import build_llm_client
from app.orchestrator.graph import build_workflow_graph
from app.orchestrator.nodes import WorkflowNodes
from app.repositories.db import create_db_engine, init_db, make_session_factory
from app.repositories.workflow_repository import SqlAlchemyWorkflowRepository, WorkflowRepository
from app.repositories.workspace_repository import FileSystemWorkspaceRepository
from app.services.sandbox import CodeRunner, SubprocessSandboxRunner
from app.services.verification_service import VerificationService
from app.services.workflow_engine import LangGraphWorkflowEngine
from app.services.workflow_service import WorkflowService
from app.tools.docs_provider import DocsProvider, build_docs_provider


@dataclass
class Container:
    settings: Settings
    repository: WorkflowRepository
    service: WorkflowService
    input_guard: GuardrailChain[UserInput]
    output_guard: GuardrailChain[ImplementationResult]


def build_container(
    settings: Settings | None = None,
    *,
    llm: LLMClient | None = None,
    docs: DocsProvider | None = None,
    runner: CodeRunner | None = None,
) -> Container:
    s = settings or get_settings()
    configure_logging(s.log_level)

    engine = create_db_engine(s.database_url)
    init_db(engine)
    repo = SqlAlchemyWorkflowRepository(make_session_factory(engine))
    workspace = FileSystemWorkspaceRepository(s.workspace_dir)

    output_guard = build_output_guardrails()
    verifier = VerificationService(
        output_guard, runner or SubprocessSandboxRunner(s.sandbox_timeout_seconds, s.sandbox_memory_mb), workspace
    )
    agents = build_agents(llm or build_llm_client(s), docs or build_docs_provider(s), workspace)
    graph = build_workflow_graph(WorkflowNodes(agents.researcher, agents.coder, agents.reviewer, verifier))
    service = WorkflowService(repo, LangGraphWorkflowEngine(graph), workspace, s.max_review_iterations, s.apply_changes_enabled)
    return Container(s, repo, service, build_input_guardrails(), output_guard)
