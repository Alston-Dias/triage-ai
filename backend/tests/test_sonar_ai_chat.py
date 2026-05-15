"""
Backend tests for SonarQube AI Remediation Assistant chat endpoints.
- GET /api/sonarqube/issues/{key}/chat
- POST /api/sonarqube/issues/{key}/chat
Covers: auth, 400/404, 5 intents, intent fallback, code block in suggest_fix,
severity reply mentions actual severity, history persistence.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://sonar-integration.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@triage.ai"
ADMIN_PASS = "admin123"

INTENTS = ["explain", "suggest_fix", "refactor", "severity", "best_practices"]
ISSUE_KEY_BUG_MAJOR = "AYxyz126"
ISSUE_KEY_SMELL = "AYxyz123"
UNKNOWN_KEY = "AYZZZ_unknown"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clean_chat(auth_headers):
    """Best-effort: keep history scoped. We don't have a delete endpoint, so capture pre-length."""
    yield


# --------------------------- AUTH ---------------------------

class TestAuth:
    def test_get_chat_requires_auth(self):
        r = requests.get(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat", timeout=10)
        assert r.status_code in (401, 403), r.text

    def test_post_chat_requires_auth(self):
        r = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          json={"text": "hi"}, timeout=10)
        assert r.status_code in (401, 403), r.text


# --------------------------- HAPPY PATHS ---------------------------

class TestGetChatHistory:
    def test_get_returns_messages_list(self, auth_headers):
        r = requests.get(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                         headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "messages" in data and isinstance(data["messages"], list)
        assert data.get("issue_key") == ISSUE_KEY_BUG_MAJOR

    def test_get_unknown_issue_404(self, auth_headers):
        r = requests.get(f"{API}/sonarqube/issues/{UNKNOWN_KEY}/chat",
                         headers=auth_headers, timeout=10)
        assert r.status_code == 404, r.text


class TestPostChat:
    def test_empty_text_returns_400(self, auth_headers):
        r = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          headers=auth_headers, json={"text": "   "}, timeout=10)
        assert r.status_code == 400, r.text

    def test_unknown_issue_returns_404(self, auth_headers):
        r = requests.post(f"{API}/sonarqube/issues/{UNKNOWN_KEY}/chat",
                          headers=auth_headers, json={"text": "hi"}, timeout=10)
        assert r.status_code == 404, r.text

    @pytest.mark.parametrize("intent", INTENTS)
    def test_each_intent_returns_tagged_reply(self, auth_headers, intent):
        r = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          headers=auth_headers,
                          json={"text": f"prompt for {intent}", "intent": intent},
                          timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "user_message" in data and "assistant_message" in data
        asst = data["assistant_message"]
        assert asst["role"] == "assistant"
        assert asst.get("intent") == intent
        assert isinstance(asst["text"], str) and len(asst["text"]) > 20

    def test_suggest_fix_contains_code_block(self, auth_headers):
        r = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          headers=auth_headers,
                          json={"text": "fix please", "intent": "suggest_fix"},
                          timeout=20)
        assert r.status_code == 200
        assert "```" in r.json()["assistant_message"]["text"]

    def test_severity_reply_mentions_major(self, auth_headers):
        r = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          headers=auth_headers,
                          json={"text": "severity?", "intent": "severity"},
                          timeout=20)
        assert r.status_code == 200
        assert "MAJOR" in r.json()["assistant_message"]["text"]

    def test_intent_omitted_keyword_fallback_explain(self, auth_headers):
        r = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          headers=auth_headers,
                          json={"text": "why is this a problem"},
                          timeout=20)
        assert r.status_code == 200
        assert r.json()["assistant_message"].get("intent") == "explain"

    def test_intent_omitted_keyword_fallback_suggest_fix(self, auth_headers):
        r = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          headers=auth_headers,
                          json={"text": "how do i fix this"},
                          timeout=20)
        assert r.status_code == 200
        assert r.json()["assistant_message"].get("intent") == "suggest_fix"


# --------------------------- PERSISTENCE / ISOLATION ---------------------------

class TestPersistenceAndIsolation:
    def test_history_grows_after_post(self, auth_headers):
        r0 = requests.get(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          headers=auth_headers, timeout=10)
        before = len(r0.json().get("messages", []))
        r1 = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                           headers=auth_headers,
                           json={"text": "explain please", "intent": "explain"},
                           timeout=20)
        assert r1.status_code == 200
        r2 = requests.get(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                          headers=auth_headers, timeout=10)
        after = len(r2.json().get("messages", []))
        assert after == before + 2  # user + assistant

    def test_each_issue_has_isolated_history(self, auth_headers):
        # Post to AYxyz123, ensure AYxyz126 history length unchanged after.
        before126 = len(requests.get(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                                     headers=auth_headers, timeout=10).json().get("messages", []))
        r = requests.post(f"{API}/sonarqube/issues/{ISSUE_KEY_SMELL}/chat",
                          headers=auth_headers,
                          json={"text": "explain", "intent": "explain"}, timeout=20)
        assert r.status_code == 200
        after126 = len(requests.get(f"{API}/sonarqube/issues/{ISSUE_KEY_BUG_MAJOR}/chat",
                                    headers=auth_headers, timeout=10).json().get("messages", []))
        assert after126 == before126  # unchanged
