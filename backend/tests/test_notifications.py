"""Iteration 4 - Notification channels + dispatch_event + theme (backend only).

Covers:
- Channel CRUD (admin) + RBAC (viewer 403)
- Per-type adapter test endpoint against httpbin.org/post (slack/teams/discord/webhook)
- Email channel error paths (missing api_key, missing to_email)
- Notification log endpoint
- Event dispatch on /triage P1/P2 incident_created
- Event dispatch on /incidents/{id}/resolve incident_resolved
- SLA breach via /alerts/unattended, dedup on second call
"""
import os
import time
import uuid
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
    "viewer": {"email": "viewer@triage.ai", "password": "viewer123"},
}
HTTPBIN = "https://httpbin.org/post"


def _login(who):
    r = requests.post(f"{API}/auth/login", json=CREDS[who], timeout=20)
    assert r.status_code == 200, f"login {who} failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _client(tok):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _client(_login("admin"))


@pytest.fixture(scope="module")
def sre1():
    return _client(_login("sre1"))


@pytest.fixture(scope="module")
def viewer():
    return _client(_login("viewer"))


# -------- Channel CRUD + RBAC --------
class TestChannelCRUD:
    def test_list_channels_any_role(self, viewer):
        r = viewer.get(f"{API}/notifications/channels", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_viewer_cannot_create(self, viewer):
        r = viewer.post(f"{API}/notifications/channels",
                        json={"name": "TEST_viewer_attempt", "type": "slack",
                              "config": {"webhook_url": HTTPBIN}, "triggers": ["incident_created"]},
                        timeout=15)
        assert r.status_code == 403

    def test_admin_create_patch_delete(self, admin):
        payload = {"name": f"TEST_ch_{uuid.uuid4().hex[:6]}", "type": "slack",
                   "config": {"webhook_url": HTTPBIN},
                   "triggers": ["incident_created", "sla_breach"], "enabled": True}
        r = admin.post(f"{API}/notifications/channels", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        ch = r.json()
        assert ch["id"].startswith("NCH-")
        assert ch["type"] == "slack"
        assert ch["config"]["webhook_url"] == HTTPBIN
        assert set(ch["triggers"]) == {"incident_created", "sla_breach"}
        assert ch["enabled"] is True
        assert ch["created_by"] == "admin@triage.ai"
        cid = ch["id"]

        # GET verifies persistence
        lst = admin.get(f"{API}/notifications/channels").json()
        assert any(c["id"] == cid for c in lst)

        # PATCH
        upd = dict(payload, name="TEST_ch_updated", enabled=False)
        r = admin.patch(f"{API}/notifications/channels/{cid}", json=upd, timeout=15)
        assert r.status_code == 200
        lst = admin.get(f"{API}/notifications/channels").json()
        m = next(c for c in lst if c["id"] == cid)
        assert m["name"] == "TEST_ch_updated"
        assert m["enabled"] is False

        # viewer DELETE forbidden
        rv = _client(_login("viewer")).delete(f"{API}/notifications/channels/{cid}")
        assert rv.status_code == 403

        # admin DELETE
        r = admin.delete(f"{API}/notifications/channels/{cid}", timeout=15)
        assert r.status_code == 200
        lst = admin.get(f"{API}/notifications/channels").json()
        assert not any(c["id"] == cid for c in lst)


# -------- Adapter test for slack/teams/discord/webhook via httpbin --------
@pytest.mark.parametrize("ch_type", ["slack", "teams", "discord", "webhook"])
def test_channel_test_endpoint_via_httpbin(admin, ch_type):
    payload = {"name": f"TEST_{ch_type}_{uuid.uuid4().hex[:5]}", "type": ch_type,
               "config": {"webhook_url": HTTPBIN},
               "triggers": ["incident_created"], "enabled": True}
    cid = admin.post(f"{API}/notifications/channels", json=payload, timeout=15).json()["id"]
    try:
        r = admin.post(f"{API}/notifications/channels/{cid}/test", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "ok", f"{ch_type} test got: {j}"
        # last_used_at + last_status persisted
        lst = admin.get(f"{API}/notifications/channels").json()
        m = next(c for c in lst if c["id"] == cid)
        assert m["last_status"] == "ok"
        assert m["last_used_at"]
    finally:
        admin.delete(f"{API}/notifications/channels/{cid}")


def test_slack_missing_webhook_url_returns_error(admin):
    payload = {"name": "TEST_slack_nourl", "type": "slack",
               "config": {}, "triggers": ["incident_created"], "enabled": True}
    cid = admin.post(f"{API}/notifications/channels", json=payload).json()["id"]
    try:
        r = admin.post(f"{API}/notifications/channels/{cid}/test", timeout=15)
        assert r.status_code == 200
        assert r.json()["status"].startswith("error:")
        assert "webhook_url missing" in r.json()["status"]
    finally:
        admin.delete(f"{API}/notifications/channels/{cid}")


# -------- Email channel error paths (no real Resend call) --------
class TestEmailChannel:
    def test_email_missing_api_key(self, admin):
        payload = {"name": "TEST_email_noapi", "type": "email",
                   "config": {"to_email": "x@y.com"}, "triggers": ["incident_created"]}
        cid = admin.post(f"{API}/notifications/channels", json=payload).json()["id"]
        try:
            r = admin.post(f"{API}/notifications/channels/{cid}/test", timeout=15)
            assert r.status_code == 200
            assert r.json()["status"] == "error: api_key missing"
        finally:
            admin.delete(f"{API}/notifications/channels/{cid}")

    def test_email_missing_to_email(self, admin):
        payload = {"name": "TEST_email_noto", "type": "email",
                   "config": {"api_key": "re_fake_key"}, "triggers": ["incident_created"]}
        cid = admin.post(f"{API}/notifications/channels", json=payload).json()["id"]
        try:
            r = admin.post(f"{API}/notifications/channels/{cid}/test", timeout=15)
            assert r.status_code == 200
            assert r.json()["status"] == "error: to_email missing"
        finally:
            admin.delete(f"{API}/notifications/channels/{cid}")

    def test_email_fake_api_key_graceful(self, admin):
        payload = {"name": "TEST_email_fake", "type": "email",
                   "config": {"api_key": "re_fake_key_will_fail",
                              "from_email": "onboarding@resend.dev",
                              "to_email": "test@example.com"},
                   "triggers": ["incident_created"]}
        cid = admin.post(f"{API}/notifications/channels", json=payload).json()["id"]
        try:
            r = admin.post(f"{API}/notifications/channels/{cid}/test", timeout=30)
            # Should not crash. Either returns 200 with error string in status
            assert r.status_code == 200, r.text
            assert r.json()["status"].startswith("error:")
        finally:
            admin.delete(f"{API}/notifications/channels/{cid}")


# -------- Notification log --------
def test_notification_log_endpoint(sre1):
    r = sre1.get(f"{API}/notifications/log?limit=10", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# -------- dispatch_event on triage P1/P2 --------
def _wait_for_log(client, channel_id, event, timeout=8):
    """Poll notification_log for an entry matching channel_id+event."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        logs = client.get(f"{API}/notifications/log?limit=50").json()
        for entry in logs:
            if entry.get("channel_id") == channel_id and entry.get("event") == event:
                return entry
        time.sleep(0.5)
    return None


class TestDispatchOnIncident:
    def test_incident_created_fires_dispatch(self, admin, sre1):
        # Create a fresh channel for this test that listens to incident_created
        payload = {"name": f"TEST_disp_created_{uuid.uuid4().hex[:5]}", "type": "slack",
                   "config": {"webhook_url": HTTPBIN},
                   "triggers": ["incident_created"], "enabled": True}
        cid = admin.post(f"{API}/notifications/channels", json=payload).json()["id"]
        try:
            # Seed and triage
            admin.post(f"{API}/seed", timeout=30)
            alerts = sre1.get(f"{API}/alerts").json()
            # Take 3 critical alerts to maximize P1/P2 chance
            crit = [a["id"] for a in alerts if a.get("severity") == "critical"][:3]
            if len(crit) < 2:
                crit = [a["id"] for a in alerts[:3]]
            r = sre1.post(f"{API}/triage", json={"alert_ids": crit}, timeout=180)
            assert r.status_code == 200, r.text
            tri = r.json()
            # Only fires if P1 or P2
            if tri.get("priority") not in ("P1", "P2"):
                pytest.skip(f"Triage produced {tri.get('priority')}, dispatch only for P1/P2")
            entry = _wait_for_log(admin, cid, "incident_created", timeout=10)
            assert entry is not None, "No log entry for incident_created within 10s"
            assert entry["status"] == "ok"
        finally:
            admin.delete(f"{API}/notifications/channels/{cid}")

    def test_incident_resolved_fires_dispatch(self, admin, sre1):
        payload = {"name": f"TEST_disp_resolved_{uuid.uuid4().hex[:5]}", "type": "slack",
                   "config": {"webhook_url": HTTPBIN},
                   "triggers": ["incident_resolved"], "enabled": True}
        cid = admin.post(f"{API}/notifications/channels", json=payload).json()["id"]
        try:
            admin.post(f"{API}/seed", timeout=30)
            alerts = sre1.get(f"{API}/alerts").json()
            ids = [a["id"] for a in alerts[:2]]
            tri = sre1.post(f"{API}/triage", json={"alert_ids": ids}, timeout=180).json()
            iid = tri["incident_id"]
            r = sre1.post(f"{API}/incidents/{iid}/resolve", timeout=15)
            assert r.status_code == 200
            entry = _wait_for_log(admin, cid, "incident_resolved", timeout=10)
            assert entry is not None, "No log entry for incident_resolved within 10s"
            assert entry["status"] == "ok"
        finally:
            admin.delete(f"{API}/notifications/channels/{cid}")


# -------- SLA breach dedup --------
class TestSlaBreach:
    def test_sla_breach_dispatch_and_dedup(self, admin):
        payload = {"name": f"TEST_sla_{uuid.uuid4().hex[:5]}", "type": "slack",
                   "config": {"webhook_url": HTTPBIN},
                   "triggers": ["sla_breach"], "enabled": True}
        cid = admin.post(f"{API}/notifications/channels", json=payload).json()["id"]
        try:
            admin.post(f"{API}/seed", timeout=30)
            aged = admin.post(f"{API}/demo/age-alerts", timeout=15).json()
            assert aged["aged"] == 3
            aged_ids = set(aged["ids"])

            # First call → should create sla_breach markers + dispatch
            r1 = admin.get(f"{API}/alerts/unattended", timeout=15)
            assert r1.status_code == 200
            time.sleep(4)  # let asyncio.create_task complete

            logs1 = admin.get(f"{API}/notifications/log?limit=100").json()
            first_entries = [e for e in logs1
                             if e.get("channel_id") == cid and e.get("event") == "sla_breach"]
            count1 = len(first_entries)
            assert count1 >= 1, "Expected at least 1 sla_breach dispatch on first call"

            # Second call → should NOT add more dispatches (per-alert dedup)
            admin.get(f"{API}/alerts/unattended", timeout=15)
            time.sleep(4)
            logs2 = admin.get(f"{API}/notifications/log?limit=100").json()
            second_entries = [e for e in logs2
                              if e.get("channel_id") == cid and e.get("event") == "sla_breach"]
            count2 = len(second_entries)
            assert count2 == count1, (
                f"SLA breach dedup failed: first call={count1}, second call={count2}, "
                f"aged_ids={aged_ids}"
            )
        finally:
            admin.delete(f"{API}/notifications/channels/{cid}")
