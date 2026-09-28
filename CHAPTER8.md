# Chapter 8: accounts and history ownership

Authentication uses email/password login, Argon2 password hashes and signed JWTs.
Each token identifies a database session. Logout revokes that session. Tokens expire
after 30 minutes by default; log in again to get a new one.

## Setup

Run from the project root:

```powershell
python -m pip install -r requirements.txt
docker compose up -d
python -m alembic upgrade head
```

Set `JWT_SECRET` in your ignored `.env` to a random value of at least 32 characters.
For this local checkout it has already been generated. To generate one on another
machine, run `python -c "import secrets; print(secrets.token_urlsafe(48))"` and copy
the output to `.env`. Keep it private and stable across restarts.

```powershell
python -m uvicorn --app-dir src email_assistant.basic.main:app --reload
```

## Postman workflow

1. POST `/auth/register`, with JSON:

```json
{"email": "alice@example.com", "password": "a-long-test-password"}
```

2. POST `/auth/login` with the same JSON. Copy `access_token`.
3. In Postman choose Authorization > Bearer Token and paste the token.
4. GET `/users/me` to see the current account.
5. Use the existing process, batch, stream and history endpoints with that token.
6. POST `/auth/logout` with the token. Reusing it now returns 401.

Public registration always creates a USER. Password spaces are preserved.
USER can process messages and read/delete only their own history. ADMIN can read
and delete everyone's history, including pre-authentication records with no owner.
Unknown and other users' record IDs both return 404. `/health` stays public.
The `author` in an email body is not the owner: ownership comes from the login.

## Create an administrator locally

```powershell
$env:PYTHONPATH='src'
python -m email_assistant.basic.create_admin
```

Enter a new email and a password when prompted. The password is hidden. Login
through `/auth/login` afterward. There is no public role-management endpoint.

## Architecture

- Domain: user identity and role.
- Application: AuthService and persistence/security contracts; history access rules.
- Infrastructure: Argon2/JWT implementations and SQLAlchemy repositories.
- HTTP: credentials, Bearer dependency and safe response/error mapping.
- Bootstrap: injects the concrete implementations into the services.

## Tests

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

To include real PostgreSQL authentication/ownership tests after migrating:

```powershell
$env:RUN_DATABASE_TESTS='1'
python -m unittest tests.basic.test_auth -v
```

The integration test creates random test accounts and removes only their data.
It uses fake AI providers, so it does not spend model credits or send email.

This is the local learning implementation. Before exposing it publicly, add login
rate limiting and HTTPS. Password reset, external identity providers and refresh
tokens are not part of this chapter implementation.
