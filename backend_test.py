#!/usr/bin/env python3
"""
Code Quality v2 Backend Test Suite
Tests all /api/code-quality/* endpoints
"""
import asyncio
import io
import json
import os
import sys
import time
import zipfile
from typing import Dict, Any, Optional

import httpx

# Configuration
BACKEND_URL = "https://friendly-interface-7.preview.emergentagent.com/api"
TEST_EMAIL = "sre1@triage.ai"
TEST_PASSWORD = "sre123"

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
    """Test 1: Auth gate - all endpoints must 401 without bearer token"""
    print("\n=== Test 1: Auth Gate ===")
    
    endpoints = [
        ("GET", "/code-quality/scans"),
        ("POST", "/code-quality/scans/github"),
        ("POST", "/code-quality/scans/upload"),
        ("GET", "/code-quality/integrations"),
        ("POST", "/code-quality/integrations"),
    ]
    
    all_passed = True
    async with httpx.AsyncClient(timeout=30.0) as client:
        for method, path in endpoints:
            if method == "GET":
                resp = await client.get(f"{BACKEND_URL}{path}")
            else:
                resp = await client.post(f"{BACKEND_URL}{path}", json={})
            
            if resp.status_code == 401:
                print(f"  ✓ {method} {path} correctly returns 401")
            else:
                print(f"  ✗ {method} {path} returned {resp.status_code} instead of 401")
                all_passed = False
    
    log_test("Auth gate - all endpoints require JWT", all_passed)
    return all_passed


