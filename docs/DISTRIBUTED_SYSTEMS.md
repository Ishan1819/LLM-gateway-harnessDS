# AI Cost Governor — Distributed Systems design

A containerised, horizontally
scalable LLM cost-governance gateway, deployed on Kubernetes (Docker Desktop).

## 1. What the application does

Companies give their developers ("employees") access to LLM APIs. The
governor sits between the developers and the providers:

1. every request is authenticated with the employee's proxy key (`acg-…`);
2. the employee's, team's and organisation's spending caps are checked
   **before** the request leaves (blocked requests get HTTP 429);
3. the request is forwarded to the LLM provider;
4. tokens and cost are recorded and shown on the admin dashboard, with
   80 % / 90 % budget alerts.

For the project, the real OpenAI/Anthropic APIs are replaced by **mock-llm**, a
small service that speaks both APIs and returns simulated answers and token
counts. No API key and no money are needed.

## 2. Architecture

```
                          Browser (admin)
                                │  http://localhost:8080
                       ┌────────▼─────────┐
                       │ frontend (nginx) │  React dashboard + reverse proxy
                       └────────┬─────────┘
                                │ /api, /v1   (Service "gateway")
              ┌─────────────────▼──────────────────┐
              │ gateway ×2…6   (HPA on CPU)          │  FastAPI: auth, caps,
              │ stateless, identical replicas        │  proxy, admin API
              └──┬───────────────┬───────────────┬──┘
     RPC (HTTP)  │               │ XADD event    │ SET NX PX (locks),
   retry+backoff │               │ (+Lamport ts) │ INCR (rate limit), heartbeats
        ┌────────▼──────┐   ┌────▼───────────────▼───────────────┐
        │ mock-llm ×2   │   │ Redis   stream · locks · leader     │
        │ (OpenAI +     │   │         lease · membership · rates  │
        │  Anthropic)   │   └────┬──────────────────────┬────────┘
        └───────────────┘        │ XREADGROUP            │ lease
                         ┌───────▼────────┐     ┌────────▼────────┐
                         │ usage-worker ×2│     │ alert-worker ×2 │
                         │ consumer group │     │ 1 elected leader│
                         └───────┬────────┘     └────────┬────────┘
                                 └──────────┬────────────┘
                                   ┌────────▼────────┐
                                   │ Postgres        │ StatefulSet + PVC
                                   └─────────────────┘
```

| Component | Kubernetes object | Replicas | Code |
|---|---|---|---|
| frontend | Deployment + LoadBalancer Service | 1 | `frontend/`, `frontend/nginx.conf` |
| gateway | Deployment + Service + HPA | 2 → 6 | `backend/app/main.py`, `app/routes/` |
| mock-llm | Deployment + Service | 2 | `services/mock-llm/app.py` |
| usage-worker | Deployment | 2 | `backend/app/workers/usage_worker.py` |
| alert-worker | Deployment | 2 | `backend/app/workers/alert_worker.py` |
| redis | Deployment + Service | 1 | `deploy/k8s/redis.yaml` |
| postgres | StatefulSet + PVC + Service | 1 | `deploy/k8s/postgres.yaml` |
| seed-demo | Job (one-shot) | — | `backend/seed_data.py` |

## 3. Syllabus mapping

### Unit I — Introduction
* **Architecture:** microservices. Each service has one job and can be scaled
  and restarted on its own.
* **Middleware:** the gateway is the middleware between the client SDKs and the
  provider services. Redis is the coordination middleware between the services.
* **Virtualization (self study):** every service is a Docker container, and
  Kubernetes schedules them as pods.
* **Design issues handled:** scalability (stateless gateway + HPA),
  transparency (developers change only `base_url`; replicas are invisible to
  them), openness (it speaks the standard OpenAI and Anthropic APIs) and fault
  tolerance (see Unit II).

### Unit II — Communication
* **Remote Procedure Call:** the gateway calls mock-llm with synchronous
  request/response HTTP (`app/services/proxy_service.py: forward`). Each call
  has a timeout. Connection errors and 5xx responses are retried with
  exponential backoff (`UPSTREAM_RETRIES`). Each retry opens a new connection,
  so the Service can send it to a healthy replica.
* **Message-oriented communication:** after answering, the gateway does not
  write to the database. It publishes a *usage event* to the Redis Stream
  `acg:usage-events` (`app/distributed/events.py`), which is persistent and
  asynchronous. The usage-workers read it as a **consumer group**: every event
  goes to exactly one worker, and adding workers shares the load.
* **Names, identifiers, addresses (self study):** services find each other by
  DNS name (`gateway`, `mock-llm`, `redis`, `postgres`), never by IP. Every pod
  identifies itself by its pod name (downward API → `POD_NAME`), which appears
  in response headers (`x-acg-gateway-pod`, `x-acg-upstream-pod`) and on the
  Cluster page.
* **Fault tolerance (self study):**
  * liveness and readiness probes (`/health`, `/ready`). Kubernetes restarts
    dead pods and routes traffic only to ready ones;
  * at-least-once delivery: an event is acknowledged (`XACK`) only after its
    row is committed. Events left unacknowledged by a crashed worker are
    reclaimed by another worker (`XAUTOCLAIM`);
  * an idempotent consumer: the `event_id` stops a redelivered event from
    creating a second row, so the database sees each event exactly once;
  * graceful degradation: if Redis is down, usage is written synchronously and
    locks are skipped. No request fails just because coordination is
    unavailable.
  * Redis runs with append-only persistence, so queued events survive a Redis
    restart.

