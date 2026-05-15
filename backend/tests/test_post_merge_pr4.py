"""
Post-merge regression suite for PR #4 (Predictive Triage + SonarQube AI Chat).
Verifies BOTH features coexist after conflict resolution.
"""
import os
import json
import pytest
import requests
import websockets
import asyncio

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"
WS = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws/predictive-alerts"

ADMIN = {"email": "admin@triage.ai", "password": "admin123"}


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============== AUTH REGRESSION ==============
class TestAuthRegression:
    def test_login_admin(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "access_token" in d and len(d["access_token"]) > 20
        assert d["user"]["email"] == "admin@triage.ai"

    def test_protected_requires_auth(self):
        r = requests.get(f"{API}/predictive-services/summary", timeout=15)
        assert r.status_code in (401, 403)

    def test_sonar_detail_requires_auth(self):
        # Detail endpoint is protected; read-only summary/issues/quality-gate are intentionally public for the dashboard
        r = requests.get(f"{API}/sonarqube/issues/AYxyz123", timeout=15)
        assert r.status_code in (401, 403)


# ============== PRE-EXISTING ROUTES REGRESSION ==============
class TestPreExistingRoutes:
    def test_alerts(self, auth_headers):
        r = requests.get(f"{API}/alerts", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_incidents(self, auth_headers):
        r = requests.get(f"{API}/incidents", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_sources(self, auth_headers):
        r = requests.get(f"{API}/sources", headers=auth_headers, timeout=15)
        assert r.status_code == 200

    def test_analytics_summary(self, auth_headers):
        r = requests.get(f"{API}/analytics/summary", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)


# ============== F-02 PREDICTIVE TRIAGE ==============
class TestPredictive:
    EXPECTED_SERVICES = {"payments-api", "auth-service", "checkout-svc", "search-api", "notifications-worker"}

    def test_predictive_services_summary(self, auth_headers):
        r = requests.get(f"{API}/predictive-services/summary", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        services = d if isinstance(d, list) else d.get("services", [])
        assert len(services) == 5
        # service identifier key is 'service_name'
        names = {s.get("service_name") or s.get("service") for s in services}
        assert names == self.EXPECTED_SERVICES
        for s in services:
            for k in ("max_risk", "avg_risk", "predictions", "min_eta"):
                assert k in s, f"missing {k} in {s}"

    def test_list_predictive_incidents(self, auth_headers):
        r = requests.get(f"{API}/predictive-incidents?status=open", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        prd = [i for i in items if str(i.get("id", "")).startswith("PRD-")]
        assert len(prd) >= 1
        first = prd[0]
        for k in ("id", "service_name", "risk_score", "status"):
            assert k in first

    def test_run_predictive_triage(self, auth_headers):
        r = requests.post(f"{API}/predictive-triage", headers=auth_headers, json={}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # Accept various response shapes — must include count/generated/predictions key
        assert any(k in d for k in ("generated", "count", "predictions", "incidents"))

    def test_incident_trend(self, auth_headers):
        r = requests.get(f"{API}/predictive-incidents?status=open", headers=auth_headers, timeout=15)
        items = r.json()
        if not items:
            pytest.skip("no predictive incidents")
        inc_id = items[0]["id"]
        r = requests.get(f"{API}/predictive-incidents/{inc_id}/trend?points=60", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # series may be list or dict containing list
        series = d if isinstance(d, list) else (d.get("series") or d.get("points") or d.get("data") or [])
        assert isinstance(series, list)
        assert len(series) >= 1

    def test_acknowledge_and_resolve(self, auth_headers):
        r = requests.get(f"{API}/predictive-incidents?status=open", headers=auth_headers, timeout=15)
        items = r.json()
        if not items:
            pytest.skip("no predictive incidents")
        inc_id = items[0]["id"]
        ack = requests.patch(f"{API}/predictive-incidents/{inc_id}/acknowledge", headers=auth_headers, timeout=15)
        assert ack.status_code == 200
        ack_data = ack.json()
        assert ack_data.get("status") in ("acknowledged", "ack", "ACKNOWLEDGED")
        res = requests.patch(f"{API}/predictive-incidents/{inc_id}/resolve", headers=auth_headers, timeout=15)
        assert res.status_code == 200
        assert res.json().get("status") in ("resolved", "RESOLVED")

    def test_websocket_predictive_alerts(self, token):
        async def _run():
            try:
                async with websockets.connect(WS, additional_headers={"Authorization": f"Bearer {token}"}, open_timeout=10) as ws:
                    msg = await asyncio.wait_for(ws.recv(), timeout=8)
                    return json.loads(msg)
            except TypeError:
                # older websockets versions
                async with websockets.connect(WS + f"?token={token}", open_timeout=10) as ws:
                    msg = await asyncio.wait_for(ws.recv(), timeout=8)
                    return json.loads(msg)
        result = asyncio.get_event_loop().run_until_complete(_run()) if False else asyncio.run(_run())
        assert isinstance(result, dict)
        # WebSocket emits {event: 'snapshot', data: [...]}
        assert ("event" in result and result["event"] == "snapshot") or "type" in result or "service" in result or "services" in result or "data" in result


# ============== SONARQUBE ==============
class TestSonarQube:
    def test_sonar_summary(self, auth_headers):
        r = requests.get(f"{API}/sonarqube/summary", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # metrics is nested
        m = d.get("metrics", d)
        for k in ("bugs", "vulnerabilities", "codeSmells", "coverage", "duplications", "lines", "sqaleRating"):
            assert k in m, f"missing metric {k}"

    def test_sonar_issues_list(self, auth_headers):
        r = requests.get(f"{API}/sonarqube/issues", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 4
        assert len(d["issues"]) == 4
        for k in ("buckets", "breakdown", "technical_debt_minutes", "severityBreakdown"):
            assert k in d

    def test_sonar_issue_detail(self, auth_headers):
        r = requests.get(f"{API}/sonarqube/issues/AYxyz123", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("key", "severity", "status", "rule", "component"):
            assert k in d

    def test_sonar_claim(self, auth_headers):
        # reset first
        requests.patch(f"{API}/sonarqube/issues/AYxyz124/status", headers=auth_headers, json={"status": "OPEN"}, timeout=15)
        r = requests.post(f"{API}/sonarqube/issues/AYxyz124/claim", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] in ("IN_PROGRESS", "CLAIMED")
        assert d.get("assignee") is not None

    def test_sonar_assign(self, auth_headers):
        r = requests.post(
            f"{API}/sonarqube/issues/AYxyz125/assign",
            headers=auth_headers,
            json={"email": "sre1@triage.ai"},
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        a = d.get("assignee") or {}
        # accept dict or string
        if isinstance(a, dict):
            assert a.get("email") == "sre1@triage.ai" or a.get("login") == "sre1@triage.ai"
        else:
            assert "sre1" in str(a)

    def test_sonar_status_transitions(self, auth_headers):
        for s in ("IN_PROGRESS", "FIXED", "WONT_FIX", "OPEN"):
            r = requests.patch(
                f"{API}/sonarqube/issues/AYxyz123/status",
                headers=auth_headers,
                json={"status": s},
                timeout=15,
            )
            assert r.status_code == 200, f"status {s}: {r.text}"
            assert r.json()["status"] == s

    def test_quality_gate(self, auth_headers):
        r = requests.get(f"{API}/sonarqube/quality-gate", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "conditions" in d or "status" in d

    def test_generate_fix(self, auth_headers):
        r = requests.post(f"{API}/sonarqube/issues/AYxyz126/generate-fix", headers=auth_headers, json={}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        for k in ("confidence", "explanation"):
            assert k in d, f"missing {k}"
        # unified diff key may be 'patch' or 'diff' or 'unified_diff'
        patch = d.get("patch") or d.get("diff") or d.get("unified_diff") or ""
        assert isinstance(patch, str)

    def test_comments_list_and_post(self, auth_headers):
        # list initial
        r = requests.get(f"{API}/sonarqube/issues/AYxyz123/comments", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        before = r.json()
        before_count = len(before) if isinstance(before, list) else len(before.get("comments", []))
        # add
        r = requests.post(
            f"{API}/sonarqube/issues/AYxyz123/comments",
            headers=auth_headers,
            json={"text": "TEST_post_merge_comment"},
            timeout=15,
        )
        assert r.status_code in (200, 201)
        # re-list
        r = requests.get(f"{API}/sonarqube/issues/AYxyz123/comments", headers=auth_headers, timeout=15)
        after = r.json()
        after_count = len(after) if isinstance(after, list) else len(after.get("comments", []))
        assert after_count == before_count + 1

    @pytest.mark.parametrize("intent", ["explain", "suggest_fix", "refactor", "severity", "best_practices"])
    def test_sonar_ai_chat(self, auth_headers, intent):
        r = requests.post(
            f"{API}/sonarqube/issues/AYxyz126/chat",
            headers=auth_headers,
            json={"text": "test", "intent": intent},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        am = d.get("assistant_message") or {}
        reply = am.get("text") if isinstance(am, dict) else am
        if not reply:
            reply = d.get("reply") or d.get("message") or ""
        assert isinstance(reply, str) and len(reply) > 0
