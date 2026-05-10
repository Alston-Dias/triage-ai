"""TriageAI backend regression tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback: read frontend env directly
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def seeded(client):
    r = client.post(f"{API}/seed", timeout=30)
    assert r.status_code == 200
    assert r.json().get("seeded") == 10
    return True


# Health
def test_root(client):
    r = client.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["service"] == "TriageAI"
    assert j["status"] == "operational"


# Seed + list alerts
def test_seed_and_list_alerts(client, seeded):
    r = client.get(f"{API}/alerts", timeout=15)
    assert r.status_code == 200
    alerts = r.json()
    assert len(alerts) == 10
    a = alerts[0]
    for k in ["id", "source", "severity", "service", "region", "title", "status", "timestamp"]:
        assert k in a
    assert a["status"] == "active"
    assert "_id" not in a


# Custom ingest
def test_ingest_custom_alert(client, seeded):
    payload = {"source": "datadog", "severity": "high", "service": "TEST_svc",
               "region": "us-east-1", "title": "TEST_ingest"}
    r = client.post(f"{API}/alerts/ingest", json=payload, timeout=15)
    assert r.status_code == 200
    a = r.json()
    assert a["service"] == "TEST_svc"
    assert a["id"].startswith("ALT-")


# Simulate
def test_simulate_alert(client, seeded):
    r = client.post(f"{API}/alerts/simulate", timeout=15)
    assert r.status_code == 200
    assert r.json()["id"].startswith("ALT-")


# Resolve single
def test_resolve_single_alert(client, seeded):
    alerts = client.get(f"{API}/alerts").json()
    aid = alerts[-1]["id"]
    r = client.patch(f"{API}/alerts/{aid}/resolve", timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    # verify
    r2 = client.get(f"{API}/alerts?status=resolved", timeout=15)
    assert any(x["id"] == aid for x in r2.json())


def test_resolve_alert_not_found(client):
    r = client.patch(f"{API}/alerts/ALT-NONEXIST/resolve", timeout=15)
    assert r.status_code == 404


# Triage flow + linked incident
@pytest.fixture(scope="session")
def triaged(client, seeded):
    # re-seed to ensure 10 active
    client.post(f"{API}/seed", timeout=30)
    alerts = client.get(f"{API}/alerts").json()
    ids = [a["id"] for a in alerts[:4]]
    r = client.post(f"{API}/triage", json={"alert_ids": ids}, timeout=120)
    assert r.status_code == 200, r.text
    return r.json(), ids


def test_triage_structure(triaged):
    triage, ids = triaged
    assert triage["priority"] in ["P1", "P2", "P3", "P4"]
    assert isinstance(triage["mttr_estimate_minutes"], int)
    assert triage["summary"]
    assert len(triage["root_causes"]) >= 1
    assert len(triage["remediation"]) >= 3
    phases = {s["phase"] for s in triage["remediation"]}
    assert phases & {"immediate", "short-term", "long-term"}
    assert triage["incident_id"].startswith("INC-")
    assert triage["id"].startswith("TRG-")
    assert set(triage["alert_ids"]) == set(ids)


def test_triage_creates_incident(client, triaged):
    triage, _ = triaged
    r = client.get(f"{API}/incidents", timeout=15)
    assert r.status_code == 200
    incs = r.json()
    assert any(i["id"] == triage["incident_id"] for i in incs)


def test_incident_detail(client, triaged):
    triage, _ = triaged
    r = client.get(f"{API}/incidents/{triage['incident_id']}", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["incident"]["id"] == triage["incident_id"]
    assert j["triage"]["id"] == triage["id"]
    assert len(j["alerts"]) >= 1


def test_triage_no_alerts(client):
    r = client.post(f"{API}/triage", json={"alert_ids": []}, timeout=30)
    assert r.status_code == 400


# Bulk resolve + linked incident resolution
def test_resolve_bulk_and_incidents(client, triaged):
    triage, ids = triaged
    r = client.post(f"{API}/alerts/resolve-bulk", json={"alert_ids": ids}, timeout=15)
    assert r.status_code == 200
    assert r.json()["resolved"] == len(ids)
    # incident should now be resolved
    inc = client.get(f"{API}/incidents/{triage['incident_id']}").json()["incident"]
    assert inc["status"] == "resolved"
    assert inc["resolved_at"]


# Analytics
def test_analytics_summary(client):
    r = client.get(f"{API}/analytics/summary", timeout=15)
    assert r.status_code == 200
    j = r.json()
    for k in ["totals", "by_source", "by_severity", "mttr_trend", "top_incidents"]:
        assert k in j
    assert len(j["mttr_trend"]) == 7
    sevs = {x["severity"] for x in j["by_severity"]}
    assert {"critical", "high", "medium", "low"} <= sevs
    for k in ["alerts", "active_alerts", "incidents", "open_incidents"]:
        assert k in j["totals"]
