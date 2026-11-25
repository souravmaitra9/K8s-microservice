import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_alert_rules_cover_the_recorded_metrics() -> None:
    document = yaml.safe_load((ROOT / "deploy/helm/agent-platform/files/alerts.yaml").read_text())
    rules = document["groups"][0]["rules"]
    blob = "\n".join(rule["expr"] for rule in rules)
    for metric in (
        "agent_request_duration_seconds_bucket",
        "agent_llm_tokens_total",
        "guardrail_blocks_total",
        "guardrail_requests_total",
        "agent_tool_calls_total",
        "agent_tool_steps_exhausted_total",
        "agent_requests_total",
    ):
        assert metric in blob
    for rule in rules:
        assert rule["labels"]["severity"]
        assert rule["annotations"]["summary"]


def test_grafana_dashboard_uses_the_same_metrics() -> None:
    dashboard = json.loads((ROOT / "deploy/grafana/agent-platform.json").read_text())
    exprs = [target["expr"] for panel in dashboard["panels"] for target in panel["targets"]]
    blob = "\n".join(exprs)
    assert len(dashboard["panels"]) == 6
    for metric in (
        "agent_request_duration_seconds_bucket",
        "agent_requests_total",
        "agent_llm_tokens_total",
        "guardrail_blocks_total",
        "agent_tool_calls_total",
        "guardrail_requests_total",
    ):
        assert metric in blob


def test_kyverno_and_falco_policies_parse() -> None:
    policies = list((ROOT / "policy/kyverno").glob("*.yaml"))
    assert len(policies) >= 4
    for path in policies:
        document = yaml.safe_load(path.read_text())
        assert document["kind"] == "ClusterPolicy"
        assert document["spec"]["rules"]
    rules = yaml.safe_load((ROOT / "policy/falco/agent-platform.yaml").read_text())
    named = [item for item in rules if "rule" in item]
    assert len(named) >= 4
    for item in named:
        assert item["condition"]
        assert item["priority"]
        assert item["output"]
