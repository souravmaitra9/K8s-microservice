from fastapi import FastAPI, Query
from prometheus_client import CollectorRegistry, Counter, make_asgi_app

from kb.search import search_runbooks


def create_app() -> FastAPI:
    registry = CollectorRegistry()
    requests = Counter(
        "kb_requests_total",
        "Search requests.",
        registry=registry,
    )
    app = FastAPI(title="kb", version="0.1.0")
    app.mount("/metrics", make_asgi_app(registry=registry))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/search")
    def search(q: str = Query(default="", max_length=200)) -> dict[str, list[dict[str, str]]]:
        requests.inc()
        return {"results": search_runbooks(q)}

    return app


app = create_app()
