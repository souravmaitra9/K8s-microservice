import json
from dataclasses import dataclass

import httpx

from agent.settings import Settings


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict | None


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    prompt_tokens: int
    completion_tokens: int


class StubLLM:
    """Deterministic stand-in used when LLM_BASE_URL is empty.

    Local and CI runs have no model endpoint. The stub still walks the tool
    loop so the policy checks are the same ones a real model would hit.
    """

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        del tools
        if any(message.get("role") == "tool" for message in messages):
            return _summarize(messages)
        user = _latest_user(messages)
        lowered = user.lower()
        prompt_tokens = max(1, len(user) // 4)
        if "ticket" in lowered:
            severity = next(
                (level for level in ("sev1", "sev2", "sev3", "sev4") if level in lowered), "sev3"
            )
            title = user.strip()[:80] or "incident"
            summary = user.strip()[:200] or "incident"
            call = ToolCall(
                "call-ticket",
                "ticket_create",
                {"title": title, "severity": severity, "summary": summary},
            )
            return LLMResponse(None, (call,), prompt_tokens, 12)
        query = user.strip()[:180] or "runbook"
        call = ToolCall("call-kb", "kb_search", {"query": query})
        return LLMResponse(None, (call,), prompt_tokens, 12)


class OpenAIClient:
    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        self._settings = settings
        self._http = http

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        url = self._settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"content-type": "application/json"}
        if self._settings.llm_api_key:
            headers["authorization"] = f"Bearer {self._settings.llm_api_key}"
        payload: dict[str, object] = {
            "model": self._settings.llm_model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            payload["tools"] = tools
        try:
            response = self._http.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError("llm request failed") from exc
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise LLMError("llm response was not usable") from exc
        return parse_completion(body)


def build_llm(settings: Settings, http: httpx.Client) -> StubLLM | OpenAIClient:
    if not settings.llm_base_url:
        return StubLLM()
    return OpenAIClient(settings, http)


def parse_completion(payload: dict) -> LLMResponse:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMError("llm response had no choices")
    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        raise LLMError("llm response had no message")
    content = message.get("content")
    if not isinstance(content, str):
        content = None
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return LLMResponse(
        content=content,
        tool_calls=parse_tool_calls(message),
        prompt_tokens=_tokens(usage, "prompt_tokens"),
        completion_tokens=_tokens(usage, "completion_tokens"),
    )


def parse_tool_calls(message: dict) -> tuple[ToolCall, ...]:
    calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        if not isinstance(raw, dict):
            continue
        function = raw.get("function") if isinstance(raw.get("function"), dict) else {}
        name = function.get("name") if isinstance(function.get("name"), str) else ""
        call_id = raw.get("id") if isinstance(raw.get("id"), str) else ""
        calls.append(ToolCall(call_id, name, _parse_args(function.get("arguments"))))
    return tuple(calls)


def _parse_args(raw: object) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _tokens(usage: dict, key: str) -> int:
    try:
        return max(0, int(usage.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def _latest_user(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def _summarize(messages: list[dict]) -> LLMResponse:
    raw = ""
    for message in reversed(messages):
        if message.get("role") == "tool" and isinstance(message.get("content"), str):
            raw = message["content"]
            break
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    text = "Done."
    if isinstance(data, dict) and "results" in data:
        results = data["results"] or []
        if not results:
            text = "No runbook matched."
        else:
            title = (
                results[0].get("title", "untitled") if isinstance(results[0], dict) else "untitled"
            )
            text = f"Top runbook: {title}."
    elif isinstance(data, dict) and "id" in data:
        text = f"Opened {data.get('id')} ({data.get('severity', 'unknown')})."
    return LLMResponse(text, (), 8, 12)