### Unit III — Synchronization
* **Logical clocks (Lamport):** `app/distributed/lamport.py`. Each gateway pod
  ticks its clock when it sends a usage event and stamps the event with the
  value. The worker applies `C = max(C, t) + 1` on receive. The Cluster page
  orders recent events by `(lamport_ts, origin_pod)`, which is one consistent
  total order across pods with no synchronised physical clocks. The timestamp
  is also stored in `usage_logs.lamport_ts`.
* **Clock synchronization:** all physical timestamps are UTC and come from the
  database server, a single time source. Ordering *between* pods uses Lamport
  time instead of wall clocks.
* **Mutual exclusion:** `app/distributed/lock.py`, used in
  `app/routes/proxy.py: user_critical_section`.
  * *Problem:* two gateway pods serve the same employee at the same moment.
    Both read "spent $0.99 of $1.00", both allow the request, and the cap is
    overshot.
  * *Solution:* a per-employee Redis lock (`SET key token NX PX ttl`) makes
    *check cap → call LLM → reserve spend* a critical section.
  * Only the owner can release the lock (token compare via WATCH/MULTI), and
    the TTL frees it if the owner crashes.
  * Spend that is reserved but not yet persisted is kept in *pending* counters,
    so the cap check stays correct while events wait in the queue.
* **Election algorithm:** `app/distributed/leader.py`. The alert-workers
  compete for a lease (`SET leader id NX PX ttl`). Only the leader scans caps
  and raises alerts. It renews the lease every ttl/3. If it dies, the lease
  expires and a follower wins a new **term**. This is the lease-based election
  used by Kubernetes controllers and etcd/ZooKeeper recipes, with Redis
  providing the atomic step. Bully and Ring need every node to know every other
  node; a lease does not.
* **Global state:** the Cluster page is a snapshot of the system state. It
  shows live members (from heartbeats), the leader, the queue backlog, lock
  statistics and the clocks.

### Unit IV — Emerging distributed paradigms
* **Kubernetes:** Deployments, StatefulSet with a PersistentVolumeClaim,
  Services (ClusterIP and LoadBalancer), ConfigMap, Secret, Job, probes,
  resource requests/limits, rolling updates, and a HorizontalPodAutoscaler.
* **Distributed web-based system:** a browser client, an nginx front end, a
  stateless application tier and a shared data tier.
* **Case study links:** the gateway pattern is how AWS API Gateway and
  Cloudflare Workers front their backends. The mock-llm Deployment plays the
  role of a managed provider endpoint.

## 4. Request lifecycle (one proxy call)

1. The SDK sends `POST /v1/org/demo/chat/completions` with `Bearer acg-…`.
   nginx forwards it to Service `gateway`, which picks a pod.
2. The gateway authenticates the employee and applies the cluster-wide rate
   limit (a Redis counter shared by all pods).
3. **Lock** `acg:lock:user:<id>`, then check caps (DB spend + pending spend).
4. **RPC** to Service `mock-llm`, with retry and backoff.
5. **Publish** the usage event (Lamport ts, origin pod) with `XADD`, and add
   its cost to the pending counters in the same Redis transaction.
6. **Unlock**, then reply. The headers name the pods and the Lamport ts.
7. A **usage-worker** reads the event (`XREADGROUP`), inserts the row, releases
   the pending spend, and acknowledges it (`XACK`).
8. The **alert-worker leader** periodically raises 80 % / 90 % alerts.

## 5. Configuration

All settings are environment variables (`backend/app/config.py`).
`backend/.env` holds the local values and the secrets.

| Variable | Meaning |
|---|---|
| `POD_NAME` | identity of the process (pod name in Kubernetes) |
| `REDIS_URL` | coordination layer; unset = single-process mode |
| `USAGE_MODE` | `sync` (direct DB write) or `stream` (Redis Stream + workers) |
| `USAGE_STREAM`, `USAGE_GROUP` | stream key and consumer group name |
| `LOCK_TTL_MS`, `LOCK_WAIT_MS` | lock lease and the maximum wait before a 429 |
| `LEADER_TTL_MS` | leader lease. Failover time is at most this value |
| `ALERT_SCAN_INTERVAL_S` | how often the leader scans caps |
| `HEARTBEAT_TTL_S` | how long until a silent pod drops out of the view |
| `UPSTREAM_RETRIES` | RPC retries to mock-llm |
| `RATE_LIMIT_PER_MIN` | per-key limit, enforced across the cluster |
| `GATEWAY_INTERNAL_URL` | where the Employee Simulator sends traffic (Service URL) |
| `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL` | point at mock-llm |
| `POSTGRES_*`, `JWT_SECRET`, `ENCRYPTION_KEY` | secrets → Kubernetes Secret |

## 6. Known trade-offs (worth mentioning in a viva)

* The lock is held across the LLM call. This gives strict cap correctness, but
  it serialises one employee's concurrent requests. Different employees still
  run fully in parallel.
* A single Redis instance is a single point of coordination. A production
  setup would use Redis Sentinel/Cluster, or Redlock across several masters.
* Streaming responses take the lock only for the cap check, because holding it
  for a stream that lasts minutes would block the employee.
