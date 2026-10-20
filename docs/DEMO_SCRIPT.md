# Viva demo script (about 10 minutes)

Everything is shown from the **admin account** (`admin@test.com` / `demo123`).
Employees are driven from the admin's **Employee simulator** page.

Keep two windows open: the browser at <http://localhost:8080>, and a
PowerShell terminal.

## 0. Before the viva (once)

1. Docker Desktop → Settings → Kubernetes → **Enable Kubernetes** → Apply.
2. From the project folder run:
   ```powershell
   .\scripts\deploy.ps1
   ```
3. Check that every pod is running:
   ```powershell
   kubectl -n acg get pods
   ```
   You should see 2 gateway, 2 mock-llm, 2 usage-worker, 2 alert-worker,
   1 frontend, 1 redis and 1 postgres pod, plus a completed seed job.

## 1. The system (Unit I, IV)

```powershell
kubectl -n acg get deploy,sts,svc,hpa
```
Explain the architecture diagram in `docs/DISTRIBUTED_SYSTEMS.md`: seven
services, all containers, managed by Kubernetes. Then log in as the admin and
show the **Overview** page with 30 days of seeded usage.

## 2. Inter-service communication + load balancing (Unit II: RPC)

1. Open **Employee simulator** and click the **Load balancing** preset.
2. Click **Send**.
3. Point at the two charts: requests spread across both **gateway** pods and
   both **mock-llm** pods. That is the Service load-balancing the RPC calls.
4. In the table, each row shows which gateway pod served the request and which
   LLM pod answered it.

## 3. Message-oriented communication (Unit II)

1. Open the **Cluster** page and show the stream, the consumer group and the
   two usage-workers.
2. Stop the consumers:
   ```powershell
   kubectl -n acg scale deploy usage-worker --replicas=0
   ```
3. Send 60 requests from the simulator. On the **Cluster** page, *Queue
   backlog* goes up: the events are waiting safely in the stream.
4. Start the consumers again:
   ```powershell
   kubectl -n acg scale deploy usage-worker --replicas=2
   ```
   The backlog drains to 0, and the new spend appears on Overview and Users.

## 4. Lamport clocks (Unit III)

On the **Cluster** page, *Recent usage events* are ordered by Lamport
timestamp. Events come from different gateway pods (`origin_pod`) and are
persisted by different workers (`processed_by`), yet they form one consistent
order. Explain the rules: tick on send, `max(C, t) + 1` on receive.

## 5. Mutual exclusion (Unit III)

1. Open **Cap management** and give one employee a monthly cap only slightly
   above their current spend, e.g. current spend + $0.01.
2. In the **Employee simulator**, pick **only that employee** and use the
   **Mutual exclusion** preset (20 concurrent requests on `gpt-4-turbo`,
   about $0.0025 each). Send.
3. Show the result:
   * Only a few requests return 200; the rest return 429 *Budget limit
     reached*.
   * The *Lock wait* column shows the requests waited for each other, even
     though they ran on different gateway pods.
   * Spend never goes past the cap.
4. On the **Cluster** page, the *Mutual exclusion* card shows the contended
   acquisitions.

## 6. Leader election + failover (Unit III)

1. The **Cluster** page marks one alert-worker with **★ leader · term N**.
2. Click **⏻ Turn off (simulate crash)** on the leader's card. The worker
   exits without giving up its lease, like a real crash. (Or delete the pod
   from the terminal: `kubectl -n acg delete pod <leader-pod-name>`.)
3. Within about 6 seconds the other alert-worker becomes the leader with term
   N+1 (see *Leader history*). Kubernetes restarts the crashed container
   (`kubectl -n acg get pods` shows RESTARTS 1), and it rejoins as a follower.

## 7. Fault tolerance (Unit II self study)

1. Start sending traffic. Use the **Scale-out burst** preset, or run:
   ```powershell
   python scripts/load_test.py --duration 60
   ```
2. Kill a gateway pod while the traffic is running:
   ```powershell
   kubectl -n acg delete pod -l app=gateway --wait=false
   kubectl -n acg get pods -w
   ```
3. The requests keep succeeding (retries plus the other replicas), and
   Kubernetes recreates the pods.
4. Optional: make mock-llm fail 30 % of calls and watch the retries hide it:
   ```powershell
   kubectl -n acg set env deploy/mock-llm MOCK_FAILURE_RATE=0.3
   ```
   Set it back to `0` afterwards.

## 8. Scalability: autoscaling (Unit IV)

1. Start sustained load:
   ```powershell
   python scripts/load_test.py --duration 180 --concurrency 60
   ```
2. In another terminal, watch the autoscaler:
   ```powershell
   kubectl -n acg get hpa gateway -w
   ```
3. CPU passes 50 %, and the HPA scales the gateway from 2 to as many as 6 pods.
   New pods appear on the **Cluster** page as their heartbeats arrive.
4. After the load stops, it scales back down after about a minute.

## 9. Cleanup

```powershell
.\scripts\teardown.ps1
```
