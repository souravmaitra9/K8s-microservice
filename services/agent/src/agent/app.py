import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import make_asgi_app
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.guard import GuardClient
from agent.llm import build_llm
from agent.metrics import build_metrics
from agent.orchestrator import Orchestrator
from agent.settings import Settings
from agent.tools import ToolClient

logger = logging.getLogger("agent")


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str = Field(pattern=r"^(user|assistant|system|tool)$")
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


def create_app(
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
    llm: object | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    metrics = build_metrics()
    http = httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(settings.llm_timeout, connect=settings.http_timeout),
        trust_env=False,
        follow_redirects=False,
        headers={"user-agent": "agent-platform/0.1"},
    )
    model = llm or build_llm(settings, http)
    orchestrator = Orchestrator(
        settings,
        model,
        GuardClient(settings.guardrail_url, http),
        ToolClient(settings, http),
        metrics,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Iterator[None]:
        yield
        http.close()

    app = FastAPI(title="agent", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.metrics = metrics
    app.mount("/metrics", make_asgi_app(registry=metrics.registry))

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

    @app.post("/v1/chat")
    def chat(request: Request) -> JSONResponse:
        started = time.perf_counter()
        status_label = "error"
        try:
            try:
                payload = json.loads(request.state.raw_body)
                model_in = ChatRequest.model_validate(payload)
            except (json.JSONDecodeError, ValidationError):
                status_label = "invalid"
                return JSONResponse(status_code=422, content={"detail": "invalid request"})
            messages = [item.model_dump() for item in model_in.messages]
            result = orchestrator.run(messages)
            status_label = _status_label(result.http_status, result.blocked)
            logger.info(
                "chat status=%s blocked=%s tools=%s request_id=%s",
                result.http_status,
                result.blocked,
                ",".join(item["name"] for item in result.tool_calls),
                request.state.request_id,
            )
            if result.http_status != 200:
                body: dict[str, object] = {"detail": result.message}
                if result.findings:
                    body["findings"] = result.findings
                return JSONResponse(status_code=result.http_status, content=body)
            ok: dict[str, object] = {
                "message": result.message,
                "tool_calls": result.tool_calls,
                "blocked": result.blocked,
                "usage": result.usage,
            }
            if result.findings:
                ok["findings"] = result.findings
            return JSONResponse(status_code=200, content=ok)
        finally:
            metrics.duration.observe(time.perf_counter() - started)
            metrics.requests.labels(status=status_label).inc()

    return app


def _status_label(http_status: int, blocked: bool) -> str:
    if http_status == 403:
        return "denied"
    if http_status >= 500:
        return "error"
    if http_status == 200 and blocked:
        return "blocked"
    if http_status == 200:
        return "ok"
    return "invalid"


app = create_app()
