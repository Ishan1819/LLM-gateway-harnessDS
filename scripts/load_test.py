"""Sustained load against the gateway, to trigger the HorizontalPodAutoscaler.

Logs in as the demo admin, picks the seeded employees, and keeps sending
proxy requests as them for --duration seconds. Watch scaling in another
terminal:

    kubectl --context docker-desktop -n acg get hpa gateway -w
    kubectl --context docker-desktop -n acg get pods -l app=gateway -w

    python scripts/load_test.py                       # 120 s, 40 concurrent
    python scripts/load_test.py --duration 300 --concurrency 60
    python scripts/load_test.py --base-url http://localhost:8080

Requires only `httpx` (pip install httpx). No real LLM is called.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import time

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--email", default="admin@test.com")
    parser.add_argument("--password", default="demo123")
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=40)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=30) as api:
        login = await api.post("/api/auth/login", json={"email": args.email, "password": args.password})
        login.raise_for_status()
        token = login.json()["access_token"]
        slug = login.json()["organization"]["slug"]
        users = (await api.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})).json()
        keys = []
        for u in users:
            if not u["is_active"]:
                continue
            k = await api.get(f"/api/admin/users/{u['id']}/key", headers={"Authorization": f"Bearer {token}"})
            keys.append(k.json()["proxy_api_key"])

    # Lift caps out of the way? No: blocked (429) requests are still real load
    # on the gateway, and they show cap enforcement working under pressure.
    print(f"{len(keys)} employees, {args.concurrency} concurrent, {args.duration}s against {args.base_url}")

    stats = collections.Counter()
    pods = collections.Counter()
    deadline = time.time() + args.duration
    limits = httpx.Limits(max_keepalive_connections=0)  # new connection each time -> spread over pods

    async with httpx.AsyncClient(base_url=args.base_url, timeout=60, limits=limits) as client:
        async def worker(n: int) -> None:
            i = n
            while time.time() < deadline:
                key = keys[i % len(keys)]
                i += args.concurrency
                try:
                    r = await client.post(
                        f"/v1/org/{slug}/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": f"load test {i}"}]},
                    )
                    stats[r.status_code] += 1
                    pods[r.headers.get("x-acg-gateway-pod", "?")] += 1
                except httpx.HTTPError:
                    stats["error"] += 1

        async def reporter() -> None:
            while time.time() < deadline:
                await asyncio.sleep(5)
                total = sum(stats.values())
                print(f"[{int(deadline - time.time()):>4}s left] {total} requests  {dict(stats)}  pods={len(pods)}")

        await asyncio.gather(reporter(), *(worker(n) for n in range(args.concurrency)))

    print("\nRequests per gateway pod:")
    for pod, count in pods.most_common():
        print(f"  {pod:<40} {count}")


if __name__ == "__main__":
    asyncio.run(main())
