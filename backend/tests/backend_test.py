"""TriageAI backend regression tests (iteration 2 - JWT auth + new features)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin":  {"email": "admin@triage.ai",  "password": "admin123"},
    "sre1":   {"email": "sre1@triage.ai",   "password": "sre123"},
    "sre2":   {"email": "sre2@triage.ai",   "password": "sre123"},
    "viewer": {"email": "viewer@triage.ai", "password": "viewer123"},
}


def _login(who):
    r = requests.post(f"{API}/auth/login", json=CREDS[who], timeout=20)
    assert r.status_code == 200, f"login {who} failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def admin_token():
    return _login("admin")["access_token"]


@pytest.fixture(scope="session")
def sre1_token():
    return _login("sre1")["access_token"]


@pytest.fixture(scope="session")
def sre2_token():
    return _login("sre2")["access_token"]


def _client(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# -------------------- AUTH --------------------
class TestAuth:
    def test_login_success(self):
        r = requests.post(f"{API}/auth/login", json=CREDS["sre1"], timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert "access_token" in j and isinstance(j["access_token"], str) and len(j["access_token"]) > 20
        assert j.get("token_type") == "bearer"
        assert j["user"]["email"] == "sre1@triage.ai"
        assert j["user"]["name"] == "Alex Chen"
        assert j["user"]["role"] == "on-call"
        assert "password_hash" not in j["user"]
        assert "_id" not in j["user"]

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "sre1@triage.ai", "password": "wrong"}, timeout=20)
        assert r.status_code == 401

    def test_login_unknown_user(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "ghost@triage.ai", "password": "x"}, timeout=20)
        assert r.status_code == 401

    def test_me_with_token(self, sre1_token):
        c = _client(sre1_token)
        r = c.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        u = r.json()
        assert u["email"] == "sre1@triage.ai"
        assert u["name"] == "Alex Chen"
        assert u["role"] == "on-call"
        assert "password_hash" not in u

    def test_me_no_token(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401

    def test_me_bad_token(self):
        r = requests.get(f"{API}/auth/me",
                         headers={"Authorization": "Bearer not.a.jwt"}, timeout=15)
        assert r.status_code == 401

    def test_users_list(self, admin_token):
        c = _client(admin_token)
        r = c.get(f"{API}/auth/users", timeout=15)
        assert r.status_code == 200
        users = r.json()
        emails = {u["email"] for u in users}
        assert {"admin@triage.ai", "sre1@triage.ai", "sre2@triage.ai", "viewer@triage.ai"} <= emails
        for u in users:
            assert "password_hash" not in u
            assert "_id" not in u

    def test_protected_endpoint_requires_token(self):
        r = requests.get(f"{API}/alerts", timeout=15)
        assert r.status_code == 401


# -------------------- SOURCES --------------------
class TestSources:
    def test_default_sources(self, admin_token):
        c = _client(admin_token)
        r = c.get(f"{API}/sources", timeout=15)
        assert r.status_code == 200
        srcs = r.json()
        assert len(srcs) >= 4
        names = {s["name"] for s in srcs}
        assert {"AWS CloudWatch", "Datadog Production", "PagerDuty V2", "Grafana 9"} <= names

    def test_source_crud(self, admin_token):
        c = _client(admin_token)
        r = c.post(f"{API}/sources",
                   json={"name": "TEST_src", "type": "custom", "enabled": True}, timeout=15)
        assert r.status_code == 200
        src = r.json()
        sid = src["id"]
        assert sid.startswith("SRC-")
        assert src["enabled"] is True

        # toggle
        r = c.patch(f"{API}/sources/{sid}", timeout=15)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        # verify GET reflects toggle
        srcs = c.get(f"{API}/sources").json()
        match = next((s for s in srcs if s["id"] == sid), None)
        assert match and match["enabled"] is False

        # delete
        r = c.delete(f"{API}/sources/{sid}", timeout=15)
        assert r.status_code == 200
        srcs = c.get(f"{API}/sources").json()
        assert not any(s["id"] == sid for s in srcs)


# -------------------- INCIDENTS FLOW --------------------
@pytest.fixture(scope="session")
def seeded(sre1_token):
    c = _client(sre1_token)
    r = c.post(f"{API}/seed", timeout=30)
    assert r.status_code == 200
    assert r.json()["seeded"] == 10
    return True


@pytest.fixture(scope="session")
def triaged_incident(sre1_token, seeded):
    """sre1 runs triage to create an incident."""
    c = _client(sre1_token)
    alerts = c.get(f"{API}/alerts").json()
    ids = [a["id"] for a in alerts[:3]]
    r = c.post(f"{API}/triage", json={"alert_ids": ids}, timeout=180)
    assert r.status_code == 200, r.text
    triage = r.json()
    return triage, ids


class TestIncidentFlow:
    def test_triage_sets_created_by(self, sre1_token, triaged_incident):
        triage, _ = triaged_incident
        c = _client(sre1_token)
        r = c.get(f"{API}/incidents/{triage['incident_id']}", timeout=15)
        assert r.status_code == 200
        inc = r.json()["incident"]
        assert inc["created_by"] == "sre1@triage.ai"
        assert inc["status"] in ("triaging", "in_progress", "open")

    def test_pickup_by_sre2(self, sre2_token, triaged_incident):
        triage, _ = triaged_incident
        c = _client(sre2_token)
        r = c.post(f"{API}/incidents/{triage['incident_id']}/pickup", timeout=15)
        assert r.status_code == 200
        assert r.json()["assignee"] == "sre2@triage.ai"

        inc = c.get(f"{API}/incidents/{triage['incident_id']}").json()["incident"]
        assert inc["assignee"] == "sre2@triage.ai"
        assert inc["status"] == "in_progress"
        assert any("picked up" in u["text"].lower() for u in inc["updates"])

    def test_add_collaborator(self, sre2_token, triaged_incident):
        triage, _ = triaged_incident
        c = _client(sre2_token)
        r = c.post(f"{API}/incidents/{triage['incident_id']}/collaborators",
                   json={"email": "sre1@triage.ai"}, timeout=15)
        assert r.status_code == 200
        inc = c.get(f"{API}/incidents/{triage['incident_id']}").json()["incident"]
        assert "sre1@triage.ai" in inc["collaborators"]
        assert any("collaborator" in u["text"].lower() for u in inc["updates"])

    def test_post_update(self, sre2_token, triaged_incident):
        triage, _ = triaged_incident
        c = _client(sre2_token)
        r = c.post(f"{API}/incidents/{triage['incident_id']}/updates",
                   json={"text": "TEST_custom note from sre2"}, timeout=15)
        assert r.status_code == 200
        u = r.json()
        assert u["user_email"] == "sre2@triage.ai"
        assert "TEST_custom note" in u["text"]

    def test_scope_mine_vs_others(self, sre1_token, sre2_token, triaged_incident):
        triage, _ = triaged_incident
        iid = triage["incident_id"]
        c1 = _client(sre1_token)
        c2 = _client(sre2_token)

        mine_sre1 = c1.get(f"{API}/incidents?scope=mine").json()
        assert any(i["id"] == iid for i in mine_sre1), "sre1 (creator+collab) should see in mine"

        mine_sre2 = c2.get(f"{API}/incidents?scope=mine").json()
        assert any(i["id"] == iid for i in mine_sre2), "sre2 (assignee) should see in mine"

        others_sre1 = c1.get(f"{API}/incidents?scope=others").json()
        assert not any(i["id"] == iid for i in others_sre1)

    def test_resolve_incident(self, sre2_token, triaged_incident):
        triage, alert_ids = triaged_incident
        iid = triage["incident_id"]
        c = _client(sre2_token)
        r = c.post(f"{API}/incidents/{iid}/resolve", timeout=15)
        assert r.status_code == 200
        inc = c.get(f"{API}/incidents/{iid}").json()["incident"]
        assert inc["status"] == "resolved"
        assert inc["resolved_at"]
        alerts = c.get(f"{API}/alerts?status=resolved").json()
        resolved_ids = {a["id"] for a in alerts}
        assert set(alert_ids) <= resolved_ids


# -------------------- CHAT --------------------
@pytest.fixture(scope="session")
def fresh_incident_for_chat(sre1_token):
    c = _client(sre1_token)
    c.post(f"{API}/seed", timeout=30)
    alerts = c.get(f"{API}/alerts").json()
    ids = [a["id"] for a in alerts[:2]]
    r = c.post(f"{API}/triage", json={"alert_ids": ids}, timeout=180)
    assert r.status_code == 200
    return r.json()


class TestChat:
    def test_initial_history_empty(self, sre1_token, fresh_incident_for_chat):
        iid = fresh_incident_for_chat["incident_id"]
        c = _client(sre1_token)
        r = c.get(f"{API}/incidents/{iid}/chat", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["incident_id"] == iid
        assert j["messages"] == []

    def test_send_chat_message(self, sre1_token, fresh_incident_for_chat):
        iid = fresh_incident_for_chat["incident_id"]
        c = _client(sre1_token)
        r = c.post(f"{API}/incidents/{iid}/chat",
                   json={"text": "What is the most likely root cause?"}, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["user_message"]["role"] == "user"
        assert j["user_message"]["user_email"] == "sre1@triage.ai"
        assert j["assistant_message"]["role"] == "assistant"
        assert isinstance(j["assistant_message"]["text"], str)
        assert len(j["assistant_message"]["text"]) > 0

        h = c.get(f"{API}/incidents/{iid}/chat").json()
        assert len(h["messages"]) >= 2
        assert h["messages"][0]["role"] == "user"
        assert h["messages"][1]["role"] == "assistant"

    def test_chat_blocked_after_resolve(self, sre1_token, sre2_token, fresh_incident_for_chat):
        iid = fresh_incident_for_chat["incident_id"]
        c2 = _client(sre2_token)
        r = c2.post(f"{API}/incidents/{iid}/resolve", timeout=15)
        assert r.status_code == 200

        c1 = _client(sre1_token)
        r = c1.post(f"{API}/incidents/{iid}/chat",
                    json={"text": "anything"}, timeout=30)
        assert r.status_code == 400


# -------------------- UNATTENDED ALERTS --------------------
class TestUnattended:
    def test_age_alerts_and_unattended(self, admin_token):
        c = _client(admin_token)
        c.post(f"{API}/seed", timeout=30)
        r = c.post(f"{API}/demo/age-alerts", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["aged"] == 3
        assert len(j["ids"]) == 3

        r = c.get(f"{API}/alerts/unattended", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["threshold_days"] == 5
        assert j["count"] >= 3
        assert len(j["alerts"]) >= 3
