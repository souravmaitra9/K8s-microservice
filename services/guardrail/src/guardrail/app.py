import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import make_asgi_app
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from guardrail.metrics import Metrics, build_metrics
from guardrail.policy import Decision, Policy
from guardrail.settings import Settings

logger = logging.getLogger("guardrail")


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(default="", max_length=32_000)
    tools: list[Any] = Field(default_factory=list, max_length=8)
    source: str = "prompt"


def create_app(
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    metrics = build_metrics()
    policy = Policy(
        allowed_tools=settings.allowed_tools,
        max_bytes=settings.max_bytes,
        injection_threshold=settings.injection_threshold,
    )
    http = httpx.Client(
        transport=transport,
        timeout=settings.agent_timeout,
        trust_env=False,
        follow_redirects=False,
        headers={"user-agent": "agent-platform/0.1"},
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Iterator[None]:
        yield
        http.close()

    app = FastAPI(title="guardrail", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.policy = policy
    app.state.metrics = metrics
    app.state.http = http
    app.mount("/metrics", make_asgi_app(registry=metrics.registry))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "invalid request"})

    @app.middleware("http")
    async def gate(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        body = await request.body()
        request.state.raw_body = body
        request.state.request_id = request_id
        if request.method in {"POST", "PUT", "PATCH"} and len(body) > settings.max_bytes:
            response: Response = JSONResponse(
                status_code=413, content={"detail": "request body too large"}
            )
        else:
            response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/check")
    def check(request: Request) -> JSONResponse:
        payload = _json_object(request.state.raw_body)
        try:
            model = CheckRequest.model_validate(payload)
        except ValidationError:
            return JSONResponse(status_code=422, content={"detail": "invalid request"})
        if model.source not in {"prompt", "tool_args", "tool_result", "output"}:
            return JSONResponse(status_code=422, content={"detail": "invalid request"})
        decision = _screen(
            policy,
            metrics,
            model.text,
            _tool_names(model.tools),
            len(request.state.raw_body),
            model.source,
            request.state.request_id,
        )
        return JSONResponse(status_code=200, content=_check_body(decision))

    @app.post("/v1/chat")
    def chat(request: Request) -> Response:
        payload = _json_object(request.state.raw_body)
        text = _message_text(payload)
        if not text.strip():
            raise HTTPException(status_code=400, detail="user text is required")
        names = _tool_names(payload.get("tools") or [])
        decision = _screen(
            policy,
            metrics,
            text,
            names,
            len(request.state.raw_body),
            "prompt",
            request.state.request_id,
        )
        if not decision.allow:
            return JSONResponse(status_code=403, content=_deny_body(decision))
        upstream_headers = {
            "content-type": "application/json",
            "x-request-id": request.state.request_id,
        }
        try:
            upstream = http.post(
                f"{settings.agent_url.rstrip('/')}/v1/chat",
                content=request.state.raw_body,
                headers=upstream_headers,
            )
        except httpx.HTTPError:
            logger.warning("agent unreachable request_id=%s", request.state.request_id)
            return JSONResponse(status_code=502, content={"detail": "agent unavailable"})
        media_type = upstream.headers.get("content-type", "application/json")
        return Response(
            content=upstream.content, status_code=upstream.status_code, media_type=media_type
        )

    return app


def _screen(
    policy: Policy,
    metrics: Metrics,
    text: str,
    tools: list[str],
    byte_length: int,
    source: str,
    request_id: str,
) -> Decision:
    started = time.perf_counter()
    try:
        decision = policy.evaluate(text, tools, byte_length=byte_length, source=source)
    finally:
        metrics.duration.observe(time.perf_counter() - started)
    metrics.requests.labels(
        decision="allow" if decision.allow else "deny",
        source=source,
    ).inc()
    if not decision.allow:
        for category in sorted({item.category for item in decision.findings}):
            metrics.blocks.labels(category=category, source=source).inc()
    logger.info(
        "decision=%s source=%s bytes=%s codes=%s request_id=%s",
        "allow" if decision.allow else "deny",
        source,
        byte_length,
        ",".join(item.code for item in decision.findings),
        request_id,
    )
    return decision


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid json")
    return payload


def _tool_names(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="tools must be a list")
    if len(raw) > 8:
        raise HTTPException(status_code=400, detail="too many tools")
    names: list[str] = []
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            function = item.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                names.append(function["name"])
            elif isinstance(item.get("name"), str):
                names.append(item["name"])
            else:
                names.append("")
        else:
            names.append("")
    return names


def _message_text(payload: dict[str, Any]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    if len(messages) > 20:
        raise HTTPException(status_code=400, detail="too many messages")
    parts: list[str] = []
    for message in messages:
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            parts.append(message["content"])
    return "\n".join(parts)


def _finding_payload(decision: Decision) -> list[dict[str, object]]:
    return [
        {"category": item.category, "code": item.code, "score": round(item.score, 3)}
        for item in decision.findings
    ]


def _check_body(decision: Decision) -> dict[str, object]:
    return {
        "decision": "allow" if decision.allow else "deny",
        "findings": _finding_payload(decision),
        "redacted_text": decision.redacted_text,
    }


def _deny_body(decision: Decision) -> dict[str, object]:
    return {"detail": "denied", "findings": _finding_payload(decision)}


app = create_app()
