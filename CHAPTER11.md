# Chapter 11: simple testing with pytest

This branch replaces the previous `unittest` suite with pytest functions.
Application code is unchanged. Tests are kept under one `tests/` directory;
each test arranges inputs, runs an operation, then asserts the result.

## Install and run

Use your project's Python environment (Python 3.10 or newer).
From the project root on either Windows or Linux:

```shell
python -m pip install -r requirements-test.txt
python -m pytest -q
```

Use `python3` instead of `python` if that is your Linux command.
`pytest.ini` adds `src` to the import path, so no PYTHONPATH command is needed.
Do not use `unittest discover` for these new pytest functions.

```shell
python -m pytest tests/test_cache.py -v
python -m pytest --cov=email_assistant --cov-report=term-missing
```

The default suite needs no database or API key. External tests are collected but
skipped unless explicitly enabled. Failures are shown with the failing assertion;
logs from deliberately simulated provider failures stay captured on successful runs.

## What each file teaches

| File | Scope and purpose |
| --- | --- |
| `conftest.py` | Function-scoped fixtures, dependency injection, test-client setup/cleanup, opt-in flags |
| `fakes.py` | One in-memory repository with owner filtering; fresh for each test |
| `test_processing.py` | Unit tests for decisions, failures, cancellation, caching, batch order/concurrency |
| `test_cache.py` | Parameterized exact-match keys, TTL boundaries, LRU capacity, invalid settings |
| `test_validation.py` | Valid/invalid/boundary inputs, token validation, registration and calendar behavior |
| `test_usage.py` | Weighted limits, expiration, concurrency and atomic login quotas |
| `test_ai_adapters.py` | Patching the model boundary while testing real adapter validation and graph execution |
| `test_api.py` | Vertical/API workflows, history isolation, streaming, shared cache/quota, authentication |
| `test_database.py` | Real repository integration plus registration-to-logout workflow with stubbed AI |
| `test_ai_behavior.py` | Opt-in live classifier minimum functionality, invariance and directional expectation tests |

The `AsyncMock` fixtures supply fixed AI outputs and record awaited calls (mock/spy
behavior). Fake clocks avoid sleeping for cache and rate-limit expiration. Async
events coordinate the concurrency test; timeouts prevent it from hanging.

## Optional PostgreSQL tests

Use a dedicated test database. The following assumes the repository's Compose
settings and Docker Compose are available:

```shell
docker compose up -d --wait postgres
docker compose exec postgres createdb -U email_assistant email_assistant_test
```

Create the database once; skip `createdb` if it already exists. Then set the URL
and apply migrations before testing.

PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://email_assistant:email_assistant@localhost:5433/email_assistant_test"
$env:DATABASE_URL = $env:TEST_DATABASE_URL
python -m alembic upgrade head
python -m pytest --run-database -m database -v
```

Bash:

```bash
export TEST_DATABASE_URL="postgresql+asyncpg://email_assistant:email_assistant@localhost:5433/email_assistant_test"
DATABASE_URL="$TEST_DATABASE_URL" python3 -m alembic upgrade head
python3 -m pytest --run-database -m database -v
```

The fixture creates unique test accounts and deletes only their records and sessions
in teardown. Database connections and HTTP clients are closed. An enabled test fails
if configuration or database access is broken; it does not silently skip.
The old `RUN_DATABASE_TESTS` flag is replaced by `--run-database`.

## Optional live AI evaluations

Set `GROQ_API_KEY` in your terminal environment, then run:

```shell
python -m pytest --run-ai -m ai -v
```

The live-test fixture reads the terminal environment, not `.env`, so export the key
explicitly before running. Do not commit API keys to the repository.

These make paid network calls to the real classifier (nine calls on a fully passing
run). They check three Chapter 11 techniques:

- Minimum functionality: clear marketing, status-update and reply-request examples.
- Invariance: capitalization or surrounding whitespace should not change a decision.
- Directional expectation: adding a direct request changes notification into response.

The model is probabilistic. An assertion failure may reveal a prompt/model regression;
inspect it instead of automatically retrying until it passes. Reuse the same cases
when changing prompts or models. Three basic examples are a starting evaluation set,
not a reliable estimate of real-world accuracy. Extend it with representative emails
and agreed quality thresholds before using it as a release gate.

## Deliberately small scope

This applies the chapter's core techniques to an email assistant. RAG chunking,
vector retrieval precision/recall, large stress suites, LLM-as-judge evaluation,
bias/adversarial datasets and CI automation are not implemented here. Live evaluations
currently measure classification, not generated reply quality. API workflows use
stubbed AI; the database workflow is not a full live-provider E2E test.

Coverage reports show executed code, not proof of correctness or AI quality.
There is no arbitrary coverage threshold. The old suite remains in Git history;
this intentionally smaller suite does not preserve every old assertion.
