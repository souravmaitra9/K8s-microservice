"""Heuristics for untrusted text. These are filters, not a classifier."""

import re
import unicodedata
from dataclasses import dataclass

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u2060"), None)
_CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "і": "i",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "А": "A",
        "Е": "E",
        "І": "I",
        "О": "O",
        "Р": "P",
        "С": "C",
        "У": "Y",
        "Х": "X",
    }
)

_INJECTION: tuple[tuple[re.Pattern[str], str, float], ...] = (
    (
        re.compile(
            r"\b(ignore|disregard|forget|override)\b.{0,48}\b"
            r"(previous|prior|above|earlier)\b.{0,48}\b"
            r"(instructions|prompts?|rules|guidelines|system prompt)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "instruction_override",
        0.95,
    ),
    (
        re.compile(
            r"\b(ignore|disregard)\b.{0,24}\b(all|any)\b.{0,24}\b(instructions|rules|guidelines)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "instruction_override",
        0.95,
    ),
    (
        re.compile(
            r"\b(reveal|print|show|dump|repeat|output|leak)\b.{0,48}\b"
            r"(system prompt|hidden prompt|developer message|"
            r"hidden instructions|initial instructions)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "prompt_exfiltration",
        0.95,
    ),
    (
        re.compile(
            r"\byou are now\b.{0,48}\b"
            r"(a|an|unrestricted|dan|jailbroken|developer|admin|root|unfiltered)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "role_override",
        0.9,
    ),
    (
        re.compile(r"\b(jailbreak|developer mode|dan mode|do anything now)\b", re.IGNORECASE),
        "jailbreak",
        0.9,
    ),
    (
        re.compile(
            r"(<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>|</?system>)",
            re.IGNORECASE,
        ),
        "control_token",
        0.9,
    ),
    (
        re.compile(
            r"\b(bypass|disable|turn off)\b.{0,40}\b"
            r"(guardrail|safety filter|content filter|safety policy)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "control_bypass",
        0.9,
    ),
)

_SECRET_SHAPES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws_access_key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "github_pat"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "github_fine_grained_pat"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "api_token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "slack_token"),
    (re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"), "private_key"),
)

_ASSIGNED = re.compile(
    r"(?i)\b(aws_secret_access_key|api[_-]?key|secret|token|password)\b"
    r"\s*[:=]\s*['\"]?([A-Za-z0-9_+\/=-]{12,})"
)

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

_COMMANDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\$\([^)]{1,80}\)"), "command_substitution"),
    (re.compile(r"`[^`]{1,80}`"), "backtick_substitution"),
    (
        re.compile(
            r"\b(curl|wget|nc|ncat|socat|bash|sh)\b.{0,40}(-c\b|https?://|\|)",
            re.IGNORECASE | re.DOTALL,
        ),
        "transfer_or_shell",
    ),
    (re.compile(r";\s*(rm|curl|wget|sh|bash)\b", re.IGNORECASE), "chained_shell"),
)


@dataclass(frozen=True)
class Finding:
    category: str
    code: str
    score: float


@dataclass(frozen=True)
class Scan:
    findings: tuple[Finding, ...]
    redacted_text: str


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).translate(_CONFUSABLES)


def luhn_ok(digits: str) -> bool:
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _plausible_assigned(value: str) -> bool:
    if any(char.isdigit() for char in value) and len(value) >= 12:
        return True
    mixed_case = any(char.islower() for char in value) and any(char.isupper() for char in value)
    return len(value) >= 20 and mixed_case


def _add(findings: list[Finding], seen: set[str], finding: Finding) -> None:
    if finding.code in seen:
        return
    seen.add(finding.code)
    findings.append(finding)


def _secrets(text: str) -> tuple[list[Finding], str]:
    findings: list[Finding] = []
    seen: set[str] = set()
    redacted = text
    for pattern, code in _SECRET_SHAPES:
        if pattern.search(redacted):
            _add(findings, seen, Finding("secret", code, 1.0))
            redacted = pattern.sub("[redacted]", redacted)

    def replace_assigned(match: re.Match[str]) -> str:
        value = match.group(2)
        if not _plausible_assigned(value):
            return match.group(0)
        _add(findings, seen, Finding("secret", "assigned_secret", 1.0))
        prefix = match.group(0)[: match.start(2) - match.start()]
        return prefix + "[redacted]"

    redacted = _ASSIGNED.sub(replace_assigned, redacted)
    return findings, redacted


def _pii(text: str) -> tuple[list[Finding], str]:
    findings: list[Finding] = []
    redacted = text
    if _EMAIL.search(redacted):
        findings.append(Finding("pii", "email", 0.9))
        redacted = _EMAIL.sub("[redacted]", redacted)
    if _SSN.search(redacted):
        findings.append(Finding("pii", "ssn", 1.0))
        redacted = _SSN.sub("[redacted]", redacted)

    card_found = False

    def replace_card(match: re.Match[str]) -> str:
        nonlocal card_found
        digits = re.sub(r"\D", "", match.group(0))
        if luhn_ok(digits):
            card_found = True
            return "[redacted]"
        return match.group(0)

    redacted = _CARD.sub(replace_card, redacted)
    if card_found:
        findings.append(Finding("pii", "payment_card", 1.0))
    return findings, redacted


def _injection(text: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for pattern, code, score in _INJECTION:
        if pattern.search(text):
            _add(findings, seen, Finding("injection", code, score))
    return findings


def _commands(text: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for pattern, code in _COMMANDS:
        if pattern.search(text):
            _add(findings, seen, Finding("command", code, 1.0))
    return findings


def scan(text: str, *, commands: bool) -> Scan:
    normalized = normalize(text)
    findings = _injection(normalized)
    secret_findings, redacted = _secrets(normalized)
    pii_findings, redacted = _pii(redacted)
    findings.extend(secret_findings)
    findings.extend(pii_findings)
    if commands:
        findings.extend(_commands(normalized))
    return Scan(findings=tuple(findings), redacted_text=redacted)
