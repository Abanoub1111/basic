from fastapi import APIRouter

from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.interfaces.http.schemas import (
    HealthResponse,
    ProcessEmailRequest,
    ProcessEmailResponse,
)


def create_router(
    service: ProcessEmailService, #DEPENDENCY INJECTION AT HTTP BOUNDARY
) -> APIRouter:
    """Create HTTP routes using the provided application service."""

    router = APIRouter()

    @router.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
    )
    def health() -> HealthResponse:
        """Report whether the API is running."""

        return HealthResponse(status="ok")

    @router.post(
        "/emails/process",
        response_model=ProcessEmailResponse,
        tags=["Emails"],
    )
    def process_email(
        request: ProcessEmailRequest,
    ) -> ProcessEmailResponse:
        """Classify an email and perform the appropriate action."""

        email = request.to_domain()
        result = service.process(email)

        return ProcessEmailResponse.from_result(result)

    return router