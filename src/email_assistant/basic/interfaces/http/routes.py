from fastapi import APIRouter

from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.interfaces.http.schemas import (
    HealthResponse,
    ProcessEmailRequest,
    ProcessEmailResponse,
    ProcessEmailsBatchRequest,
    ProcessEmailsBatchResponse,
)

def create_router(
    service: ProcessEmailService,  # Dependency injection at the HTTP boundary.
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
    async def process_email(
        request: ProcessEmailRequest,
    ) -> ProcessEmailResponse:
        """Classify an email and perform the appropriate action."""

        email = request.to_domain()
        result = await service.process(email)

        return ProcessEmailResponse.from_result(result)

    @router.post(
        "/emails/process/batch",
        response_model=ProcessEmailsBatchResponse,
        tags=["Emails"],
    )
    async def process_email_batch(
        request: ProcessEmailsBatchRequest,
    ) -> ProcessEmailsBatchResponse:
        """Process a bounded batch of emails concurrently."""

        results = await service.process_many(request.to_domain())

        return ProcessEmailsBatchResponse.from_results(results)

    return router