async def test_github_scan_happy_path(token: str) -> Optional[str]:
    """Test 2: Happy-path GitHub scan"""
    print("\n=== Test 2: GitHub Scan Happy Path ===")
    
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
            return None
        
        data = resp.json()
        scan_id = data.get("id")
        
        # Verify response structure
        checks = [
            ("id" in data, "has id"),
            (data.get("status") in ["queued", "scanning"], "status is queued/scanning"),
            (data.get("source") == "github", "source is github"),
            ("octocat/Hello-World" in data.get("source_label", ""), "source_label contains repo"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        if not all_checks_passed:
            log_test("GitHub scan - initiate", False, f"Failed checks: {failed_checks}")
            return None
        
        log_test("GitHub scan - initiate", True, f"Scan ID: {scan_id}")
        
        # Poll for completion (max 24 iterations = 120s)
        print(f"  Polling scan {scan_id} for completion...")
        for i in range(24):
            await asyncio.sleep(5)
            resp = await client.get(
                f"{BACKEND_URL}/code-quality/scans/{scan_id}",
                headers=headers
            )
            
            if resp.status_code != 200:
                log_test("GitHub scan - poll", False, f"Status {resp.status_code}")
                return None
            
            data = resp.json()
            status = data.get("status")
            print(f"    Iteration {i+1}/24: status={status}, file_count={data.get('file_count', 0)}")
            
            if status in ["done", "failed"]:
                break
        
        final_status = data.get("status")
        if final_status == "done":
            log_test("GitHub scan - completion", True, f"Status: done, files: {data.get('file_count', 0)}")
        else:
            log_test("GitHub scan - completion", False, f"Status: {final_status}, error: {data.get('error', 'N/A')}")
            return None
        
        # Get issues
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans/{scan_id}/issues",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("GitHub scan - get issues", False, f"Status {resp.status_code}")
            return None
        
        issues = resp.json()
        log_test("GitHub scan - get issues", True, f"Found {len(issues)} issues (empty list OK for tiny repo)")
        
        return scan_id


async def test_invalid_github_url(token: str):
    """Test 3: Invalid GitHub URL"""
    print("\n=== Test 3: Invalid GitHub URL ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/scans/github",
            headers=headers,
            json={"repo_url": "not-a-url"}
        )
        
        passed = resp.status_code == 400
        log_test("Invalid GitHub URL returns 400", passed, f"Status: {resp.status_code}")


async def test_zip_upload_happy_path(token: str) -> Optional[str]:
    """Test 4: Happy-path zip upload with vulnerable code"""
    print("\n=== Test 4: Zip Upload Happy Path ===")
    
    # Create in-memory zip with vulnerable Python file
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        vuln_code = '''import os
password = "hunter2"
eval(input("> "))
def add(a, b):
    return a + b
'''
        zf.writestr("vuln.py", vuln_code)
    
    zip_buffer.seek(0)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Upload
        files = {"file": ("test.zip", zip_buffer, "application/zip")}
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/scans/upload",
            headers=headers,
            files=files
        )
        
        if resp.status_code != 200:
            log_test("Zip upload - initiate", False, f"Status {resp.status_code}: {resp.text}")
            return None
        
        data = resp.json()
        scan_id = data.get("id")
        
        # Verify response
        checks = [
            (data.get("status") in ["queued", "scanning"], "status is queued/scanning"),
            (data.get("source") == "upload", "source is upload"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        if not all_checks_passed:
            log_test("Zip upload - initiate", False, "Response structure invalid")
            return None
        
        log_test("Zip upload - initiate", True, f"Scan ID: {scan_id}")
        
        # Poll for completion
        print(f"  Polling scan {scan_id} for completion...")
        for i in range(24):
            await asyncio.sleep(5)
            resp = await client.get(
                f"{BACKEND_URL}/code-quality/scans/{scan_id}",
                headers=headers
            )
            
            if resp.status_code != 200:
                log_test("Zip upload - poll", False, f"Status {resp.status_code}")
                return None
            
            data = resp.json()
            status = data.get("status")
            print(f"    Iteration {i+1}/24: status={status}")
            
            if status in ["done", "failed"]:
                break
        
        final_status = data.get("status")
        if final_status == "done":
            log_test("Zip upload - completion", True, f"Status: done")
        else:
            log_test("Zip upload - completion", False, f"Status: {final_status}, error: {data.get('error', 'N/A')}")
            return None
        
        # Get issues - expect at least 1 (hardcoded password or eval)
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans/{scan_id}/issues",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Zip upload - get issues", False, f"Status {resp.status_code}")
            return None
        
        issues = resp.json()
        has_issues = len(issues) >= 1
        log_test("Zip upload - get issues", has_issues, 
                f"Found {len(issues)} issues (expected >= 1 for hardcoded password/eval)")
        
        return scan_id


async def test_oversize_upload(token: str):
    """Test 5: Oversize upload (> 50 MB)"""
    print("\n=== Test 5: Oversize Upload ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create a 51 MB file
    print("  Creating 51 MB zip file...")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Write 51 MB of random data
        junk_data = b'x' * (51 * 1024 * 1024)
        zf.writestr("junk.bin", junk_data)
    
    zip_buffer.seek(0)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        files = {"file": ("large.zip", zip_buffer, "application/zip")}
        try:
            resp = await client.post(
                f"{BACKEND_URL}/code-quality/scans/upload",
                headers=headers,
                files=files
            )
            
            passed = resp.status_code == 413
            log_test("Oversize upload returns 413", passed, f"Status: {resp.status_code}")
        except Exception as e:
            # Connection might be closed by server
            log_test("Oversize upload returns 413", True, f"Connection closed (expected for oversize)")


async def test_non_zip_upload(token: str):
    """Test 6: Non-zip upload"""
    print("\n=== Test 6: Non-Zip Upload ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create a text file
    txt_buffer = io.BytesIO(b"This is not a zip file")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        files = {"file": ("test.txt", txt_buffer, "text/plain")}
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/scans/upload",
            headers=headers,
            files=files
        )
        
        passed = resp.status_code == 400
        log_test("Non-zip upload returns 400", passed, f"Status: {resp.status_code}")


async def test_integrations_crud(token: str):
    """Test 7: Integrations CRUD"""
    print("\n=== Test 7: Integrations CRUD ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    integration_id = None
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 7a. Create integration
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/integrations",
            headers=headers,
            json={
                "name": "Bad Sonar",
                "provider": "sonarqube",
                "base_url": "http://example.invalid",
                "token": "bogus",
                "project_key": "x"
            }
        )
        
        if resp.status_code != 200:
            log_test("Integration - create", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        integration_id = data.get("id")
        
        # Verify token is not in response but token_set is true
        checks = [
            ("token" not in data, "token not in response"),
            (data.get("token_set") == True, "token_set is true"),
            (data.get("provider") == "sonarqube", "provider is sonarqube"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Integration - create", all_checks_passed, 
                f"ID: {integration_id}, Failed: {failed_checks if failed_checks else 'none'}")
        
        if not integration_id:
            return
        
        # 7b. List integrations
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/integrations",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Integration - list", False, f"Status {resp.status_code}")
            return
        
        integrations = resp.json()
        found = None
        for integ in integrations:
            if integ.get("id") == integration_id:
                found = integ
                break
        
        if found:
            checks = [
                ("token" not in found, "token not in list response"),
                (found.get("token_set") == True, "token_set is true in list"),
            ]
            all_checks_passed = all(check[0] for check in checks)
            log_test("Integration - list", all_checks_passed, 
                    f"Found integration, token_set={found.get('token_set')}")
        else:
            log_test("Integration - list", False, "Integration not found in list")
        
        # 7c. Sync integration (should fail gracefully)
        print(f"  Syncing integration {integration_id} (expect graceful failure)...")
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/integrations/{integration_id}/sync",
            headers=headers
        )
        
        # Should return 4xx or 5xx HTTPException, not unhandled 500
        is_graceful_failure = resp.status_code in [400, 401, 403, 404, 500]
        
        # Check if it's a proper HTTPException response (has detail field)
        try:
            error_data = resp.json()
            has_detail = "detail" in error_data or "error" in str(error_data).lower()
        except:
            has_detail = False
        
        log_test("Integration - sync fails gracefully", is_graceful_failure and has_detail,
                f"Status: {resp.status_code}, has error detail: {has_detail}")
        
        # Check last_status after sync
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/integrations",
            headers=headers
        )
        
        if resp.status_code == 200:
            integrations = resp.json()
            found = None
            for integ in integrations:
                if integ.get("id") == integration_id:
                    found = integ
                    break
            
            if found:
                last_status = found.get("last_status", "")
                starts_with_error = last_status.startswith("error")
                log_test("Integration - last_status after sync", starts_with_error,
                        f"last_status: {last_status[:50]}")
        
        # 7d. Unknown provider
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/integrations",
            headers=headers,
            json={
                "name": "Unknown",
                "provider": "unknown_xyz",
                "base_url": "http://example.com",
                "token": "test"
            }
        )
        
        passed = resp.status_code in [400, 422]
        log_test("Integration - unknown provider", passed, f"Status: {resp.status_code}")
        
        # 7e. Delete integration
        resp = await client.delete(
            f"{BACKEND_URL}/code-quality/integrations/{integration_id}",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Integration - delete", False, f"Status {resp.status_code}")
            return
        
        log_test("Integration - delete", True, "Deleted successfully")
        
        # Re-delete should return 404
        resp = await client.delete(
            f"{BACKEND_URL}/code-quality/integrations/{integration_id}",
            headers=headers
        )
        
        passed = resp.status_code == 404
        log_test("Integration - re-delete returns 404", passed, f"Status: {resp.status_code}")


async def test_issue_fix(token: str, scan_id: Optional[str]):
    """Test 8: Issue fix endpoint"""
    print("\n=== Test 8: Issue Fix ===")
    
    if not scan_id:
        log_test("Issue fix - skipped", False, "No scan_id available (previous test failed)")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=90.0) as client:
        # Get issues from scan
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans/{scan_id}/issues",
            headers=headers
        )
        
        if resp.status_code != 200 or not resp.json():
            log_test("Issue fix - get issue", False, "No issues available")
            return
        
        issues = resp.json()
        issue_id = issues[0].get("id")
        
        if not issue_id:
            log_test("Issue fix - get issue", False, "Issue has no id")
            return
        
        log_test("Issue fix - get issue", True, f"Using issue {issue_id}")
        
        # Request fix
        print(f"  Requesting fix for issue {issue_id} (may take up to 60s)...")
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/issues/{issue_id}/fix",
            headers=headers,
            json={}
        )
        
        if resp.status_code != 200:
            log_test("Issue fix - generate", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        fix_data = resp.json()
        
        # Verify all required fields are present and non-empty
        required_fields = ["explanation", "patched_file", "diff", "test_hint"]
        checks = []
        for field in required_fields:
            value = fix_data.get(field, "")
            is_present = field in fix_data
            is_non_empty = bool(value and str(value).strip())
            checks.append((is_present and is_non_empty, f"{field} present and non-empty"))
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Issue fix - generate", all_checks_passed,
                f"Fields: {', '.join(required_fields)}, Failed: {failed_checks if failed_checks else 'none'}")
        
        # Verify fix is persisted
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/issues/{issue_id}",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Issue fix - persistence", False, f"Status {resp.status_code}")
            return
        
        issue_data = resp.json()
        has_fix = "fix" in issue_data and issue_data["fix"] is not None
        log_test("Issue fix - persistence", has_fix, f"Fix persisted: {has_fix}")


