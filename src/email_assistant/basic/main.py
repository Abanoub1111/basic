from contextlib import asynccontextmanager

from fastapi import FastAPI

from email_assistant.basic.bootstrap import build_application
from email_assistant.basic.interfaces.http.app import create_app


container = build_application()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Check and release infrastructure owned by the application."""

    await container.database.check_connection()
    yield
    await container.database.dispose()


app = create_app(
    container.process_email_service,
    container.email_history_service,
    lifespan=lifespan,
)
