from dataclasses import dataclass

import httpx


class GuardError(Exception):
    pass


@dataclass(frozen=True)
class GuardDecision:
    allow: bool
    findings: tuple[dict, ...]
    redacted_text: str


class GuardClient:
    def __init__(self, base_url: str, http: httpx.Client) -> None:
        self._base = base_url.rstrip("/")
        self._http = http

    def check(self, text: str, tools: list[str], source: str) -> GuardDecision:
        try:
            response = self._http.post(
                f"{self._base}/v1/check",
                json={"text": text, "tools": tools, "source": source},
            )
        except httpx.HTTPError as exc:
            raise GuardError("guardrail unreachable") from exc
        if response.status_code >= 400:
            raise GuardError("guardrail rejected the check")
        try:
            data = response.json()
            findings = data.get("findings") or []
            if not isinstance(findings, list):
                raise TypeError("findings")
            return GuardDecision(
                allow=data["decision"] == "allow",
                findings=tuple(item for item in findings if isinstance(item, dict)),
                redacted_text=data.get("redacted_text")
                if isinstance(data.get("redacted_text"), str)
                else "",
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise GuardError("guardrail response was not usable") from exc