async def test_scan_list(token: str):
    """Test 9: Scan list"""
    print("\n=== Test 9: Scan List ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Scan list", False, f"Status {resp.status_code}")
            return
        
        scans = resp.json()
        
        # Should have at least 2 scans (github + upload from earlier tests)
        has_enough = len(scans) >= 2
        
        # Check if sorted by created_at desc
        is_sorted = True
        if len(scans) >= 2:
            for i in range(len(scans) - 1):
                if scans[i].get("created_at", "") < scans[i+1].get("created_at", ""):
                    is_sorted = False
                    break
        
        log_test("Scan list", has_enough and is_sorted,
                f"Found {len(scans)} scans (expected >= 2), sorted: {is_sorted}")


async def test_delete_scan(token: str, scan_id: Optional[str]):
    """Test 10: Delete scan"""
    print("\n=== Test 10: Delete Scan ===")
    
    if not scan_id:
        log_test("Delete scan - skipped", False, "No scan_id available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Delete scan
        resp = await client.delete(
            f"{BACKEND_URL}/code-quality/scans/{scan_id}",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Delete scan", False, f"Status {resp.status_code}")
            return
        
        log_test("Delete scan", True, f"Deleted scan {scan_id}")
        
        # Verify scan is gone
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans/{scan_id}",
            headers=headers
        )
        
        passed = resp.status_code == 404
        log_test("Delete scan - verify 404", passed, f"Status: {resp.status_code}")
        
        # Verify issues are gone
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans/{scan_id}/issues",
            headers=headers
        )
        
        passed = resp.status_code == 404
        log_test("Delete scan - issues gone", passed, f"Status: {resp.status_code}")


