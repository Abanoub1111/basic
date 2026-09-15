from collections.abc import Callable
from typing import AsyncContextManager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from email_assistant.basic.application.usage import UsageLimits, RateLimitExceeded
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
    usage: UsageLimits,
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

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_error(request, error: RateLimitExceeded):
        return JSONResponse(status_code=429,
                            content={"detail": "Rate limit exceeded. Please try again later.",
                                     "retry_after_seconds": error.retry_after},
                            headers={"Retry-After": str(error.retry_after)})

    auth = AuthDependencies(auth_service)
    app.include_router(create_auth_router(auth, usage))
    router = create_router(service, history_service, auth, usage)
    app.include_router(router)

    return app
