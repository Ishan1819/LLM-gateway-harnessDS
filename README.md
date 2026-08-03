# AI Cost Governor

A proxy-based governance layer between a company's developers and the LLM APIs.
It sits in front of OpenAI and Anthropic, attributes every request to a person
and a team, enforces spending caps before a request leaves the building, and
reports on where the money went.

**The client brings their own API keys.** Nothing in this product pays for
inference — the organization's own OpenAI/Anthropic keys are stored encrypted
and used to forward requests, so their provider bill works exactly as it does
today. This product adds the tracking and control layer on top.

---

## Contents

- [Plans](#plans)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Local setup](#local-setup)
- [Connecting your code](#connecting-your-code)
- [Deployment](#deployment)
- [API reference](#api-reference)
- [Pricing table](#pricing-table)
- [Security notes](#security-notes)
- [Screenshots](#screenshots)

---

## Plans

Three tiers, defined once in `backend/app/utils/plans.py` and enforced by the
API — not just hidden in the UI.

| | Free | Standard — $49/mo | Premium — $199/mo |
|---|---|---|---|
| Tracked developers | 5 | 50 | Unlimited |
| Usage history | 7 days | 90 days | Unlimited |
| Spend dashboard | ✓ | ✓ | ✓ |
| Per-user caps | ✓ | ✓ | ✓ |
| Teams & team caps | — | ✓ | ✓ |
| Budget alerts (80% / 90%) | — | ✓ | ✓ |
| Savings report & projections | — | ✓ | ✓ |
| **Cost Optimizer** | — | — | ✓ |
| Editable pricing table | — | — | ✓ |

**Enforcement is server-side.** A gated endpoint returns `402 Payment Required`
with the tier that would unlock it, so the dashboard can render a specific
upgrade prompt. Locked pages stay visible and explain the feature rather than
disappearing — the lock doubles as the pitch.

**Self-serve signup is Free-only.** Requesting a paid tier at registration is
rejected by the API; paid plans are sales-assisted. The seeded demo org runs on
**Premium** so the whole product is visible in a walkthrough — flip
`plan=plans.PREMIUM` in `seed_data.py` to demo the gates instead.

### The Cost Optimizer (Premium)

The one feature that pays for itself. It reads usage the proxy already recorded
— never prompt bodies — and reports, in dollars:

- **Model right-sizing.** For each model, the requests below *its own median*
  context size are candidates for one tier down. Measuring against the model's
  own usage means a team with genuinely large contexts isn't told to downgrade
  everything.
- **Repeated prompts.** The same prompt sent 3+ times by one person — usually a
  retry loop. Everything after the first run is what caching could absorb.
- **Per-team prompt efficiency.** Context size, output length and repeat rate
  per team, each with specific guidance drawn from that team's own traffic.

Findings are **estimates, presented as such** — a model downgrade only holds if
quality holds, and the UI says so rather than implying a one-click saving.

---

## How it works

1. A company signs up and gets an organization with a unique slug.
2. An admin pastes in **their own** OpenAI and/or Anthropic API keys. They are
   encrypted with Fernet before they touch the database.
3. The admin creates teams, adds users, and sets daily/monthly caps.
4. Each user gets a unique **proxy API key** (`acg-…`).
5. Developers change one thing in their code — the `base_url` — and point it at
   `https://<your-host>/v1/org/<slug>`.
6. Every request is authenticated, checked against the caps, forwarded upstream
   with the org's real key, and logged with token counts and computed cost.

If a cap is reached, the proxy returns **HTTP 429** with
`Budget limit reached. Contact your admin.` and the request never reaches the
provider — so the block actually prevents spend rather than reporting on it
afterwards.

---

## Architecture

```
    Developer's code                  AI Cost Governor                Provider
 ┌──────────────────┐          ┌────────────────────────────┐    ┌──────────────┐
 │ OpenAI(          │          │  1. authenticate proxy key │    │  OpenAI API  │
 │   base_url=proxy │  HTTPS   │  2. check user/team/org cap │    │      or      │
 │   api_key=acg-…  │ ───────► │  3. decrypt org key         ├───►│ Anthropic API│
 │ )                │          │  4. forward request         │    └──────────────┘
 └──────────────────┘          │  5. log tokens + cost       │           │
          ▲                    │  6. fire threshold alerts   │◄──────────┘
          └────────────────────┤                             │
             response, byte-   └──────────────┬──────────────┘
             identical                        │
                                    ┌─────────┴─────────┐
                                    │  Postgres  Redis  │
                                    │  (usage)  (limits)│
                                    └─────────┬─────────┘
                                              │
                                     ┌────────┴────────┐
                                     │ React dashboard │
                                     └─────────────────┘
```

**Provider routing is by model name.** `claude-*` goes to Anthropic, everything
else to OpenAI — so a single endpoint serves both, and a team can switch models
without switching URLs.

### Repository layout

```
ai-cost-governor/
├── backend/                  FastAPI service (proxy + admin API)
│   ├── app/
│   │   ├── main.py           App wiring, CORS, routers
│   │   ├── config.py         Environment configuration
│   │   ├── database.py       Engine, session, Base
│   │   ├── models/           Organization, Team, User, UsageLog, Alert
│   │   ├── routes/           proxy, auth, admin, settings
│   │   ├── services/         proxy, usage, cap, alert, encryption, auth
│   │   ├── middleware/       Redis rate limiter
│   │   └── utils/pricing.py  Model rate card  ← edit prices here
│   ├── seed_data.py          Demo org with 30 days of usage
│   ├── requirements.txt
│   └── render.yaml           One-click Render deploy
└── frontend/                 React + Vite + Tailwind + Recharts
    ├── src/components/       Sidebar, charts, tables, cap editor
    ├── src/pages/            Login, Dashboard, Teams, Users, Caps,
    │                         Alerts, Savings, Settings
    ├── src/services/api.js   Typed API client
    └── vercel.json
```

---

## Local setup

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Generate the encryption key and paste it into .env:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

python seed_data.py          # demo org with 30 days of usage
uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs>

### Frontend

```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open <http://localhost:5173> and sign in with the demo account:

```
admin@test.com / demo123
```

### What the seed data contains

- **Demo Organization** with 20 users across Backend (8), Frontend (5) and Data Science (7)
- 30 days of usage — ~11,600 requests, weekday/weekend rhythm, per-team model mixes
- Data Science on heavy GPT-4 Turbo and Claude Opus; Frontend mostly on GPT-4o-mini
- Three users with a visible waste pattern: high volume, short repetitive prompts
- Caps derived from each user's **month-end run rate**, so several users sit near
  their cap and a few are on pace to blow through it — regardless of which day of
  the month you run the seed
- A matching alert history

Re-run `python seed_data.py` any time to reset it, or `--keep` to seed only when
the demo org is missing.

---

## Connecting your code

The only change is `base_url`. Everything else — models, parameters, streaming,
tool use — is passed through untouched.

**OpenAI SDK**

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://your-app.onrender.com/v1/org/demo",
    api_key="acg-…",                       # the user's proxy key
)

client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)
```

**Anthropic SDK**

```python
from anthropic import Anthropic

client = Anthropic(
    base_url="https://your-app.onrender.com/v1/org/demo",
    api_key="acg-…",
)

client.messages.create(
    model="claude-opus-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
```

Both `Authorization: Bearer <key>` and `x-api-key: <key>` are accepted, so either
SDK's default auth style works.

**Streaming works.** SSE is passed through chunk by chunk while usage is
accumulated from the stream and recorded when it closes. For OpenAI, set
`stream_options={"include_usage": True}` so the provider emits the usage frame
the cost engine needs — without it, a streamed request records zero tokens.

---

## Deployment

No Docker required.

### 1. Database

Either Render Postgres (provisioned by `render.yaml`) or a Supabase free project.
Copy the connection string; `postgres://` URLs are normalized automatically.

### 2. Backend on Render

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point at the repo. `backend/render.yaml`
   provisions the web service and the database.
3. Set the two secrets Render can't generate for you:
   - `ENCRYPTION_KEY` — the Fernet key you generated above
   - `CORS_ORIGINS` — your Vercel domain, e.g. `https://your-app.vercel.app`
   - `REDIS_URL` — optional, from Upstash
4. After the first deploy, seed the demo data from the Render shell if you want it:
   `python seed_data.py`

Tables are created automatically on startup.

### 3. Redis on Upstash (optional)

Create a free Redis database, copy the `rediss://` URL into `REDIS_URL`. It backs
per-key rate limiting (120 requests/minute by default). **If `REDIS_URL` is
unset, rate limiting is skipped rather than failing requests** — so the service
runs fine before Upstash is wired up.

### 4. Frontend on Vercel

1. **New Project** → import the repo → set **Root Directory** to `frontend`.
2. Add environment variable `VITE_API_BASE_URL` = your Render URL
   (e.g. `https://ai-cost-governor-api.onrender.com`, no trailing slash).
3. Deploy. `vercel.json` handles the SPA rewrite and build settings.

Then go back and make sure your Vercel domain is in the backend's `CORS_ORIGINS`.
Any `*.vercel.app` origin is allowed by default, so preview deploys work without
extra configuration.

---

## API reference

### Proxy

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/org/{slug}/chat/completions` | OpenAI-compatible. Routes `claude-*` models to Anthropic. |
| `POST` | `/v1/org/{slug}/messages` | Anthropic Messages API compatible. |
| `GET` | `/v1/org/{slug}/models` | Model list, for SDKs that probe on startup. |

### Admin — all require `Authorization: Bearer <JWT>`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` | Create org + admin, returns a JWT |
| `POST` | `/api/auth/login` | Admin login |
| `GET` | `/api/auth/me` | Current session |
| `GET` | `/api/admin/dashboard` | Overview stats, trend, teams, models |
| `GET` | `/api/admin/usage?group_by=user\|team\|model&period=day\|week\|month` | Usage analytics |
| `GET` | `/api/admin/users` | Users with usage and cap utilization |
| `POST` | `/api/admin/users` | Create a user, generates a proxy key |
| `DELETE` | `/api/admin/users/{id}` | Remove a user |
| `GET` | `/api/admin/teams` | Teams with usage |
| `POST` | `/api/admin/teams` | Create a team |
| `PUT` | `/api/admin/caps/{user_id}` | Update user caps / active flag |
| `PUT` | `/api/admin/caps/team/{team_id}` | Update team caps |
| `PUT` | `/api/admin/caps/bulk` | Bulk cap / activation update |
| `GET` | `/api/admin/alerts` | Alert history |
| `PUT` | `/api/admin/alerts/{id}/read` | Mark an alert read |
| `GET` | `/api/admin/savings` | Savings report data |
| `GET` | `/api/admin/settings/keys` | Masked provider keys + proxy URL |
| `PUT` | `/api/admin/settings/keys` | Update provider keys and budget |
| `GET` | `/api/admin/settings/pricing` | Active rate card |

---

## Pricing table

Costs are computed from `backend/app/utils/pricing.py` — a plain dict of
USD-per-million-token rates. Nothing else hardcodes a price, so updating a rate
is a one-line change.

| Model | Input | Output |
|---|---|---|
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4-turbo | $10.00 | $30.00 |
| claude-opus-5 | $5.00 | $25.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4-5 | $1.00 | $5.00 |
| claude-fable-5 | $10.00 | $50.00 |

> **Note on the Anthropic rates.** The original spec listed Claude Opus at
> $15/$75 and Claude Haiku at $0.25/$1.25. Those are not the current rates —
> Claude Opus 5 is **$5/$25** and Claude Haiku 4.5 is **$1/$5** per million
> tokens. The table above uses the correct current figures, since costing against
> stale rates would misreport every number on the dashboard. The bare names
> `claude-opus` and `claude-haiku` were also replaced with real model IDs
> (`claude-opus-5`, `claude-haiku-4-5`) so requests actually route. Change any of
> it in `pricing.py` if you need different values.

Unknown models fall back to a mid-tier rate rather than being recorded as free,
and dated snapshots (`gpt-4o-2024-11-20`) match on prefix.

Anthropic cache tokens (`cache_creation_input_tokens`, `cache_read_input_tokens`)
are counted as input, so caching-heavy workloads aren't under-reported.

---

## Security notes

- **Provider keys are encrypted at rest** with Fernet and are never returned by
  any endpoint — the settings page shows a mask (`sk-…a1b2`).
- **Passwords** are bcrypt-hashed. Login returns the same error for an unknown
  email and a wrong password, so the endpoint doesn't confirm which accounts exist.
- **Prompt content is not stored.** Only the first 100 characters are kept, as a
  request label for the usage log.
- **Proxy keys** are 32 bytes of `secrets.token_urlsafe`, unique per user, and
  scoped to one organization.
- **Cap checks run before forwarding**, so an over-budget request costs nothing.
- Rotating `ENCRYPTION_KEY` makes previously stored provider keys unreadable —
  the settings page will show `unreadable — re-enter key` rather than failing
  silently.

---

## Screenshots

Add images to a `docs/` folder and reference them here:

| View | Description |
|---|---|
| Overview | Spend today/month/projected, 30-day trend, spend by team and model, top spenders |
| Teams | Per-team bar chart and budget table with pace against cap |
| Users | Sortable table: requests, tokens, spend, cap utilization, status |
| Cap management | Single and bulk cap editing, enable/disable accounts |
| Alerts | 80% / 90% / limit-reached history with filters |
| Savings report | Budget vs projection, month-over-month, spend by model, flagged accounts |
| Settings | Encrypted key management and copy-paste SDK snippets |
