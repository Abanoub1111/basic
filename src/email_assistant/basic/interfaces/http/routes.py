from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.interfaces.http.schemas import (
    HealthResponse,
    ProcessEmailRequest,
    ProcessEmailResponse,
    ProcessEmailsBatchRequest,
    ProcessEmailsBatchResponse,
)
from email_assistant.basic.interfaces.http.streaming import (
    stream_process_email_events,
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

    @router.post(
        "/emails/process/stream",
        response_class=StreamingResponse,
        responses={
            200: {
                "content": {"text/event-stream": {}},
                "description": "Real-time email processing events.",
            }
        },
        tags=["Emails"],
    )
    async def process_email_stream(
        body: ProcessEmailRequest,
        request: Request,
    ) -> StreamingResponse:
        """Stream processing progress and the drafted reply over SSE."""

        event_stream = stream_process_email_events(
            service,
            body.to_domain(),
            request.is_disconnected,
        )

        return StreamingResponse(
            event_stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router
