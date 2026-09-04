from fastapi import FastAPI

from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.bootstrap import build_process_email_service
from email_assistant.basic.interfaces.http.routes import create_router


def create_app(
    service: ProcessEmailService | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    if service is None:
        service = build_process_email_service()

    app = FastAPI(
        title="Email Assistant API",
        description="Classify and process incoming emails.",
        version="1.0.0",
    )

    router = create_router(service)
    app.include_router(router)

    return app


app = create_app()