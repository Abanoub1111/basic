from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from email_assistant.basic.application.services import (
    EmailHistoryNotFoundError,
    EmailHistoryService,
    ProcessEmailService,
)
from email_assistant.basic.interfaces.http.schemas import (
    EmailHistoryListResponse,
    EmailHistoryResponse,
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
    history_service: EmailHistoryService,
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

    @router.get(
        "/emails/history",
        response_model=EmailHistoryListResponse,
        tags=["Email history"],
    )
    async def list_email_history(
        skip: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> EmailHistoryListResponse:
        """Return stored processing operations, newest first."""

        records = await history_service.list(skip=skip, limit=limit)
        return EmailHistoryListResponse(
            items=[EmailHistoryResponse.from_record(record) for record in records],
            skip=skip,
            limit=limit,
        )

    @router.get(
        "/emails/history/{record_id}",
        response_model=EmailHistoryResponse,
        tags=["Email history"],
    )
    async def get_email_history(record_id: UUID) -> EmailHistoryResponse:
        """Return one stored processing operation."""

        try:
            record = await history_service.get(record_id)
        except EmailHistoryNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email processing record was not found.",
            ) from error

        return EmailHistoryResponse.from_record(record)

    @router.delete(
        "/emails/history/{record_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["Email history"],
    )
    async def delete_email_history(record_id: UUID) -> Response:
        """Delete one stored processing operation."""

        try:
            await history_service.delete(record_id)
        except EmailHistoryNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email processing record was not found.",
            ) from error

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
