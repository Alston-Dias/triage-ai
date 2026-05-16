#!/usr/bin/env python3
"""
LLM Gateway Integration Test Suite
Tests all LLM-backed endpoints after gateway swap from Emergent/Claude to corporate OpenAI-compatible gateway
"""
import asyncio
import json
import sys
import time
from typing import Dict, Any, Optional, List

import httpx

# Configuration
BACKEND_URL = "https://ai-orchestrator-112.preview.emergentagent.com/api"
TEST_EMAIL = "admin@triage.ai"
TEST_PASSWORD = "admin123"

# Test results tracking
test_results = []


def log_test(name: str, passed: bool, details: str = ""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name}")
    if details:
        print(f"  Details: {details}")
    test_results.append({"name": name, "passed": passed, "details": details})


async def login() -> str:
    """Login and return JWT token"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if resp.status_code != 200:
            raise Exception(f"Login failed: {resp.status_code} {resp.text}")
        data = resp.json()
        return data["access_token"]


async def test_auth_gate(token: str):
    """Test: Auth gate - all LLM endpoints must 401 without bearer token"""
    print("\n=== Test: Auth Gate (401 without token) ===")
    
    endpoints = [
        ("POST", "/triage", {"alert_ids": ["ALT-12345678"]}),
        ("POST", "/incidents/INC-12345678/chat", {"text": "test"}),
        ("POST", "/predictive-triage", {}),
        ("POST", "/code-quality/demo/seed", {}),
        ("POST", "/code-quality/issues/ISS-12345678/fix", {}),
        ("POST", "/code-quality/scans/github", {"repo_url": "https://github.com/test/test"}),
        ("POST", "/sonarqube/issues/AYxyz123/chat", {"intent": "explain_rule", "text": "test"}),
    ]
    
    all_passed = True
    async with httpx.AsyncClient(timeout=30.0) as client:
        for method, path, body in endpoints:
            resp = await client.post(f"{BACKEND_URL}{path}", json=body)
            
            if resp.status_code == 401:
                print(f"  ✓ {method} {path} correctly returns 401")
            else:
                print(f"  ✗ {method} {path} returned {resp.status_code} instead of 401")
                all_passed = False
    
    log_test("Auth gate - all LLM endpoints require JWT", all_passed)
    return all_passed


async def test_seed_demo_data(token: str):
    """Test: POST /api/code-quality/demo/seed?reset=true"""
    print("\n=== Test: POST /api/code-quality/demo/seed ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/demo/seed?reset=true",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Demo seed", False, f"Status {resp.status_code}: {resp.text}")
            return False
        
        data = resp.json()
        
        # Verify response structure
        checks = [
            (data.get("ok") == True, "ok is true"),
            (data.get("reset") == True, "reset is true"),
            (data.get("integrations_added", 0) >= 1, "integrations_added >= 1"),
            (data.get("scans_added", 0) >= 1, "scans_added >= 1"),
            (data.get("issues_added", 0) >= 1, "issues_added >= 1"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Demo seed", all_checks_passed, 
                f"integrations={data.get('integrations_added')}, scans={data.get('scans_added')}, issues={data.get('issues_added')}, Failed: {failed_checks if failed_checks else 'none'}")
        
        return all_checks_passed


async def test_seed_alerts(token: str):
    """Seed alerts if needed for triage test"""
    print("\n=== Seeding Alerts ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check if alerts exist
        resp = await client.get(f"{BACKEND_URL}/alerts", headers=headers)
        if resp.status_code == 200:
            alerts = resp.json()
            if len(alerts) >= 2:
                print(f"  ✓ Found {len(alerts)} existing alerts")
                return [a["id"] for a in alerts[:2]]
        
        # Seed alerts
        resp = await client.post(f"{BACKEND_URL}/seed", headers=headers)
        if resp.status_code != 200:
            print(f"  ✗ Failed to seed: {resp.status_code}")
            return []
        
        # Get alerts again
        resp = await client.get(f"{BACKEND_URL}/alerts", headers=headers)
        if resp.status_code == 200:
            alerts = resp.json()
            print(f"  ✓ Seeded {len(alerts)} alerts")
            return [a["id"] for a in alerts[:2]]
        
        return []


async def test_triage(token: str, alert_ids: List[str]) -> Optional[str]:
    """Test 1: POST /api/triage with 1-2 alerts"""
    print("\n=== Test 1: POST /api/triage ===")
    
    if not alert_ids:
        log_test("Triage - no alerts", False, "No alerts available")
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        print(f"  Triaging alerts: {alert_ids[:2]}")
        resp = await client.post(
            f"{BACKEND_URL}/triage",
            headers=headers,
            json={"alert_ids": alert_ids[:2]}
        )
        
        if resp.status_code != 200:
            log_test("Triage - API call", False, f"Status {resp.status_code}: {resp.text}")
            return None
        
        data = resp.json()
        
        # Verify response structure
        checks = [
            (data.get("priority") in ["P0", "P1", "P2", "P3"], "priority in [P0,P1,P2,P3]"),
            ("blast_radius" in data, "has blast_radius"),
            (isinstance(data.get("mttr_estimate_minutes"), int), "mttr_estimate_minutes is int"),
            (isinstance(data.get("affected_services"), list), "affected_services is list"),
            (bool(data.get("summary", "").strip()), "summary is non-empty"),
            (isinstance(data.get("root_causes"), list), "root_causes is list"),
            (isinstance(data.get("remediation"), list), "remediation is list"),
            (isinstance(data.get("deployments"), list), "deployments is list"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        # Check if response is NOT the fallback
        summary = data.get("summary", "")
        is_not_fallback = "Automated fallback triage" not in summary
        
        if not is_not_fallback:
            log_test("Triage - LLM response", False, 
                    "Response contains 'Automated fallback triage' - LLM failed")
            return data.get("incident_id")
        
        # Verify root_causes structure
        root_causes_valid = True
        if data.get("root_causes"):
            for rc in data["root_causes"]:
                if not all(k in rc for k in ["rank", "hypothesis", "confidence", "reasoning"]):
                    root_causes_valid = False
                    break
        
        # Verify remediation structure
        remediation_valid = True
        if data.get("remediation"):
            for rem in data["remediation"]:
                if not all(k in rem for k in ["phase", "action"]):
                    remediation_valid = False
                    break
        
        checks.append((root_causes_valid, "root_causes have correct structure"))
        checks.append((remediation_valid, "remediation has correct structure"))
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Triage - API call", all_checks_passed,
                f"priority={data.get('priority')}, root_causes={len(data.get('root_causes', []))}, remediation={len(data.get('remediation', []))}, Failed: {failed_checks if failed_checks else 'none'}")
        
        log_test("Triage - LLM response (not fallback)", is_not_fallback,
                f"summary length: {len(summary)} chars")
        
        return data.get("incident_id")


async def test_incident_chat(token: str, incident_id: Optional[str]):
    """Test 2: POST /api/incidents/{id}/chat"""
    print("\n=== Test 2: POST /api/incidents/{id}/chat ===")
    
    if not incident_id:
        log_test("Incident chat - no incident", False, "No incident_id available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        print(f"  Chatting with incident: {incident_id}")
        resp = await client.post(
            f"{BACKEND_URL}/incidents/{incident_id}/chat",
            headers=headers,
            json={"text": "What's the immediate next step?"}
        )
        
        if resp.status_code != 200:
            log_test("Incident chat - API call", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Verify response structure
        assistant_message = data.get("assistant_message", {})
        text = assistant_message.get("text", "")
        
        checks = [
            (bool(text.strip()), "assistant_message.text is non-empty"),
            ("_(AI assistant unavailable:" not in text, "not the unavailable sentinel"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Incident chat - API call", all_checks_passed,
                f"response length: {len(text)} chars, Failed: {failed_checks if failed_checks else 'none'}")


async def test_predictive_triage(token: str):
    """Test 3: POST /api/predictive-triage"""
    print("\n=== Test 3: POST /api/predictive-triage ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/predictive-triage",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Predictive triage - API call", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Verify response structure
        checks = [
            (data.get("generated", 0) >= 1, "generated >= 1"),
            (isinstance(data.get("predictions"), list), "predictions is list"),
            (len(data.get("predictions", [])) >= 1, "predictions has at least 1 item"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        # Check if predictions have non-empty recommended_action
        predictions = data.get("predictions", [])
        long_action_found = False
        for pred in predictions:
            action = pred.get("recommended_action", "")
            if len(action) > 80:
                long_action_found = True
                break
        
        checks.append((long_action_found, "at least one prediction has recommended_action > 80 chars"))
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Predictive triage - API call", all_checks_passed,
                f"generated={data.get('generated')}, predictions={len(predictions)}, Failed: {failed_checks if failed_checks else 'none'}")


async def test_code_quality_fix(token: str):
    """Test 4: POST /api/code-quality/issues/{issue_id}/fix"""
    print("\n=== Test 4: POST /api/code-quality/issues/{id}/fix ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Get scans
        resp = await client.get(f"{BACKEND_URL}/code-quality/scans", headers=headers)
        if resp.status_code != 200:
            log_test("Code quality fix - get scans", False, f"Status {resp.status_code}")
            return
        
        scans = resp.json()
        
        # Find a "done" scan
        done_scan = None
        for scan in scans:
            if scan.get("status") == "done":
                done_scan = scan
                break
        
        if not done_scan:
            log_test("Code quality fix - no done scan", False, "No 'done' scan available")
            return
        
        scan_id = done_scan["id"]
        
        # Get issues from scan
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans/{scan_id}/issues",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Code quality fix - get issues", False, f"Status {resp.status_code}")
            return
        
        issues = resp.json()
        
        if not issues:
            log_test("Code quality fix - no issues", False, "No issues in done scan")
            return
        
        issue_id = issues[0]["id"]
        print(f"  Requesting fix for issue: {issue_id}")
        
        # Request fix
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/issues/{issue_id}/fix",
            headers=headers,
            json={}
        )
        
        if resp.status_code != 200:
            log_test("Code quality fix - API call", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        fix_data = resp.json()
        
        # Verify required fields
        checks = [
            ("explanation" in fix_data, "has explanation"),
            (bool(fix_data.get("explanation", "").strip()), "explanation is non-empty"),
            ("patched_file" in fix_data, "has patched_file"),
            (len(fix_data.get("patched_file", "")) > 50, "patched_file > 50 chars"),
            ("diff" in fix_data, "has diff"),
            ("@@" in fix_data.get("diff", ""), "diff contains @@"),
            ("+" in fix_data.get("diff", "") or "-" in fix_data.get("diff", ""), "diff contains +/- lines"),
            ("test_hint" in fix_data, "has test_hint"),
            (bool(fix_data.get("test_hint", "").strip()), "test_hint is non-empty"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Code quality fix - API call", all_checks_passed,
                f"explanation={len(fix_data.get('explanation', ''))} chars, patched_file={len(fix_data.get('patched_file', ''))} chars, diff={len(fix_data.get('diff', ''))} chars, Failed: {failed_checks if failed_checks else 'none'}")


async def test_code_quality_github_scan(token: str):
    """Test 5: POST /api/code-quality/scans/github"""
    print("\n=== Test 5: POST /api/code-quality/scans/github ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Start scan
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/scans/github",
            headers=headers,
            json={"repo_url": "https://github.com/octocat/Hello-World"}
        )
        
        if resp.status_code != 200:
            log_test("GitHub scan - initiate", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        scan_id = data.get("id")
        
        log_test("GitHub scan - initiate", True, f"Scan ID: {scan_id}")
        
        # Poll for completion (max 18 iterations = 90s)
        print(f"  Polling scan {scan_id} for completion (max 90s)...")
        for i in range(18):
            await asyncio.sleep(5)
            resp = await client.get(
                f"{BACKEND_URL}/code-quality/scans/{scan_id}",
                headers=headers
            )
            
            if resp.status_code != 200:
                log_test("GitHub scan - poll", False, f"Status {resp.status_code}")
                return
            
            data = resp.json()
            status = data.get("status")
            print(f"    Iteration {i+1}/18: status={status}")
            
            if status in ["done", "failed"]:
                break
        
        final_status = data.get("status")
        if final_status == "done":
            log_test("GitHub scan - completion", True, f"Status: done")
        else:
            log_test("GitHub scan - completion", False, f"Status: {final_status}, error: {data.get('error', 'N/A')}")


async def test_sonarqube_chat(token: str):
    """Test 6: POST /api/sonarqube/issues/{key}/chat"""
    print("\n=== Test 6: POST /api/sonarqube/issues/{key}/chat ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Get issues
        resp = await client.get(f"{BACKEND_URL}/sonarqube/issues", headers=headers)
        
        if resp.status_code != 200:
            log_test("SonarQube chat - get issues", False, f"Status {resp.status_code}")
            return
        
        data = resp.json()
        issues = data.get("issues", [])
        
        if not issues:
            log_test("SonarQube chat - no issues", False, "No issues available")
            return
        
        issue_key = issues[0]["key"]
        print(f"  Chatting about issue: {issue_key}")
        
        # Chat with explain_rule intent
        resp = await client.post(
            f"{BACKEND_URL}/sonarqube/issues/{issue_key}/chat",
            headers=headers,
            json={"intent": "explain_rule", "text": "Explain this rule"}
        )
        
        if resp.status_code != 200:
            log_test("SonarQube chat - API call", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Verify response structure
        assistant_message = data.get("assistant_message", {})
        text = assistant_message.get("text", "")
        
        checks = [
            (bool(text.strip()), "assistant reply is non-empty"),
            ("(no mocked reply)" not in text, "not the '(no mocked reply)' sentinel"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("SonarQube chat - API call", all_checks_passed,
                f"response length: {len(text)} chars, Failed: {failed_checks if failed_checks else 'none'}")


async def test_sonarqube_issues_no_regression(token: str):
    """Test 8: GET /api/sonarqube/issues - verify no regression"""
    print("\n=== Test 8: GET /api/sonarqube/issues (no regression) ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{BACKEND_URL}/sonarqube/issues", headers=headers)
        
        if resp.status_code != 200:
            log_test("SonarQube issues - API call", False, f"Status {resp.status_code}")
            return
        
        data = resp.json()
        
        # Verify F-02 enriched fields are present
        checks = [
            ("buckets" in data, "has buckets field"),
            ("technical_debt_minutes" in data, "has technical_debt_minutes field"),
            ("total_unfiltered" in data, "has total_unfiltered field"),
        ]
        
        # Verify buckets structure
        if "buckets" in data:
            buckets = data["buckets"]
            checks.append((isinstance(buckets, dict), "buckets is dict"))
            checks.append(("BLOCKER" in buckets, "buckets has BLOCKER"))
            checks.append(("HIGH" in buckets, "buckets has HIGH"))
            checks.append(("MEDIUM" in buckets, "buckets has MEDIUM"))
            checks.append(("LOW" in buckets, "buckets has LOW"))
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("SonarQube issues - no regression", all_checks_passed,
                f"buckets={data.get('buckets')}, tech_debt={data.get('technical_debt_minutes')}, total={data.get('total_unfiltered')}, Failed: {failed_checks if failed_checks else 'none'}")


async def main():
    """Run all tests"""
    print("=" * 80)
    print("LLM Gateway Integration Test Suite")
    print("Testing all LLM-backed endpoints after gateway swap")
    print("=" * 80)
    
    try:
        # Login
        print("\n=== Authentication ===")
        token = await login()
        print(f"✓ Logged in as {TEST_EMAIL}")
        
        # Run tests
        await test_auth_gate(token)
        
        # Seed demo data first
        await test_seed_demo_data(token)
        
        # Seed alerts for triage
        alert_ids = await test_seed_alerts(token)
        
        # Test 1: Triage
        incident_id = await test_triage(token, alert_ids)
        
        # Test 2: Incident chat
        await test_incident_chat(token, incident_id)
        
        # Test 3: Predictive triage
        await test_predictive_triage(token)
        
        # Test 4: Code quality fix
        await test_code_quality_fix(token)
        
        # Test 5: GitHub scan
        await test_code_quality_github_scan(token)
        
        # Test 6: SonarQube chat
        await test_sonarqube_chat(token)
        
        # Test 8: SonarQube issues no regression
        await test_sonarqube_issues_no_regression(token)
        
        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for r in test_results if r["passed"])
        total = len(test_results)
        
        print(f"\nTotal: {passed}/{total} tests passed")
        print("\nDetailed Results:")
        for r in test_results:
            status = "✅" if r["passed"] else "❌"
            print(f"{status} {r['name']}")
            if r["details"]:
                print(f"   {r['details']}")
        
        # Exit code
        sys.exit(0 if passed == total else 1)
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
