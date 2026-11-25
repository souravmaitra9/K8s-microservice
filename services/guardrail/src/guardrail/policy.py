"""What the gateway does with a detector hit.

Output from the model is redacted, not refused, when the only problem is a
secret or a PII value. Untrusted input (the user, tool arguments, tool
results) is refused. Command-looking strings are only refused in tool
arguments: a person asking how backticks work is not the same as a tool call.
"""

import re
from dataclasses import dataclass

from guardrail.detectors import Finding, scan

_TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_BLOCKING = {"secret", "pii", "command", "tool", "size"}


@dataclass(frozen=True)
class Decision:
    allow: bool
    findings: tuple[Finding, ...]
    redacted_text: str


@dataclass(frozen=True)
class Policy:
    allowed_tools: frozenset[str]
    max_bytes: int = 32768
    injection_threshold: float = 0.8

    def evaluate(
        self,
        text: str,
        tools: list[str] | None = None,
        *,
        byte_length: int | None = None,
        source: str = "prompt",
    ) -> Decision:
        if source not in {"prompt", "tool_args", "tool_result", "output"}:
            raise ValueError(f"unknown source: {source}")
        requested = list(tools or [])
        size = len(text.encode("utf-8")) if byte_length is None else byte_length
        scanned = scan(text, commands=(source == "tool_args"))

        if source == "output":
            reported = tuple(
                item for item in scanned.findings if item.category in {"secret", "pii"}
            )
            return Decision(True, reported, scanned.redacted_text)

        findings: list[Finding] = []
        if size > self.max_bytes:
            findings.append(Finding("size", "body_too_large", 1.0))

        injection = [item for item in scanned.findings if item.category == "injection"]
        if _noisy_or(injection) >= self.injection_threshold:
            findings.extend(injection)

        findings.extend(
            item for item in scanned.findings if item.category in {"secret", "pii", "command"}
        )

        if source in {"prompt", "tool_args"} and requested:
            if len(requested) > 8:
                findings.append(Finding("tool", "too_many_tools", 1.0))
            elif any(not _tool_allowed(name, self.allowed_tools) for name in requested):
                findings.append(Finding("tool", "tool_not_allowed", 1.0))

        blocking = [
            item for item in findings if item.category in _BLOCKING or item.category == "injection"
        ]
        return Decision(not blocking, tuple(findings), scanned.redacted_text)


def _noisy_or(findings: list[Finding]) -> float:
    score = 0.0
    for finding in findings:
        score = 1 - (1 - score) * (1 - finding.score)
    return score


def _tool_allowed(name: str, allowed: frozenset[str]) -> bool:
    return _TOOL_NAME.fullmatch(name) is not None and name in allowed
