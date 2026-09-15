from fastapi import APIRouter, Depends, HTTPException, Request
from email_assistant.basic.application.usage import UsageLimits
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from email_assistant.basic.application.auth import AuthService
from email_assistant.basic.domain.users import User


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(LoginRequest):
    password: str = Field(min_length=12, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthDependencies:
    """Translate HTTP credentials into a verified application user."""

    def __init__(self, service: AuthService):
        self.service = service

    async def token(self, credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False))) -> str:
        if credentials is None:
            raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
        return credentials.credentials

    def current_user_dependency(self):
        async def current_user(token: str = Depends(self.token)) -> User:
            return await self.service.current_user(token)
        return current_user


def create_auth_router(auth: AuthDependencies, usage: UsageLimits) -> APIRouter:
    router = APIRouter(tags=["Authentication"])

    @router.post("/auth/register", response_model=User, status_code=201)
    async def register(body: RegisterRequest):
        return await auth.service.register(str(body.email), body.password)

    @router.post("/auth/login", response_model=TokenResponse)
    async def login(body: LoginRequest, request: Request):
        usage.login(request.client.host if request.client else "unknown", str(body.email))
        return TokenResponse(access_token=await auth.service.login(str(body.email), body.password))

    @router.post("/auth/logout", status_code=204)
    async def logout(token: str = Depends(auth.token)) -> None:
        await auth.service.logout(token)

    @router.get("/users/me", response_model=User)
    async def me(user: User = Depends(auth.current_user_dependency())):
        return user

    return router
