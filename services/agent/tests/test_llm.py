import json

import httpx
import pytest

from agent.llm import LLMError, OpenAIClient, StubLLM, parse_completion
from agent.settings import Settings


def test_parse_tool_call() -> None:
    parsed = parse_completion(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "kb_search",
                                    "arguments": json.dumps({"query": "disk"}),
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }
    )
    assert parsed.tool_calls[0].name == "kb_search"
    assert parsed.tool_calls[0].arguments == {"query": "disk"}
    assert parsed.prompt_tokens == 10


def test_parse_rejects_an_empty_payload() -> None:
    with pytest.raises(LLMError):
        parse_completion({"choices": []})


def test_invalid_tool_arguments_are_not_a_dict() -> None:
    parsed = parse_completion(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"id": "c", "function": {"name": "kb_search", "arguments": "not-json"}}
                        ]
                    }
                }
            ]
        }
    )
    assert parsed.tool_calls[0].arguments is None


def test_openai_client_sends_the_key_and_hides_it_on_failure() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(500, json={"error": "nope"})

    settings = Settings(llm_base_url="http://llm/v1", llm_api_key="test-key", llm_model="local")
    client = OpenAIClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMError) as exc:
        client.complete([{"role": "user", "content": "hi"}], [])
    assert seen["authorization"] == "Bearer test-key"
    assert "test-key" not in str(exc.value)


def test_stub_searches_then_summarizes() -> None:
    stub = StubLLM()
    first = stub.complete([{"role": "user", "content": "CrashLoopBackOff on payments"}], [])
    assert first.tool_calls[0].name == "kb_search"
    second = stub.complete(
        [
            {"role": "user", "content": "CrashLoopBackOff on payments"},
            {
                "role": "tool",
                "content": json.dumps({"results": [{"title": "CrashLoopBackOff"}]}),
            },
        ],
        [],
    )
    assert second.content == "Top runbook: CrashLoopBackOff."


def test_stub_opens_a_ticket() -> None:
    stub = StubLLM()
    response = stub.complete(
        [{"role": "user", "content": "Open a sev2 ticket for payments latency"}],
        [],
    )
    assert response.tool_calls[0].name == "ticket_create"
    assert response.tool_calls[0].arguments["severity"] == "sev2"
