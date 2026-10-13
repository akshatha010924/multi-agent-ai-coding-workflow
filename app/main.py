"""FastAPI entrypoint. Run:  uvicorn app.main:create_app --factory"""
from fastapi import FastAPI

from app.container import Container, build_container
from app.controllers.error_handlers import register_error_handlers
from app.controllers.workflow_controller import health_router, router


def create_app(container: Container | None = None) -> FastAPI:
    app = FastAPI(title="Multi-Agent AI Coding Workflow", version="1.0.0")
    app.state.container = container or build_container()
    register_error_handlers(app)
    app.include_router(router)
    app.include_router(health_router)
    return app
