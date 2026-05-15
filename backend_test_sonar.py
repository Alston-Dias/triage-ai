#!/usr/bin/env python3
"""
F-02 Backend Verification Test Suite
Tests the enhanced SonarQube dashboard endpoints
"""

import requests
import json
import sys
from typing import Dict, Any

# Use internal pod URL for testing
BASE_URL = "http://127.0.0.1:8001/api"

# Test credentials
ADMIN_EMAIL = "admin@triage.ai"
ADMIN_PASSWORD = "admin123"

# Global auth token
auth_token = None

def print_test(name: str):
    """Print test name"""
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print('='*80)

def print_pass(msg: str):
    """Print success message"""
    print(f"✅ PASS: {msg}")

def print_fail(msg: str):
    """Print failure message"""
    print(f"❌ FAIL: {msg}")

def print_info(msg: str):
    """Print info message"""
    print(f"ℹ️  INFO: {msg}")

def login() -> str:
    """Login and get auth token"""
    print_test("Login")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if response.status_code != 200:
        print_fail(f"Login failed with status {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)
    
    data = response.json()
    token = data.get("access_token")
    
    if not token:
        print_fail("No access_token in login response")
        sys.exit(1)
    
    print_pass(f"Login successful, got token")
    return token

def get_headers() -> Dict[str, str]:
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}

def test_sonarqube_issues_basic():
    """Test 1: GET /api/sonarqube/issues - verify new fields"""
    print_test("GET /api/sonarqube/issues - Basic response with new fields")
    
    response = requests.get(f"{BASE_URL}/sonarqube/issues")
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    
    # Check for new fields
    required_fields = ["buckets", "technical_debt_minutes", "total_unfiltered", "total", "issues", "breakdown"]
    missing_fields = [f for f in required_fields if f not in data]
    
    if missing_fields:
        print_fail(f"Missing fields: {missing_fields}")
        return False
    
    print_pass("All required fields present")
    
    # Verify buckets structure
    buckets = data.get("buckets", {})
    expected_bucket_keys = ["BLOCKER", "HIGH", "MEDIUM", "LOW"]
    missing_buckets = [k for k in expected_bucket_keys if k not in buckets]
    
    if missing_buckets:
        print_fail(f"Missing bucket keys: {missing_buckets}")
        return False
    
    print_pass(f"Buckets present: {buckets}")
    
    # Verify technical_debt_minutes is an int >= 0
    tech_debt = data.get("technical_debt_minutes")
    if not isinstance(tech_debt, int) or tech_debt < 0:
        print_fail(f"technical_debt_minutes should be int >= 0, got {tech_debt}")
        return False
    
    print_pass(f"technical_debt_minutes: {tech_debt}")
    
    # Verify total_unfiltered is present
    total_unfiltered = data.get("total_unfiltered")
    if not isinstance(total_unfiltered, int) or total_unfiltered < 0:
        print_fail(f"total_unfiltered should be int >= 0, got {total_unfiltered}")
        return False
    
    print_pass(f"total_unfiltered: {total_unfiltered}")
    
    return True

def test_sonarqube_issues_bucket_filter():
    """Test 2: GET /api/sonarqube/issues?bucket=MEDIUM"""
    print_test("GET /api/sonarqube/issues?bucket=MEDIUM")
    
    response = requests.get(f"{BASE_URL}/sonarqube/issues?bucket=MEDIUM")
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    total = data.get("total", 0)
    total_unfiltered = data.get("total_unfiltered", 0)
    
    # Verify total <= total_unfiltered
    if total > total_unfiltered:
        print_fail(f"total ({total}) should be <= total_unfiltered ({total_unfiltered})")
        return False
    
    print_pass(f"total ({total}) <= total_unfiltered ({total_unfiltered})")
    
    # Verify all returned issues have severity mapping to MEDIUM (=MAJOR)
    issues = data.get("issues", [])
    for issue in issues:
        severity = issue.get("severity", "").upper()
        if severity != "MAJOR":
            print_fail(f"Issue {issue.get('key')} has severity {severity}, expected MAJOR for MEDIUM bucket")
            return False
    
    print_pass(f"All {len(issues)} issues have MAJOR severity (MEDIUM bucket)")
    
    # Test bucket=HIGH (should return 0 as mock data has no BLOCKER/CRITICAL)
    print_info("Testing bucket=HIGH (should return 0)")
    response = requests.get(f"{BASE_URL}/sonarqube/issues?bucket=HIGH")
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    total = data.get("total", 0)
    
    if total != 0:
        print_fail(f"bucket=HIGH should return 0 issues (mock data has no BLOCKER/CRITICAL), got {total}")
        return False
    
    print_pass("bucket=HIGH correctly returns 0 issues")
    
    return True

