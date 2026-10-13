"""Controller layer: HTTP only. Validates input/output, delegates to the service, contains NO business logic."""
from fastapi import APIRouter, Depends, Query, Request

from app.controllers.schemas import (
    ErrorResponse,
    EventSchema,
    WorkflowCreateRequest,
    WorkflowResponse,
    WorkflowStatusResponse,
)
from app.guardrails.base import GuardrailChain
from app.guardrails.input_guards import UserInput
from app.services.workflow_service import SubmitWorkflowCommand, WorkflowService

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])
health_router = APIRouter(tags=["health"])


def get_service(request: Request) -> WorkflowService:
    return request.app.state.container.service


def get_input_guard(request: Request) -> GuardrailChain[UserInput]:
    return request.app.state.container.input_guard


@router.post(
    "",
    response_model=WorkflowResponse,
    responses={422: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    summary="Run research -> code -> verify -> review for a coding task",
)
def create_workflow(
    body: WorkflowCreateRequest,
    service: WorkflowService = Depends(get_service),
    guard: GuardrailChain[UserInput] = Depends(get_input_guard),
) -> WorkflowResponse:
    guard.enforce(UserInput(task=body.task, context=body.context))  # security validation (raises 422)
    result = service.run(SubmitWorkflowCommand(**body.model_dump()))
    return WorkflowResponse.from_result(result)


@router.get("/{task_id}", response_model=WorkflowStatusResponse, responses={404: {"model": ErrorResponse}})
def get_workflow(task_id: str, service: WorkflowService = Depends(get_service)) -> WorkflowStatusResponse:
    rec = service.get(task_id)
    return WorkflowStatusResponse(
        task_id=rec.task_id,
        workflow_status=rec.status,
        current_step=rec.current_step,
        iteration_count=rec.iteration_count,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        result=WorkflowResponse.from_result(rec.result) if rec.result else None,
    )


@router.get("/{task_id}/events", response_model=list[EventSchema], responses={404: {"model": ErrorResponse}})
def get_workflow_events(task_id: str, service: WorkflowService = Depends(get_service)) -> list[EventSchema]:
    return [EventSchema(message=e.message, created_at=e.created_at) for e in service.events(task_id)]


@router.get("", response_model=list[WorkflowStatusResponse])
def list_workflows(limit: int = Query(20, ge=1, le=100), service: WorkflowService = Depends(get_service)):
    return [
        WorkflowStatusResponse(task_id=r.task_id, workflow_status=r.status, current_step=r.current_step,
                               iteration_count=r.iteration_count, created_at=r.created_at, updated_at=r.updated_at)
        for r in service.recent(limit)
    ]


@health_router.get("/health")
def health(request: Request) -> dict:
    c = request.app.state.container
    return {
        "status": "ok" if c.repository.ping() else "degraded",
        "database": c.repository.ping(),
        "llm_provider": c.settings.llm_provider,
        "llm_model": c.settings.llm_model if c.settings.llm_provider != "mock" else "mock",
        "mcp_enabled": c.settings.mcp_enabled,
    }
