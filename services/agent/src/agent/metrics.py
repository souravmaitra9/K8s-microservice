from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Histogram


@dataclass
class Metrics:
    requests: Counter
    duration: Histogram
    tokens: Counter
    tool_calls: Counter
    llm_errors: Counter
    guardrail_denies: Counter
    steps_exhausted: Counter
    registry: CollectorRegistry


def build_metrics(registry: CollectorRegistry | None = None) -> Metrics:
    registry = registry or CollectorRegistry()
    return Metrics(
        requests=Counter(
            "agent_requests_total",
            "Chat requests by outcome.",
            ["status"],
            registry=registry,
        ),
        duration=Histogram(
            "agent_request_duration_seconds",
            "Chat request latency, including model and tool time.",
            registry=registry,
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
        ),
        tokens=Counter(
            "agent_llm_tokens_total",
            "Tokens reported by the model endpoint.",
            ["direction"],
            registry=registry,
        ),
        tool_calls=Counter(
            "agent_tool_calls_total",
            "Tool calls by allow-listed tool and status.",
            ["tool", "status"],
            registry=registry,
        ),
        llm_errors=Counter(
            "agent_llm_errors_total",
            "Failed model requests.",
            registry=registry,
        ),
        guardrail_denies=Counter(
            "agent_guardrail_denies_total",
            "Prompts the guardrail refused before the model was called.",
            registry=registry,
        ),
        steps_exhausted=Counter(
            "agent_tool_steps_exhausted_total",
            "Runs that hit the tool-step cap.",
            registry=registry,
        ),
        registry=registry,
    )
