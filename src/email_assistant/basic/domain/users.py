from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    role: UserRole
    is_active: bool