async def test_sonarqube_smoke(token: str):
    """Test 11: Smoke check on existing /api/sonarqube/* endpoints"""
    print("\n=== Test 11: SonarQube Smoke Check ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BACKEND_URL}/sonarqube/summary",
            headers=headers
        )
        
        # Should not return 500
        not_500 = resp.status_code != 500
        
        # Should return some data
        has_data = False
        if resp.status_code == 200:
            try:
                data = resp.json()
                has_data = bool(data)
            except:
                pass
        
        log_test("SonarQube smoke check", not_500 and has_data,
                f"Status: {resp.status_code}, has data: {has_data}")


async def main():
    """Run all tests"""
    print("=" * 80)
    print("Code Quality v2 Backend Test Suite")
    print("=" * 80)
    
    try:
        # Login
        print("\n=== Authentication ===")
        token = await login()
        print(f"✓ Logged in as {TEST_EMAIL}")
        
        # Run tests
        await test_auth_gate(token)
        
        github_scan_id = await test_github_scan_happy_path(token)
        
        await test_invalid_github_url(token)
        
        upload_scan_id = await test_zip_upload_happy_path(token)
        
        await test_oversize_upload(token)
        
        await test_non_zip_upload(token)
        
        await test_integrations_crud(token)
        
        # Use upload scan for fix test (more likely to have issues)
        await test_issue_fix(token, upload_scan_id)
        
        await test_scan_list(token)
        
        # Delete github scan
        await test_delete_scan(token, github_scan_id)
        
        await test_sonarqube_smoke(token)
        
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
