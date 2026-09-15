# Chapter 9: small in-memory usage limits

The application now uses a rolling 60-second window. Configure these positive
integer limits in `.env` and restart the server:

```dotenv
EMAILS_PER_MINUTE=20
LOGIN_IP_PER_MINUTE=10
LOGIN_EMAIL_PER_MINUTE=5
```

## Email processing

Authenticated users (including admins) share one quota across single, batch and
stream processing endpoints. One email costs one unit; a five-email batch costs
five units. Charges are reserved atomically before processing or opening the SSE
stream. A batch that exceeds the remaining quota is rejected in full. Rejected
requests do not spend quota or create processing records. Accepted requests still
count if subsequent AI processing fails.

If the configured capacity is smaller than a submitted batch, the response is 422:
split the batch, because waiting would never make it fit. Otherwise exhausted
quota returns 429 with `Retry-After` (seconds) and a JSON error. Login with another
session of the same account does not reset its processing quota.

## Login attempts

Every valid login submission, successful or unsuccessful, is charged against two
independent counters: normalized email and client IP. Both must permit the attempt
before password verification runs. Different email addresses still share the IP
limit; different IPs still share the target email limit. A rejection spends neither
counter. No passwords or tokens are stored in these counters.

Client IP comes from `request.client.host`; the application does not read arbitrary
forwarded headers itself. When deploying behind a proxy, configure the ASGI server
to trust forwarded addresses only from your real proxy.

Registration, history, logout and `/health` are outside this chapter's rate limits.
These limits do not replace the existing concurrency limit or the provider's own
request/token limits.

## Try it in Postman

1. Temporarily set `EMAILS_PER_MINUTE=2` and restart.
2. Login and use the returned Bearer token.
3. Process a batch of two emails. Then call single processing or streaming:
   expect 429 and `Retry-After` before any further processing begins.
4. Wait the indicated time and retry. A different user has their own quota.
5. Submit an incorrect password for the same email five times. The sixth login
   attempt returns 429. Earlier login attempts in that minute also count.
6. Restore your preferred limits and restart.

## Architecture and scope

`application/usage.py` defines the policy, charges, counter contract and exception.
`infrastructure/usage_counter.py` implements the counter with a monotonic clock and
a lock so concurrent admissions cannot exceed the quota. Expired entries are
removed on access. Bootstrap injects one shared instance into HTTP routes.
The HTTP layer identifies the caller, checks usage and maps rejection to 429.

Counters are local to one server process and reset on restart/reload. Use one
worker for these local limits. Multiple workers/replicas need shared storage later.
No database migrations, Redis, new packages or additional AI calls are required.

## Tests

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.basic.test_usage -v
```

On Linux:

```bash
PYTHONPATH=src python -m unittest tests.basic.test_usage -v
```

Tests cover concurrency, window expiry with a fake clock, independent login
counters, weighted batches, user isolation, early SSE rejection and ensuring that
rejected logins never reach password verification. No external AI calls are used.
