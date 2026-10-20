"""Standalone proof that Headroom-inspired compression actually works.

    input (agent transcript: RAG context + tool JSON + repetitive polling)
      -> compress_conversation() [3 techniques]
      -> real tiktoken token measurement (before vs after)
      -> savings report

Run with:  python -m scripts.compression_demo   (from backend/)
       or: python scripts/compression_demo.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.compression import compress_conversation  # noqa: E402
from app.services.compression.tokenizer import count_tokens  # noqa: E402

RAG_CHUNKS = [
    "Horizontal pod autoscaling (HPA) adjusts the number of running replicas "
    "based on observed CPU, memory, or custom metrics. It works by polling "
    "the metrics API on a fixed interval (default 15s) and comparing the "
    "observed value against a target utilization. When the observed value "
    "exceeds the target for a sustained period, HPA increases replica count "
    "up to a configured maximum; when it drops well below target, it scales "
    "down, subject to a cooldown/stabilization window to avoid thrashing.",
    "Vertical pod autoscaling (VPA) takes a different approach: instead of "
    "changing replica count, it adjusts the CPU/memory requests and limits "
    "of existing pods based on historical usage. VPA is most useful for "
    "workloads that cannot be horizontally scaled easily, such as stateful "
    "singletons, and is often run in 'recommendation only' mode alongside "
    "HPA rather than in full auto mode, since the two can conflict if both "
    "try to react to the same metric signal simultaneously.",
    "Cluster autoscaling operates one level above pod autoscaling: it adds "
    "or removes worker nodes based on whether pending pods are unschedulable "
    "due to insufficient resources, or whether existing nodes are "
    "significantly underutilized and their pods could be consolidated "
    "elsewhere. Node scale-down typically respects pod disruption budgets "
    "and drains connections gracefully before terminating an instance.",
    "A common scaling anti-pattern is setting the HPA target utilization too "
    "close to 100%, which leaves no headroom to absorb a traffic spike while "
    "new replicas are still starting up (cold start latency). A more robust "
    "target is usually 60-70% utilization, combined with a slightly larger "
    "stabilization window on scale-down than scale-up, so the system reacts "
    "quickly to load increases but is conservative about releasing capacity.",
    "Custom metrics autoscaling (e.g. queue depth, requests-per-second, "
    "p99 latency) generally produces better scaling decisions than raw CPU "
    "for I/O-bound services, because CPU utilization can stay flat even as "
    "queue backlog grows during an upstream slowdown. Exposing an "
    "application-level metric via a metrics adapter lets HPA scale on the "
    "signal that actually correlates with user-facing degradation.",
    "Predictive/scheduled autoscaling pre-warms capacity ahead of known "
    "traffic patterns (daily peak hours, marketing campaigns) rather than "
    "reacting after the fact. This avoids the cold-start latency window "
    "entirely for predictable load, and is typically implemented as a cron "
    "trigger that temporarily raises the HPA minReplicas floor, letting "
    "reactive autoscaling still handle any unexpected excess above that.",
]


def build_rag_context(chunks: list[str]) -> str:
    parts = [f"[Source {i}]\n{c}" for i, c in enumerate(chunks, 1)]
    return "\n\n".join(parts)


def build_health_check_logs(n: int = 220) -> str:
    lines: list[str] = []
    start = datetime(2026, 8, 12, 9, 0, 0)
    services = ["auth-service", "billing-service", "search-service", "notification-service"]
    failed = warned = 0
    for i in range(n):
        ts = (start + timedelta(seconds=i * 3)).isoformat()
        service = services[i % len(services)]
        if i % 47 == 0 and i > 0:
            failed += 1
            lines.append(f"{ts} ERROR {service} healthcheck failed: connection timeout after 5000ms")
        elif i % 23 == 0 and i > 0:
            warned += 1
            lines.append(f"{ts} WARN {service} healthcheck slow: response time 1240ms exceeds 1000ms threshold")
        else:
            lines.append(f"{ts} INFO {service} healthcheck OK: status=200 latency=45ms")
    lines.append(f"=== {n} healthchecks run: {failed} failed, {warned} warnings, {n - failed - warned} passed ===")
    return "\n".join(lines)


def build_deployment_polling_output() -> str:
    lines = ["Deploying service auth-service v2.4.1..."]
    lines += ["Waiting for pods to become ready (0/3)..."] * 15
    lines += ["Waiting for pods to become ready (2/3)..."] * 8
    lines += ["Waiting for pods to become ready (3/3)..."] * 3
    lines.append("Deployment auth-service v2.4.1 is ready.")
    return "\n".join(lines)


def build_transcript() -> list[str]:
    """A realistic agent transcript mixing all 3 target scenarios:
    RAG context, large JSON/log tool output, and repetitive re-fetches
    across turns.
    """
    turn1 = (
        "User: We're seeing latency spikes during traffic bursts. What autoscaling "
        "strategy should we use, and can you check current service health and the "
        "last deployment status?"
    )
    turn2 = "Tool result (health_check_logs):\n" + build_health_check_logs()
    turn3 = "Tool result (deployment_status):\n" + build_deployment_polling_output()
    turn4 = (
        "Tool result (vector_search query='autoscaling strategies for bursty traffic'):\n"
        + build_rag_context(RAG_CHUNKS)
    )
    turn5 = (
        "User: Good. Given that, what specifically should we change for the auth-service? "
        "Pull the autoscaling docs again to be sure."
        "\n\nTool result (vector_search query='autoscaling strategies bursty traffic auth-service'):\n"
        + build_rag_context(RAG_CHUNKS)  # re-fetched, same underlying chunks -> cross-turn dedup target
    )
    turn6 = "Tool result (deployment_status, re-checked):\n" + build_deployment_polling_output()
    return [turn1, turn2, turn3, turn4, turn5, turn6]


def format_report(result) -> str:
    def fmt(n: int) -> str:
        return f"{n:,}"

    lines = [
        "Headroom-inspired Compression Demo",
        "=" * 40,
        f"Techniques applied: {', '.join(result.techniques_applied)}",
        "",
        f"Original tokens:    {fmt(result.original_tokens):>10}",
        f"Compressed tokens:  {fmt(result.compressed_tokens):>10}",
        f"Tokens saved:       {fmt(result.tokens_saved):>10}",
        f"Reduction:          {result.reduction_pct:>9.1f}%",
    ]
    return "\n".join(lines)


def main() -> None:
    blocks = build_transcript()

    print("Per-block original token counts (measured with tiktoken):")
    for i, b in enumerate(blocks, 1):
        print(f"  turn {i}: {count_tokens(b):,} tokens")
    print()

    result = compress_conversation(blocks)
    print(format_report(result))


if __name__ == "__main__":
    main()
