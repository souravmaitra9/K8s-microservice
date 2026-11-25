from fastapi.testclient import TestClient

from kb.app import create_app
from kb.search import search_runbooks


def test_crashloop_ranks_first() -> None:
    hits = search_runbooks("CrashLoopBackOff after the deploy")
    assert hits
    assert hits[0]["id"] == "crashloop"
    assert hits[0]["title"] == "CrashLoopBackOff"


def test_empty_and_unknown_queries() -> None:
    assert search_runbooks("  ") == []
    assert search_runbooks("the and for") == []
    assert search_runbooks("zephyr") == []


def test_disk_pressure_matches() -> None:
    hits = search_runbooks("node disk pressure")
    assert hits[0]["id"] == "disk-pressure"


def test_api_bounds_the_query() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/search", params={"q": "kafka lag"})
    assert response.status_code == 200
    assert response.json()["results"][0]["id"] == "kafka-lag"
    too_long = client.get("/v1/search", params={"q": "k" * 201})
    assert too_long.status_code == 422
