from collections.abc import Callable
from typing import AsyncContextManager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from email_assistant.basic.application.auth import AuthService, AuthenticationError, AccountExistsError
from email_assistant.basic.interfaces.http.auth import AuthDependencies, create_auth_router

from email_assistant.basic.application.services import (
    EmailHistoryService,
    ProcessEmailService,
)
from email_assistant.basic.interfaces.http.routes import create_router


def create_app(
    service: ProcessEmailService,
    history_service: EmailHistoryService,
    auth_service: AuthService,
    lifespan: Callable[[FastAPI], AsyncContextManager[None]] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Email Assistant API",
        description="Classify and process incoming emails.",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.exception_handler(AuthenticationError)
    async def authentication_error(request, error):
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired credentials"},
                            headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(AccountExistsError)
    async def account_exists(request, error):
        return JSONResponse(status_code=409, content={"detail": "Account already registered"})

    auth = AuthDependencies(auth_service)
    app.include_router(create_auth_router(auth))
    router = create_router(service, history_service, auth)
    app.include_router(router)

    return app
