# AI Cost Governor — Backend

FastAPI service providing the LLM proxy and the admin API.
See the [root README](../README.md) for the full picture.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste into ENCRYPTION_KEY in .env

python seed_data.py
uvicorn app.main:app --reload --port 8000
```

Interactive docs at <http://localhost:8000/docs>.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes in prod | Postgres URL. `postgres://` is normalized. Defaults to local SQLite. |
| `JWT_SECRET` | yes | Signs admin dashboard tokens. |
| `ENCRYPTION_KEY` | yes | Fernet key for provider API keys at rest. |
| `REDIS_URL` | no | Upstash Redis for rate limiting. Skipped when unset. |
| `CORS_ORIGINS` | yes in prod | Comma-separated allowed origins. `*.vercel.app` is always allowed. |
| `OPENAI_BASE_URL` | no | Override upstream OpenAI endpoint. |
| `ANTHROPIC_BASE_URL` | no | Override upstream Anthropic endpoint. |
| `ALERT_THRESHOLDS` | no | Cap-utilization alert points. Default `0.8,0.9`. |

## Where things live

| Concern | File |
|---|---|
| Model prices | `app/utils/pricing.py` |
| Provider routing (which API a model goes to) | `app/utils/pricing.py` → `detect_provider` |
| Cap enforcement | `app/services/cap_service.py` |
| Alert thresholds and debouncing | `app/services/alert_service.py` |
| Upstream forwarding, streaming, usage extraction | `app/services/proxy_service.py` |
| Dashboard aggregations | `app/services/usage_service.py` |
| Key encryption | `app/services/encryption_service.py` |

## Notes on behaviour

- **Cap checks run before forwarding.** A blocked request returns HTTP 429 and
  never reaches the provider, so it costs nothing.
- **Usage is written on a separate DB session** so a streamed response still gets
  recorded after the request context ends. A failure to record is logged, never
  surfaced to the caller — accounting must not break a working response.
- **Streaming**: SSE frames are relayed as they arrive while usage is accumulated
  from the stream. OpenAI only emits usage when the caller sets
  `stream_options.include_usage`; without it a streamed request records zero tokens.
- **Alerts are debounced** to one per user, per type, per day, so an over-budget
  user doesn't generate an alert per request.
- **Rate limiting degrades to a no-op** if Redis is unreachable, rather than
  failing requests.
