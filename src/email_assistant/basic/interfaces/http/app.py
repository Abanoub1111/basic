from collections.abc import Callable
from typing import AsyncContextManager

from fastapi import FastAPI

from email_assistant.basic.application.services import (
    EmailHistoryService,
    ProcessEmailService,
)
from email_assistant.basic.interfaces.http.routes import create_router


def create_app(
    service: ProcessEmailService,
    history_service: EmailHistoryService,
    lifespan: Callable[[FastAPI], AsyncContextManager[None]] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Email Assistant API",
        description="Classify and process incoming emails.",
        version="1.0.0",
        lifespan=lifespan,
    )

    router = create_router(service, history_service)
    app.include_router(router)

    return app
