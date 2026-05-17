"""Backend tests for SonarQube issue workflow (detail/claim/assign/status).

Covers the new endpoints added in this iteration:
  - GET   /api/sonarqube/issues                 (extended fields)
  - GET   /api/sonarqube/issues/{key}           (auth required)
  - POST  /api/sonarqube/issues/{key}/claim     (auth required)
  - POST  /api/sonarqube/issues/{key}/assign    (auth required)
  - PATCH /api/sonarqube/issues/{key}/status    (auth required)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://file-share-center.preview.emergentagent.com").rstrip("/")
ISSUE_KEY = "AYxyz123"
UNKNOWN_KEY = "DOESNOTEXIST"


# ----------------------- fixtures -----------------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@triage.ai", "password": "admin123"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def sre_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "sre1@triage.ai", "password": "sre123"})
    assert r.status_code == 200, f"sre1 login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_issue_state(admin_token):
    """Reset the issue to OPEN/unassigned before each test via PATCH status=OPEN."""
    for key in ["AYxyz123", "AYxyz124", "AYxyz125", "AYxyz126"]:
        requests.patch(
            f"{BASE_URL}/api/sonarqube/issues/{key}/status",
            json={"status": "OPEN"},
            headers=_auth(admin_token),
        )
    yield


# ----------------------- list (extended fields) -----------------------
class TestSonarIssuesList:
    def test_list_returns_extended_fields(self):
        r = requests.get(f"{BASE_URL}/api/sonarqube/issues")
        assert r.status_code == 200
        data = r.json()
        assert "issues" in data and isinstance(data["issues"], list)
        assert data["total"] == len(data["issues"])
        sample = next((i for i in data["issues"] if i["key"] == ISSUE_KEY), None)
        assert sample is not None, "Expected issue AYxyz123 in list"
        for field in ("title", "description", "rule", "suggestedFix", "assignee", "status", "severity", "component"):
            assert field in sample, f"missing field {field}"
        assert sample["status"] in ["OPEN", "CLAIMED", "IN_PROGRESS", "FIXED"]


# ----------------------- detail -----------------------
class TestSonarIssueDetail:
    def test_detail_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}")
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_detail_ok(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}", headers=_auth(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["key"] == ISSUE_KEY
        assert data["title"]
        assert data["description"]
        assert data["rule"]
        assert data["suggestedFix"]

    def test_detail_unknown_returns_404(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/sonarqube/issues/{UNKNOWN_KEY}", headers=_auth(admin_token))
        assert r.status_code == 404


# ----------------------- claim -----------------------
class TestSonarClaim:
    def test_claim_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/claim")
        assert r.status_code in (401, 403)

    def test_claim_sets_assignee_and_status(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/claim", headers=_auth(admin_token))
        assert r.status_code == 200
        data = r.json()
        assert data["assignee"] == "admin@triage.ai"
        assert data["status"] == "CLAIMED"

        # Verify persistence via GET detail
        g = requests.get(f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}", headers=_auth(admin_token))
        assert g.status_code == 200
        gd = g.json()
        assert gd["assignee"] == "admin@triage.ai"
        assert gd["status"] == "CLAIMED"

    def test_claim_unknown_issue_404(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/sonarqube/issues/{UNKNOWN_KEY}/claim", headers=_auth(admin_token))
        assert r.status_code == 404


# ----------------------- assign -----------------------
class TestSonarAssign:
    def test_assign_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/assign",
            json={"email": "sre1@triage.ai"},
        )
        assert r.status_code in (401, 403)

    def test_assign_sets_assignee_and_bumps_open_to_claimed(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/assign",
            json={"email": "sre1@triage.ai"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["assignee"] == "sre1@triage.ai"
        assert data["status"] == "CLAIMED"  # OPEN bumped to CLAIMED

        # Verify via GET
        g = requests.get(f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}", headers=_auth(admin_token))
        assert g.json()["assignee"] == "sre1@triage.ai"

    def test_assign_unknown_user_returns_404(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/assign",
            json={"email": "nobody@triage.ai"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404

    def test_assign_unknown_issue_returns_404(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/sonarqube/issues/{UNKNOWN_KEY}/assign",
            json={"email": "sre1@triage.ai"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404


# ----------------------- status -----------------------
class TestSonarStatus:
    def test_status_requires_auth(self):
        r = requests.patch(
            f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/status",
            json={"status": "IN_PROGRESS"},
        )
        assert r.status_code in (401, 403)

    @pytest.mark.parametrize("status", ["CLAIMED", "IN_PROGRESS", "FIXED"])
    def test_status_valid_values(self, admin_token, status):
        r = requests.patch(
            f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/status",
            json={"status": status},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        assert r.json()["status"] == status

    def test_status_invalid_returns_400(self, admin_token):
        r = requests.patch(
            f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/status",
            json={"status": "WONTFIX"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 400

    def test_status_open_clears_assignee(self, admin_token):
        # First claim
        c = requests.post(f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/claim", headers=_auth(admin_token))
        assert c.status_code == 200
        assert c.json()["assignee"] == "admin@triage.ai"

        # Now set to OPEN
        r = requests.patch(
            f"{BASE_URL}/api/sonarqube/issues/{ISSUE_KEY}/status",
            json={"status": "OPEN"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "OPEN"
        assert body["assignee"] is None

    def test_status_unknown_issue_returns_404(self, admin_token):
        r = requests.patch(
            f"{BASE_URL}/api/sonarqube/issues/{UNKNOWN_KEY}/status",
            json={"status": "FIXED"},
            headers=_auth(admin_token),
        )
        assert r.status_code == 404