def test_sonarqube_issues_search_filter():
    """Test 3: GET /api/sonarqube/issues?q=conditional"""
    print_test("GET /api/sonarqube/issues?q=conditional")
    
    response = requests.get(f"{BASE_URL}/sonarqube/issues?q=conditional")
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    issues = data.get("issues", [])
    
    # Verify all returned issues contain "conditional" in searchable fields
    for issue in issues:
        searchable = " ".join([
            str(issue.get("title", "")),
            str(issue.get("message", "")),
            str(issue.get("component", "")),
            str(issue.get("rule", "")),
            str(issue.get("description", "")),
        ]).lower()
        
        if "conditional" not in searchable:
            print_fail(f"Issue {issue.get('key')} does not contain 'conditional' in searchable fields")
            return False
    
    print_pass(f"All {len(issues)} issues contain 'conditional'")
    
    return True

def test_sonarqube_issues_combined_filters():
    """Test 4: GET /api/sonarqube/issues?status=OPEN&type=CODE_SMELL"""
    print_test("GET /api/sonarqube/issues?status=OPEN&type=CODE_SMELL")
    
    response = requests.get(f"{BASE_URL}/sonarqube/issues?status=OPEN&type=CODE_SMELL")
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    issues = data.get("issues", [])
    
    # Verify all returned issues have status=OPEN AND type=CODE_SMELL
    for issue in issues:
        status = issue.get("status", "").upper()
        itype = issue.get("type", "").upper()
        
        if status != "OPEN":
            print_fail(f"Issue {issue.get('key')} has status {status}, expected OPEN")
            return False
        
        if itype != "CODE_SMELL":
            print_fail(f"Issue {issue.get('key')} has type {itype}, expected CODE_SMELL")
            return False
    
    print_pass(f"All {len(issues)} issues have status=OPEN AND type=CODE_SMELL")
    
    return True

def test_sonarqube_issues_assignee_filter():
    """Test 5: GET /api/sonarqube/issues?assignee=unassigned"""
    print_test("GET /api/sonarqube/issues?assignee=unassigned")
    
    response = requests.get(f"{BASE_URL}/sonarqube/issues?assignee=unassigned")
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    issues = data.get("issues", [])
    
    # Verify all returned issues have no assignee
    for issue in issues:
        assignee = issue.get("assignee", "")
        
        if assignee:
            print_fail(f"Issue {issue.get('key')} has assignee {assignee}, expected unassigned")
            return False
    
    print_pass(f"All {len(issues)} issues are unassigned")
    
    return True

