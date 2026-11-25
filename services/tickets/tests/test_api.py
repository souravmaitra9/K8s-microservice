from fastapi.testclient import TestClient

from tickets.app import create_app


def test_create_and_fetch() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/v1/tickets",
        json={"title": "payments latency", "severity": "sev2", "summary": "p95 crossed 2s"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["id"].startswith("INC-")
    assert body["severity"] == "sev2"
    fetched = client.get(f"/v1/tickets/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "payments latency"


def test_rejects_bad_severity_and_unknown_ids() -> None:
    client = TestClient(create_app())
    rejected = client.post(
        "/v1/tickets",
        json={"title": "x", "severity": "critical", "summary": "nope"},
    )
    assert rejected.status_code == 422
    assert client.get("/v1/tickets/not-an-id").status_code == 404
    assert client.get("/v1/tickets/INC-00000000").status_code == 404
