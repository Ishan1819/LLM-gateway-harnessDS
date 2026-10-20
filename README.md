# AI Cost Governor — a distributed LLM governance gateway

Developers in a company ("employees") send
their LLM requests through a gateway. The gateway tracks every request,
enforces per-user, per-team and per-org spending caps **across a cluster of
replicas**, and reports spend on an admin dashboard.

It runs as **7 containerised services on Kubernetes** (Docker Desktop). The
real OpenAI/Anthropic APIs are replaced by a **mock LLM service**, so no API
keys are needed and nothing is ever billed.

* Distributed design → [docs/DISTRIBUTED_SYSTEMS.md](docs/DISTRIBUTED_SYSTEMS.md)
* Step-by-step demo → [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)

```
frontend (nginx) ─► gateway ×2-6 (HPA) ──RPC──► mock-llm ×2
                       │  Redis Stream / locks / leader lease / heartbeats
                       ▼
             usage-worker ×2 (consumer group)   alert-worker ×2 (1 elected leader)
                       └──────────► Postgres (StatefulSet) ◄──────────┘
```

| Concept (unit) | Where |
|---|---|
| Microservices, middleware, containers (I) | `backend/`, `services/mock-llm/`, `frontend/`, Dockerfiles |
| RPC with timeout + retry (II) | `backend/app/services/proxy_service.py` |
| Message-oriented communication (II) | `backend/app/distributed/events.py`, `app/workers/usage_worker.py` |
| Names / identifiers, fault tolerance (II) | K8s Service DNS, `POD_NAME`, probes, `XAUTOCLAIM`, idempotent consumer |
| Lamport logical clock (III) | `backend/app/distributed/lamport.py` |
| Distributed mutual exclusion (III) | `backend/app/distributed/lock.py`, `app/routes/proxy.py` |
| Leader election (III) | `backend/app/distributed/leader.py`, `app/workers/alert_worker.py` |
| Kubernetes, autoscaling (IV) | `deploy/k8s/` |

## Run it on Docker Desktop Kubernetes

Prerequisites: Docker Desktop with **Kubernetes enabled** (Settings → Kubernetes).

```powershell
.\scripts\deploy.ps1          # builds 3 images, installs metrics-server, deploys, seeds
kubectl -n acg get pods
```

Open <http://localhost:8080> and sign in as **admin@test.com / demo123**.

* **Cluster** page: live pods, the elected leader, the queue backlog, lock
  stats, and events in Lamport order.
* **Employee simulator** page: send requests as any employee and see which
  pods served them.

Remove everything with `.\scripts\teardown.ps1`.

> Using a kind cluster instead? Pass its context, e.g.
> `.\scripts\deploy.ps1 -Context kind-a7-cluster`. The script loads the images
> into the kind nodes for you.

## Run it with docker compose (no Kubernetes)

```powershell
docker compose up --build
```

Then open <http://localhost:8080>, the same login as above.

## Run it as a single process (development)

```powershell
cd services/mock-llm;  python -m uvicorn app:app --port 8099     # terminal 1
cd backend
pip install -r requirements-dev.txt
python seed_data.py
python -m uvicorn app.main:app --port 8000                         # terminal 2
cd frontend; npm install; npm run dev                              # terminal 3 -> :5173
```

Without `REDIS_URL` the gateway runs alone in `sync` mode: usage is written
directly and no locks or leader are used. Every feature still works.

## Tests

```powershell
cd backend
python -m pytest -q
```

The suite covers the Lamport clock, lock exclusivity (including lost-update
prevention), leader failover, stream publish/consume, redelivery dedup,
reclaiming a dead worker's events, caps that count pending spend, and the
Employee Simulator end to end. Redis is simulated with fakeredis.

## Repository layout

```
ai-cost-governor/
├── backend/                 gateway + workers (one image, three commands)
│   ├── app/distributed/     lamport, lock, leader, membership, events, redis client
│   ├── app/workers/         usage_worker, alert_worker
│   ├── app/routes/          proxy, governed, admin, cluster (status + simulator), auth, settings
│   ├── app/services/        caps, alerts, usage, accounting, compression, routing, pricing
│   ├── seed_data.py         demo org: 20 employees, 3 teams, 30 days of usage
│   └── .env                 local settings + secrets (copied into the K8s Secret)
├── services/mock-llm/       fake OpenAI + Anthropic provider
├── frontend/                React dashboard, served by nginx in the cluster
├── deploy/k8s/              Kubernetes manifests (kustomize)
├── scripts/                 deploy.ps1, teardown.ps1, load_test.py
├── docker-compose.yml
└── docs/
```

## Product features (unchanged from the original app)

Spend dashboard, per-user and per-team caps, 80 % / 90 % alerts, savings
report, Cost Optimizer, a governed endpoint (compression + cheapest-capable
model routing), and encrypted provider keys. API docs are at
<http://localhost:8080/docs>.
