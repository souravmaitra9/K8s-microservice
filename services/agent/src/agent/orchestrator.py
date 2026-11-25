import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

from agent.guard import GuardDecision, GuardError
from agent.llm import LLMError, LLMResponse, ToolCall
from agent.metrics import Metrics
from agent.prompt import CANARY, KNOWN_TOOLS, REFUSAL, SYSTEM_PROMPT, TOOL_SCHEMAS
from agent.settings import Settings
from agent.tools import ToolError

logger = logging.getLogger("agent")


class LLM(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


class Guard(Protocol):
    def check(self, text: str, tools: list[str], source: str) -> GuardDecision: ...


class Tools(Protocol):
    def invoke(self, name: str, arguments: dict) -> str: ...


@dataclass
class ChatResult:
    http_status: int
    message: str
    tool_calls: list[dict[str, str]]
    blocked: bool
    usage: dict[str, int]
    findings: list[dict] = field(default_factory=list)


class Orchestrator:
    def __init__(
        self, settings: Settings, llm: LLM, guard: Guard, tools: Tools, metrics: Metrics
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._guard = guard
        self._tools = tools
        self._metrics = metrics

    def run(self, messages: list[dict]) -> ChatResult:
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        incoming = [
            message["content"] for message in messages if isinstance(message.get("content"), str)
        ]
        cleaned = [
            {"role": message["role"], "content": message["content"]}
            for message in messages
            if message.get("role") in {"user", "assistant"}
            and isinstance(message.get("content"), str)
        ]
        if not any(message["role"] == "user" for message in cleaned):
            return ChatResult(400, "at least one user message is required", [], False, usage)

        decision = self._check("\n".join(incoming), [], "prompt", [], usage)
        if isinstance(decision, ChatResult):
            return decision
        if not decision.allow:
            self._metrics.guardrail_denies.inc()
            return ChatResult(403, "denied", [], True, usage, list(decision.findings))

        transcript: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, *cleaned]
        executed: list[dict[str, str]] = []
        for _step in range(self._settings.max_tool_steps):
            try:
                response = self._llm.complete(transcript, TOOL_SCHEMAS)
            except LLMError:
                self._metrics.llm_errors.inc()
                logger.warning("llm request failed")
                return ChatResult(502, "llm request failed", executed, True, usage)
            self._add_usage(usage, response)
            if not response.tool_calls:
                return self._finish(response.content or "", executed, usage)
            outcome = self._execute(response.tool_calls[0], response, transcript, executed, usage)
            if outcome is not None:
                return outcome

        self._metrics.steps_exhausted.inc()
        return ChatResult(
            200,
            "Stopped after the tool step limit.",
            executed,
            True,
            usage,
            [{"category": "limit", "code": "tool_step_limit", "score": 1.0}],
        )

    def _execute(
        self,
        call: ToolCall,
        response: LLMResponse,
        transcript: list[dict],
        executed: list[dict[str, str]],
        usage: dict[str, int],
    ) -> ChatResult | None:
        label = call.name if call.name in KNOWN_TOOLS else "unknown"
        if call.name not in KNOWN_TOOLS or not isinstance(call.arguments, dict):
            self._metrics.tool_calls.labels(tool=label, status="denied").inc()
            executed.append({"name": label, "status": "denied"})
            if call.name not in KNOWN_TOOLS:
                message = "The model requested a tool that is not allow-listed."
                code = "tool_not_allowed"
            else:
                message = "The model returned tool arguments that were not a JSON object."
                code = "invalid_arguments"
            return ChatResult(
                200,
                message,
                executed,
                True,
                usage,
                [{"category": "tool", "code": code, "score": 1.0}],
            )

        arguments = call.arguments
        args_text = json.dumps(arguments, sort_keys=True)
        decision = self._check(args_text, [call.name], "tool_args", executed, usage)
        if isinstance(decision, ChatResult):
            return decision
        if not decision.allow:
            self._note(call.name, "denied", executed)
            return ChatResult(
                200,
                "Tool arguments were rejected by policy.",
                executed,
                True,
                usage,
                list(decision.findings),
            )

        try:
            result_text = self._tools.invoke(call.name, arguments)
        except ToolError:
            logger.warning("tool %s failed", call.name)
            self._note(call.name, "error", executed)
            return ChatResult(502, "tool call failed", executed, True, usage)

        result_text = result_text[: self._settings.max_tool_result_bytes]
        decision = self._check(result_text, [], "tool_result", executed, usage)
        if isinstance(decision, ChatResult):
            return decision
        if not decision.allow:
            self._note(call.name, "withheld", executed)
            logger.info("withheld tool result tool=%s", call.name)
            return ChatResult(
                200,
                "A tool result was discarded because it failed content policy.",
                executed,
                True,
                usage,
                list(decision.findings),
            )

        self._note(call.name, "ok", executed)
        call_id = call.id or f"call-{len(executed)}"
        transcript.append(
            {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": args_text},
                    }
                ],
            }
        )
        transcript.append({"role": "tool", "tool_call_id": call_id, "content": result_text})
        return None

    def _finish(
        self, content: str, executed: list[dict[str, str]], usage: dict[str, int]
    ) -> ChatResult:
        # Injection rules stay on untrusted input. Model output is checked for
        # the prompt canary and for secrets, which are redacted rather than refused.
        if CANARY in content:
            logger.warning("model output echoed the prompt canary")
            return ChatResult(
                200,
                REFUSAL,
                executed,
                True,
                usage,
                [{"category": "prompt", "code": "canary", "score": 1.0}],
            )
        decision = self._check(content, [], "output", executed, usage)
        if isinstance(decision, ChatResult):
            return decision
        message = content.strip() or "The model returned an empty answer."
        if decision.findings:
            message = decision.redacted_text.strip() or message
        return ChatResult(200, message, executed, False, usage, list(decision.findings))

    def _check(
        self,
        text: str,
        tools: list[str],
        source: str,
        executed: list[dict[str, str]],
        usage: dict[str, int],
    ) -> GuardDecision | ChatResult:
        try:
            return self._guard.check(text, tools, source)
        except GuardError:
            logger.warning("guardrail unavailable source=%s", source)
            return ChatResult(503, "guardrail unavailable", list(executed), True, dict(usage))

    def _note(self, name: str, status: str, executed: list[dict[str, str]]) -> None:
        self._metrics.tool_calls.labels(tool=name, status=status).inc()
        executed.append({"name": name, "status": status})

    def _add_usage(self, usage: dict[str, int], response: LLMResponse) -> None:
        usage["prompt_tokens"] += response.prompt_tokens
        usage["completion_tokens"] += response.completion_tokens
        if response.prompt_tokens:
            self._metrics.tokens.labels(direction="prompt").inc(response.prompt_tokens)
        if response.completion_tokens:
            self._metrics.tokens.labels(direction="completion").inc(response.completion_tokens)
