import re

from fastapi import FastAPI, HTTPException
from prometheus_client import CollectorRegistry, Counter, make_asgi_app
from pydantic import BaseModel, Field

from tickets.store import Store

_ID = re.compile(r"^INC-[0-9a-f]{8}$")


class TicketIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    severity: str = Field(pattern=r"^sev[1-4]$")
    summary: str = Field(min_length=1, max_length=2000)


def create_app(store: Store | None = None) -> FastAPI:
    store = store or Store()
    registry = CollectorRegistry()
    created = Counter("tickets_created_total", "Tickets opened.", registry=registry)
    app = FastAPI(title="tickets", version="0.1.0")
    app.state.store = store
    app.mount("/metrics", make_asgi_app(registry=registry))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/tickets", status_code=201)
    def create(body: TicketIn) -> dict[str, str]:
        ticket = store.add(body.title.strip(), body.severity, body.summary.strip())
        created.inc()
        return ticket.as_dict()

    @app.get("/v1/tickets/{ticket_id}")
    def fetch(ticket_id: str) -> dict[str, str]:
        if _ID.fullmatch(ticket_id) is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        ticket = store.get(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        return ticket.as_dict()

    return app


app = create_app()