def test_generate_fix():
    """Test 6: POST /api/sonarqube/issues/{key}/generate-fix"""
    print_test("POST /api/sonarqube/issues/AYxyz123/generate-fix")
    
    # First, get a valid issue key from the issues list
    response = requests.get(f"{BASE_URL}/sonarqube/issues")
    if response.status_code != 200:
        print_fail("Failed to get issues list")
        return False
    
    issues = response.json().get("issues", [])
    if not issues:
        print_fail("No issues available for testing")
        return False
    
    issue_key = issues[0].get("key")
    print_info(f"Using issue key: {issue_key}")
    
    # Test with auth
    response = requests.post(
        f"{BASE_URL}/sonarqube/issues/{issue_key}/generate-fix",
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    
    # Verify required fields
    required_fields = [
        "explanation", "unified_diff", "confidence", "safe_to_apply",
        "language", "issue_key", "generated_at", "source"
    ]
    missing_fields = [f for f in required_fields if f not in data]
    
    if missing_fields:
        print_fail(f"Missing fields: {missing_fields}")
        return False
    
    print_pass("All required fields present")
    
    # Verify confidence is float 0..1
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        print_fail(f"confidence should be float 0..1, got {confidence}")
        return False
    
    print_pass(f"confidence: {confidence}")
    
    # Verify safe_to_apply is bool
    safe_to_apply = data.get("safe_to_apply")
    if not isinstance(safe_to_apply, bool):
        print_fail(f"safe_to_apply should be bool, got {type(safe_to_apply)}")
        return False
    
    print_pass(f"safe_to_apply: {safe_to_apply}")
    
    # Verify source is "mock"
    source = data.get("source")
    if source != "mock":
        print_fail(f"source should be 'mock', got {source}")
        return False
    
    print_pass(f"source: {source}")
    
    # Verify unified_diff structure
    unified_diff = data.get("unified_diff", "")
    if not unified_diff.startswith("--- a/"):
        print_fail(f"unified_diff should start with '--- a/', got: {unified_diff[:50]}")
        return False
    
    if "+++ b/" not in unified_diff:
        print_fail("unified_diff should contain '+++ b/'")
        return False
    
    if "@@" not in unified_diff:
        print_fail("unified_diff should contain '@@'")
        return False
    
    print_pass("unified_diff has correct format")
    
    # Test 404 for unknown issue_key
    print_info("Testing 404 for unknown issue_key")
    response = requests.post(
        f"{BASE_URL}/sonarqube/issues/UNKNOWN_KEY/generate-fix",
        headers=get_headers()
    )
    
    if response.status_code != 404:
        print_fail(f"Expected 404 for unknown key, got {response.status_code}")
        return False
    
    print_pass("404 for unknown issue_key")
    
    # Test 401 without token
    print_info("Testing 401 without token")
    response = requests.post(f"{BASE_URL}/sonarqube/issues/{issue_key}/generate-fix")
    
    if response.status_code != 401:
        print_fail(f"Expected 401 without token, got {response.status_code}")
        return False
    
    print_pass("401 without token")
    
    return True

def test_comments():
    """Test 7: POST/GET /api/sonarqube/issues/{key}/comments"""
    print_test("POST/GET /api/sonarqube/issues/{key}/comments")
    
    # Get a valid issue key
    response = requests.get(f"{BASE_URL}/sonarqube/issues")
    if response.status_code != 200:
        print_fail("Failed to get issues list")
        return False
    
    issues = response.json().get("issues", [])
    if not issues:
        print_fail("No issues available for testing")
        return False
    
    issue_key = issues[0].get("key")
    print_info(f"Using issue key: {issue_key}")
    
    # Test POST with valid text
    print_info("Testing POST with valid text")
    response = requests.post(
        f"{BASE_URL}/sonarqube/issues/{issue_key}/comments",
        headers=get_headers(),
        json={"text": "First note"}
    )
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    comment_data = response.json()
    
    # Verify comment structure
    required_fields = ["id", "issue_key", "author_email", "author_name", "text", "created_at"]
    missing_fields = [f for f in required_fields if f not in comment_data]
    
    if missing_fields:
        print_fail(f"Missing fields in comment: {missing_fields}")
        return False
    
    print_pass("Comment created successfully")
    
    # Verify author_email matches JWT
    if comment_data.get("author_email") != ADMIN_EMAIL:
        print_fail(f"author_email should be {ADMIN_EMAIL}, got {comment_data.get('author_email')}")
        return False
    
    print_pass(f"author_email: {comment_data.get('author_email')}")
    
    # Verify issue_key matches
    if comment_data.get("issue_key") != issue_key:
        print_fail(f"issue_key should be {issue_key}, got {comment_data.get('issue_key')}")
        return False
    
    print_pass(f"issue_key: {comment_data.get('issue_key')}")
    
    # Test POST with empty text (should be 400)
    print_info("Testing POST with empty text (should be 400)")
    response = requests.post(
        f"{BASE_URL}/sonarqube/issues/{issue_key}/comments",
        headers=get_headers(),
        json={"text": ""}
    )
    
    if response.status_code != 400:
        print_fail(f"Expected 400 for empty text, got {response.status_code}")
        return False
    
    print_pass("400 for empty text")
    
    # Test GET comments
    print_info("Testing GET comments")
    response = requests.get(
        f"{BASE_URL}/sonarqube/issues/{issue_key}/comments",
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    comments = data.get("comments", [])
    
    # Verify the comment we just added is in the list
    found = False
    for comment in comments:
        if comment.get("text") == "First note":
            found = True
            break
    
    if not found:
        print_fail("Comment 'First note' not found in comments list")
        return False
    
    print_pass(f"Comment found in list ({len(comments)} total comments)")
    
    # Test 401 without token
    print_info("Testing 401 without token on POST")
    response = requests.post(
        f"{BASE_URL}/sonarqube/issues/{issue_key}/comments",
        json={"text": "Test"}
    )
    
    if response.status_code != 401:
        print_fail(f"Expected 401 without token, got {response.status_code}")
        return False
    
    print_pass("401 without token on POST")
    
    print_info("Testing 401 without token on GET")
    response = requests.get(f"{BASE_URL}/sonarqube/issues/{issue_key}/comments")
    
    if response.status_code != 401:
        print_fail(f"Expected 401 without token, got {response.status_code}")
        return False
    
    print_pass("401 without token on GET")
    
    return True

def test_trend():
    """Test 8: GET /api/sonarqube/trend?days=7"""
    print_test("GET /api/sonarqube/trend?days=7")
    
    response = requests.get(f"{BASE_URL}/sonarqube/trend?days=7")
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    series = data.get("series", [])
    
    # Verify exactly 7 rows
    if len(series) != 7:
        print_fail(f"Expected 7 series rows, got {len(series)}")
        return False
    
    print_pass(f"Got exactly 7 series rows")
    
    # Verify each row has required fields
    for i, row in enumerate(series):
        required_fields = ["date", "bugs", "vulnerabilities", "code_smells", "total"]
        missing_fields = [f for f in required_fields if f not in row]
        
        if missing_fields:
            print_fail(f"Row {i} missing fields: {missing_fields}")
            return False
        
        # Verify all values are int >= 0
        for field in ["bugs", "vulnerabilities", "code_smells", "total"]:
            value = row.get(field)
            if not isinstance(value, int) or value < 0:
                print_fail(f"Row {i} field {field} should be int >= 0, got {value}")
                return False
        
        # Verify total = sum of bugs + vulnerabilities + code_smells
        expected_total = row["bugs"] + row["vulnerabilities"] + row["code_smells"]
        if row["total"] != expected_total:
            print_fail(f"Row {i} total should be {expected_total}, got {row['total']}")
            return False
    
    print_pass("All rows have correct structure and values")
    
    # Test days=0 (should be 422)
    print_info("Testing days=0 (should be 422)")
    response = requests.get(f"{BASE_URL}/sonarqube/trend?days=0")
    
    if response.status_code != 422:
        print_fail(f"Expected 422 for days=0, got {response.status_code}")
        return False
    
    print_pass("422 for days=0")
    
    # Test days=31 (should be 422)
    print_info("Testing days=31 (should be 422)")
    response = requests.get(f"{BASE_URL}/sonarqube/trend?days=31")
    
    if response.status_code != 422:
        print_fail(f"Expected 422 for days=31, got {response.status_code}")
        return False
    
    print_pass("422 for days=31")
    
    # Test default (no param, should return 7 rows)
    print_info("Testing default (no param, should return 7 rows)")
    response = requests.get(f"{BASE_URL}/sonarqube/trend")
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    series = data.get("series", [])
    
    if len(series) != 7:
        print_fail(f"Default should return 7 rows, got {len(series)}")
        return False
    
    print_pass("Default returns 7 rows")
    
    return True

def test_config():
    """Test 9: GET /api/sonarqube/config"""
    print_test("GET /api/sonarqube/config")
    
    response = requests.get(
        f"{BASE_URL}/sonarqube/config",
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    
    # Verify required fields
    required_fields = ["source", "base_url", "project_key", "has_token"]
    missing_fields = [f for f in required_fields if f not in data]
    
    if missing_fields:
        print_fail(f"Missing fields: {missing_fields}")
        return False
    
    print_pass("All required fields present")
    
    # Verify source is "mock"
    source = data.get("source")
    if source != "mock":
        print_fail(f"source should be 'mock', got {source}")
        return False
    
    print_pass(f"source: {source}")
    
    # Verify base_url is null
    base_url = data.get("base_url")
    if base_url is not None:
        print_fail(f"base_url should be null, got {base_url}")
        return False
    
    print_pass(f"base_url: {base_url}")
    
    # Verify project_key is "triageai"
    project_key = data.get("project_key")
    if project_key != "triageai":
        print_fail(f"project_key should be 'triageai', got {project_key}")
        return False
    
    print_pass(f"project_key: {project_key}")
    
    # Verify has_token is false
    has_token = data.get("has_token")
    if has_token is not False:
        print_fail(f"has_token should be false, got {has_token}")
        return False
    
    print_pass(f"has_token: {has_token}")
    
    return True

def test_chat_new_intents():
    """Test 10: POST /api/sonarqube/issues/{key}/chat - new intents"""
    print_test("POST /api/sonarqube/issues/{key}/chat - new intents")
    
    # Get a valid issue key
    response = requests.get(f"{BASE_URL}/sonarqube/issues")
    if response.status_code != 200:
        print_fail("Failed to get issues list")
        return False
    
    issues = response.json().get("issues", [])
    if not issues:
        print_fail("No issues available for testing")
        return False
    
    issue_key = issues[0].get("key")
    print_info(f"Using issue key: {issue_key}")
    
    # Test new intents
    new_intents = [
        ("write_test", "test"),
        ("pr_description", "PR description"),
        ("explain_rule", ""),
        ("generate_fix", ""),
        ("alternative_fix", ""),
    ]
    
    for intent, expected_keyword in new_intents:
        print_info(f"Testing intent: {intent}")
        
        response = requests.post(
            f"{BASE_URL}/sonarqube/issues/{issue_key}/chat",
            headers=get_headers(),
            json={"text": f"Test message for {intent}", "intent": intent}
        )
        
        if response.status_code != 200:
            print_fail(f"Expected 200 for intent {intent}, got {response.status_code}")
            return False
        
        data = response.json()
        assistant_message = data.get("assistant_message", {})
        reply_text = assistant_message.get("text", "")
        reply_intent = assistant_message.get("intent", "")
        
        # Verify reply is non-empty
        if not reply_text:
            print_fail(f"Reply text is empty for intent {intent}")
            return False
        
        # Verify reply does not contain "(no mocked reply)" sentinel
        if "(no mocked reply)" in reply_text:
            print_fail(f"Reply contains '(no mocked reply)' for intent {intent}")
            return False
        
        # Verify intent is echoed
        if reply_intent != intent:
            print_fail(f"Expected intent {intent}, got {reply_intent}")
            return False
        
        # For specific intents, verify expected keywords
        if expected_keyword and expected_keyword.lower() not in reply_text.lower():
            print_fail(f"Reply for {intent} should contain '{expected_keyword}' (case-insensitive)")
            return False
        
        print_pass(f"Intent {intent} works correctly")
    
    return True

def test_chat_old_intents():
    """Test 11: POST /api/sonarqube/issues/{key}/chat - old intents (backward compat)"""
    print_test("POST /api/sonarqube/issues/{key}/chat - old intents (backward compat)")
    
    # Get a valid issue key
    response = requests.get(f"{BASE_URL}/sonarqube/issues")
    if response.status_code != 200:
        print_fail("Failed to get issues list")
        return False
    
    issues = response.json().get("issues", [])
    if not issues:
        print_fail("No issues available for testing")
        return False
    
    issue_key = issues[0].get("key")
    print_info(f"Using issue key: {issue_key}")
    
    # Test old intents
    old_intents = [
        "explain",
        "suggest_fix",
        "refactor",
        "severity",
        "best_practices",
    ]
    
    for intent in old_intents:
        print_info(f"Testing old intent: {intent}")
        
        response = requests.post(
            f"{BASE_URL}/sonarqube/issues/{issue_key}/chat",
            headers=get_headers(),
            json={"text": f"Test message for {intent}", "intent": intent}
        )
        
        if response.status_code != 200:
            print_fail(f"Expected 200 for intent {intent}, got {response.status_code}")
            return False
        
        data = response.json()
        assistant_message = data.get("assistant_message", {})
        reply_text = assistant_message.get("text", "")
        
        # Verify reply is non-empty
        if not reply_text:
            print_fail(f"Reply text is empty for intent {intent}")
            return False
        
        # Verify reply does not contain "(no mocked reply)" sentinel
        if "(no mocked reply)" in reply_text:
            print_fail(f"Reply contains '(no mocked reply)' for intent {intent}")
            return False
        
        print_pass(f"Old intent {intent} works correctly")
    
    return True

def test_status_update():
    """Test 12: PATCH /api/sonarqube/issues/{key}/status"""
    print_test("PATCH /api/sonarqube/issues/{key}/status")
    
    # Get a valid issue key
    response = requests.get(f"{BASE_URL}/sonarqube/issues")
    if response.status_code != 200:
        print_fail("Failed to get issues list")
        return False
    
    issues = response.json().get("issues", [])
    if not issues:
        print_fail("No issues available for testing")
        return False
    
    issue_key = issues[0].get("key")
    print_info(f"Using issue key: {issue_key}")
    
    # Test PATCH to WONT_FIX
    print_info("Testing PATCH to WONT_FIX")
    response = requests.patch(
        f"{BASE_URL}/sonarqube/issues/{issue_key}/status",
        headers=get_headers(),
        json={"status": "WONT_FIX"}
    )
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    print_pass("PATCH to WONT_FIX successful")
    
    # Verify status is updated
    print_info("Verifying status is updated")
    response = requests.get(
        f"{BASE_URL}/sonarqube/issues/{issue_key}",
        headers=get_headers()
    )
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    status = data.get("status")
    
    if status != "WONT_FIX":
        print_fail(f"Status should be WONT_FIX, got {status}")
        return False
    
    print_pass(f"Status verified: {status}")
    
    # Reset to OPEN to keep state clean
    print_info("Resetting status to OPEN")
    response = requests.patch(
        f"{BASE_URL}/sonarqube/issues/{issue_key}/status",
        headers=get_headers(),
        json={"status": "OPEN"}
    )
    
    if response.status_code != 200:
        print_fail(f"Expected 200, got {response.status_code}")
        return False
    
    print_pass("Status reset to OPEN")
    
    return True

def main():
    """Run all tests"""
    global auth_token
    
    print("\n" + "="*80)
    print("F-02 BACKEND VERIFICATION TEST SUITE")
    print("="*80)
    
    # Login first
    auth_token = login()
    
    # Run all tests
    tests = [
        ("GET /api/sonarqube/issues - Basic", test_sonarqube_issues_basic),
        ("GET /api/sonarqube/issues - Bucket filter", test_sonarqube_issues_bucket_filter),
        ("GET /api/sonarqube/issues - Search filter", test_sonarqube_issues_search_filter),
        ("GET /api/sonarqube/issues - Combined filters", test_sonarqube_issues_combined_filters),
        ("GET /api/sonarqube/issues - Assignee filter", test_sonarqube_issues_assignee_filter),
        ("POST /api/sonarqube/issues/{key}/generate-fix", test_generate_fix),
        ("POST/GET /api/sonarqube/issues/{key}/comments", test_comments),
        ("GET /api/sonarqube/trend", test_trend),
        ("GET /api/sonarqube/config", test_config),
        ("POST /api/sonarqube/issues/{key}/chat - New intents", test_chat_new_intents),
        ("POST /api/sonarqube/issues/{key}/chat - Old intents", test_chat_old_intents),
        ("PATCH /api/sonarqube/issues/{key}/status", test_status_update),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print_fail(f"Exception in {test_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total tests: {len(tests)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print("="*80)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)

if __name__ == "__main__":
    main()
