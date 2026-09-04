from fastapi import FastAPI

from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.interfaces.http.routes import create_router


def create_app(service: ProcessEmailService) -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Email Assistant API",
        description="Classify and process incoming emails.",
        version="1.0.0",
    )

    router = create_router(service)
    app.include_router(router)

    return app
