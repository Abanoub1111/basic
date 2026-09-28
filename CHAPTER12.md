# Chapter 12: run the email assistant with Docker

Docker now runs both FastAPI and PostgreSQL. Groq still hosts the AI model;
you do not need a GPU or model files on your computer.

## Start the application

Start Docker Desktop, then open a terminal in this project folder.
If you do not already have `.env`, copy `.env.example` to `.env`.
Keep your existing `.env` if you have one.

Set these values in `.env`:

```dotenv
GROQ_API_KEY=your-real-groq-key
JWT_SECRET=your-random-secret-at-least-32-characters
```

You can generate a JWT secret using `python -c "import secrets; print(secrets.token_hex(32))"`.
Keep the same secret across restarts so existing tokens remain verifiable.

Build the application image and start both services:

```shell
docker compose up -d --build --wait
```

PostgreSQL becomes healthy first. The application then applies Alembic migrations
and starts Uvicorn. If migration fails, the application does not start; inspect its
logs. Your existing database volume is reused, not replaced.

Open http://localhost:8000/docs for API documentation, or
http://localhost:8000/health for the application health endpoint.
The health endpoint confirms HTTP responsiveness; it is not a continuous database
or Groq connectivity check. Database connectivity is checked at application startup.

## What each file does

| File | Purpose |
| --- | --- |
| `Dockerfile` | Builds a Python 3.12 slim image, installs runtime dependencies, copies code and migrations, and runs as a non-root user |
| `.dockerignore` | Restricts the build context to runtime inputs, excluding secrets, test files, documents, environments, and caches |
| `compose.yaml` | Runs the API and database on Compose's shared default network, with port mappings, health checks and restart policies |
| `.env` | Supplies API keys and application settings at runtime; it is never copied into the image |

Dependencies are installed before application code is copied, allowing Docker to
reuse the dependency layer when only code changes. Pip's download cache is not
kept in the final image. A single build stage keeps this small project simple;
there are no GPU packages, build tools, or test dependencies explicitly installed.

## Database addresses

| Where the application runs | Database host and port |
| --- | --- |
| Directly on your PC | `localhost:5433` |
| Inside the application container | `postgres:5432` |

Compose overrides `DATABASE_URL` for the application container, so a host-based
value in `.env` does not break container networking. This does not edit `.env` or
change the `TEST_DATABASE_URL` used by your test runner.

PostgreSQL stores data in the existing `email-assistant-postgres` named volume.
The Compose database credentials are for local development. Changing those values
does not automatically update credentials inside an already-initialized volume.

## Everyday commands

```shell
# Show health and running state
docker compose ps

# Follow application logs (Ctrl+C stops following, not the application)
docker compose logs -f app

# Rebuild and restart after changing code
docker compose up -d --build --wait

# Stop and remove containers, retaining the database volume
docker compose down
```

Avoid `docker compose down -v` unless you intend to delete the database volume.
Keep using `docker compose up -d --wait postgres` when you only need PostgreSQL
for local tests. The existing `python run_tests.py` and `python run_tests.py --all`
commands run tests on your host; tests are not included in the application image.

## Scope and deployment choices

Ports are published only on `127.0.0.1`, so this is a local setup, not a public
internet deployment. No image is pushed to a registry automatically. Before public
hosting, choose a deployment target, configure HTTPS and managed secrets/database
credentials, and publish an appropriately tagged image.

Use one application process/container for now: the rate limiter and classification
cache are in-memory and are not shared between workers or replicas. Migrations run
on application startup for this single-instance setup. Multiple replicas should use
a separate migration job and shared state for rate limits.

The chapter's alternative VM/serverless deployments, GPU setup, advanced network
drivers, multi-stage builds, and development bind mounts are intentionally not
added: they are optional and are not necessary for this application to run locally
as containers.
