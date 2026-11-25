import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    guardrail_url: str = "http://guardrail:8080"
    kb_url: str = "http://kb:8080"
    tickets_url: str = "http://tickets:8080"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "local"
    llm_timeout: float = 30.0
    http_timeout: float = 10.0
    max_tool_steps: int = 3
    max_tool_result_bytes: int = 4000
    max_bytes: int = 32768

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            guardrail_url=os.environ.get("GUARDRAIL_URL", "http://guardrail:8080"),
            kb_url=os.environ.get("KB_URL", "http://kb:8080"),
            tickets_url=os.environ.get("TICKETS_URL", "http://tickets:8080"),
            llm_base_url=os.environ.get("LLM_BASE_URL", ""),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            llm_model=os.environ.get("LLM_MODEL", "local"),
            llm_timeout=_float("LLM_TIMEOUT_SECONDS", 30.0),
            http_timeout=_float("HTTP_TIMEOUT_SECONDS", 10.0),
            max_tool_steps=_int("MAX_TOOL_STEPS", 3),
            max_tool_result_bytes=_int("MAX_TOOL_RESULT_BYTES", 4000),
            max_bytes=_int("MAX_BODY_BYTES", 32768),
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
