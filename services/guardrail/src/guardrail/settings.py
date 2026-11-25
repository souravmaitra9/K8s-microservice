import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    allowed_tools: frozenset[str] = frozenset({"kb_search", "ticket_create"})
    max_bytes: int = 32768
    injection_threshold: float = 0.8
    agent_url: str = "http://agent:8080"
    agent_timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "Settings":
        raw_tools = os.environ.get("ALLOWED_TOOLS", "kb_search,ticket_create")
        tools = frozenset(part.strip() for part in raw_tools.split(",") if part.strip())
        return cls(
            allowed_tools=tools,
            max_bytes=_int("MAX_BODY_BYTES", 32768),
            injection_threshold=_float("INJECTION_THRESHOLD", 0.8),
            agent_url=os.environ.get("AGENT_URL", "http://agent:8080"),
            agent_timeout=_float("AGENT_TIMEOUT_SECONDS", 60.0),
        )


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)
