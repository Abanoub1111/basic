"""Run with: python -m email_assistant.basic.create_admin"""
import asyncio
from getpass import getpass

from pydantic import EmailStr, TypeAdapter
from email_assistant.basic.domain.users import UserRole
from email_assistant.basic.infrastructure.config import DatabaseSettings
from email_assistant.basic.infrastructure.database import Database
from email_assistant.basic.infrastructure.database.auth_repository import SqlAlchemyAuthRepository
from email_assistant.basic.infrastructure.security import ArgonPasswordHasher


async def main():
    email = str(TypeAdapter(EmailStr).validate_python(input("Admin email: "))).lower()
    password = getpass("Password (12-128 characters): ")
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must contain 12-128 characters")
    if password != getpass("Confirm password: "):
        raise ValueError("Passwords do not match")
    database = Database(DatabaseSettings().database_url.get_secret_value())
    try:
        repository = SqlAlchemyAuthRepository(database.sessions)
        await repository.create_user(email, await ArgonPasswordHasher().hash(password), UserRole.ADMIN)
        print("Admin account created.")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
