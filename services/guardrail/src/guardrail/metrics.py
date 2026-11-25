from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Histogram


@dataclass
class Metrics:
    requests: Counter
    blocks: Counter
    duration: Histogram
    registry: CollectorRegistry


def build_metrics(registry: CollectorRegistry | None = None) -> Metrics:
    registry = registry or CollectorRegistry()
    return Metrics(
        requests=Counter(
            "guardrail_requests_total",
            "Policy checks by decision and source.",
            ["decision", "source"],
            registry=registry,
        ),
        blocks=Counter(
            "guardrail_blocks_total",
            "Denied checks by category and source.",
            ["category", "source"],
            registry=registry,
        ),
        duration=Histogram(
            "guardrail_request_duration_seconds",
            "Policy check latency.",
            registry=registry,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
        ),
        registry=registry,
    )
