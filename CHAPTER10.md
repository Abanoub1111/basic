# Chapter 10: classification caching only

This implements the chapter's exact-match (keyword) caching concept, TTL, and
least-recently-used (LRU) eviction. No semantic/vector cache, provider prompt cache,
fine-tuning, quantization, or new batch API is added.

## Workflow

1. The HTTP route authenticates the user and charges the existing usage quota.
2. The application creates a fresh history record.
3. It checks the classification cache using the user ID and all four email fields.
4. On a hit, reuse the classification and reasoning. On a miss, call the classifier
   and cache its successful result.
5. Run the response workflow normally when required, then finish the history record.

Single, batch, and streaming requests all share this path. Only classification is
cached: replies and email/calendar tool actions are not. Repeating a request is NOT
idempotent and can execute tools again. Every accepted email still consumes quota.
Classification failures are not cached. A successful classification remains cached
even if a later response operation fails.

## Settings

Defaults work without editing `.env`. To customize, add:

```dotenv
CLASSIFICATION_CACHE_ENABLED=true
CLASSIFICATION_CACHE_TTL_SECONDS=300
CLASSIFICATION_CACHE_MAX_ENTRIES=1000
```

Restart the server after changing settings. Set `CLASSIFICATION_CACHE_ENABLED=false`
to disable caching. TTL starts when a result is stored; hits do not extend it.
Expired entries are removed on access or insertion. At capacity, the least recently
used entry is evicted. Capacity is shared across users, but their results are isolated.

## Onion architecture

- Application: `ClassificationCache` is a port in `application/ports.py`;
  `ProcessEmailService` decides when to read/write it.
- Infrastructure: `InMemoryClassificationCache` implements hashing, TTL and LRU.
- Composition root: `bootstrap.py` injects one cache for the application lifetime.
- Domain and HTTP response schemas are unchanged.

Keys hash the user ID, author, recipient, subject and thread after existing request
validation. No semantic matching or additional whitespace/case normalization occurs.
Logs report only HIT/MISS, not email content or user identifiers. Hashing keys is not
encryption: cached reasoning may contain private information and stays in process memory.

The cache is intentionally process-local and bounded. Restarting clears it; multiple
workers do not share results. Classifier model/prompts are fixed for an app instance;
restart after changing them so old results cannot be reused. A future shared cache
would also need a model/prompt version in its keys.

Simultaneous identical cold requests can each call the model before either stores a
result. Request coalescing is deliberately not added to this small implementation.
Deleting history does not clear cached classifications; these expire independently.
No database migration, Redis service or extra dependency is required.

## Try in Postman

Start the API as usual:

```powershell
python -m uvicorn --app-dir src email_assistant.basic.main:app --reload
```

Log in, then send this twice in sequence to
`POST http://127.0.0.1:8000/emails/process` with your Bearer token:

```json
{
  "author": "newsletter@example.com",
  "to": "assistant@example.com",
  "subject": "Weekly newsletter",
  "email_thread": "This is an automated newsletter. No response is needed."
}
```

The terminal reports `Classification cache MISS`, then `Classification cache HIT`.
Each response has a different history record ID. Responses keep their existing shape;
there is no HTTP cache header because the entire response is not cached.

Change one field or use another user's account: expect a miss. For an expiry test,
set TTL to 5 seconds, restart, send once, wait more than 5 seconds and repeat.
The classifier runs again. Timing alone is not a reliable cache test, especially
when an email requires the uncached response agent.

Run automated checks without calling Groq or a live database:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.basic.test_caching -v
python -m unittest discover -s tests -q
```

The optional existing database integration test remains opt-in.
