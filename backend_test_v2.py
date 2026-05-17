#!/usr/bin/env python3
"""
Code Quality v2 - Focused Regression Test
Tests NEW endpoints: demo/seed and integrations PATCH
"""
import asyncio
import json
import sys
from typing import Dict, Any, Optional

import httpx

# Configuration
BACKEND_URL = "https://file-share-center.preview.emergentagent.com/api"
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


async def test_demo_seed_with_reset(token: str):
    """Test 1: POST /api/code-quality/demo/seed?reset=true"""
    print("\n=== Test 1: Demo Seed with Reset ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Call seed with reset=true
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/demo/seed?reset=true",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Demo seed with reset - status 200", False, f"Status {resp.status_code}: {resp.text}")
            return False
        
        data = resp.json()
        
        # Verify response structure
        checks = [
            (data.get("ok") == True, "ok is true"),
            (data.get("reset") == True, "reset is true"),
            (data.get("integrations_added", 0) >= 1, f"integrations_added >= 1 (got {data.get('integrations_added')})"),
            (data.get("scans_added", 0) >= 1, f"scans_added >= 1 (got {data.get('scans_added')})"),
            (data.get("issues_added", 0) >= 1, f"issues_added >= 1 (got {data.get('issues_added')})"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Demo seed with reset - response structure", all_checks_passed,
                f"integrations={data.get('integrations_added')}, scans={data.get('scans_added')}, issues={data.get('issues_added')}, Failed: {failed_checks if failed_checks else 'none'}")
        
        return all_checks_passed


async def test_integrations_after_seed(token: str) -> Optional[str]:
    """Test 2: GET /api/code-quality/integrations after seed - verify >=3 items, one disabled"""
    print("\n=== Test 2: Integrations After Seed ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/integrations",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Integrations list after seed", False, f"Status {resp.status_code}")
            return None
        
        integrations = resp.json()
        
        # Check count >= 3
        count_check = len(integrations) >= 3
        
        # Check for at least one disabled (Semgrep)
        disabled_integrations = [i for i in integrations if i.get("enabled") == False]
        has_disabled = len(disabled_integrations) > 0
        
        # Check that tokens are never in response
        has_token_field = any("token" in i for i in integrations)
        
        # Find Semgrep integration
        semgrep_integ = None
        for i in integrations:
            if i.get("provider") == "semgrep" or "Semgrep" in i.get("name", ""):
                semgrep_integ = i
                break
        
        checks = [
            (count_check, f"count >= 3 (got {len(integrations)})"),
            (has_disabled, f"has disabled integration (found {len(disabled_integrations)})"),
            (not has_token_field, "no 'token' field in any integration"),
            (semgrep_integ is not None, "Semgrep integration exists"),
        ]
        
        if semgrep_integ:
            checks.append((semgrep_integ.get("enabled") == False, "Semgrep is disabled"))
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Integrations list after seed", all_checks_passed,
                f"Count: {len(integrations)}, Disabled: {len(disabled_integrations)}, Failed: {failed_checks if failed_checks else 'none'}")
        
        # Return an enabled integration ID for later tests
        enabled_integ = next((i for i in integrations if i.get("enabled") == True), None)
        return enabled_integ.get("id") if enabled_integ else None


async def test_scans_after_seed(token: str) -> Optional[str]:
    """Test 3: GET /api/code-quality/scans after seed - verify >=5 items, one failed, one from integration"""
    print("\n=== Test 3: Scans After Seed ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Scans list after seed", False, f"Status {resp.status_code}")
            return None
        
        scans = resp.json()
        
        # Check count >= 5
        count_check = len(scans) >= 5
        
        # Check for at least one failed
        failed_scans = [s for s in scans if s.get("status") == "failed"]
        has_failed = len(failed_scans) > 0
        
        # Check for at least one from integration
        integration_scans = [s for s in scans if s.get("source") == "integration"]
        has_integration = len(integration_scans) > 0
        
        checks = [
            (count_check, f"count >= 5 (got {len(scans)})"),
            (has_failed, f"has failed scan (found {len(failed_scans)})"),
            (has_integration, f"has integration scan (found {len(integration_scans)})"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Scans list after seed", all_checks_passed,
                f"Count: {len(scans)}, Failed: {len(failed_scans)}, Integration: {len(integration_scans)}, Failed: {failed_checks if failed_checks else 'none'}")
        
        # Find GitHub scan with acme-corp/checkout-service
        github_scan = None
        for s in scans:
            if s.get("source") == "github" and "acme-corp/checkout-service" in s.get("source_label", ""):
                github_scan = s
                break
        
        return github_scan.get("id") if github_scan else None


async def test_scan_issues_with_fix(token: str, scan_id: Optional[str]):
    """Test 4: GET /api/code-quality/scans/{id}/issues - verify at least one issue has pre-baked fix"""
    print("\n=== Test 4: Scan Issues with Pre-baked Fix ===")
    
    if not scan_id:
        log_test("Scan issues with fix - skipped", False, "No GitHub scan ID available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans/{scan_id}/issues",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Scan issues with fix", False, f"Status {resp.status_code}")
            return
        
        issues = resp.json()
        
        # Check for at least one issue with fix
        issues_with_fix = [i for i in issues if i.get("fix") is not None]
        has_fix = len(issues_with_fix) > 0
        
        # Verify fix structure
        fix_valid = False
        if has_fix:
            fix = issues_with_fix[0].get("fix", {})
            required_keys = ["explanation", "patched_file", "diff", "test_hint"]
            fix_valid = all(key in fix and fix[key] for key in required_keys)
        
        checks = [
            (len(issues) >= 1, f"has issues (got {len(issues)})"),
            (has_fix, f"has issue with fix (found {len(issues_with_fix)})"),
            (fix_valid, "fix has all required keys (explanation, patched_file, diff, test_hint)"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Scan issues with fix", all_checks_passed,
                f"Issues: {len(issues)}, With fix: {len(issues_with_fix)}, Failed: {failed_checks if failed_checks else 'none'}")


async def test_patch_integration_disable(token: str, integration_id: Optional[str]) -> Optional[str]:
    """Test 5: PATCH /api/code-quality/integrations/{id} - disable integration"""
    print("\n=== Test 5: PATCH Integration - Disable ===")
    
    if not integration_id:
        log_test("PATCH integration disable - skipped", False, "No integration ID available")
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Disable integration
        resp = await client.patch(
            f"{BACKEND_URL}/code-quality/integrations/{integration_id}",
            headers=headers,
            json={"enabled": False}
        )
        
        if resp.status_code != 200:
            log_test("PATCH integration disable", False, f"Status {resp.status_code}: {resp.text}")
            return None
        
        data = resp.json()
        
        # Verify response
        checks = [
            (data.get("enabled") == False, "enabled is false"),
            ("token" not in data, "token not in response"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("PATCH integration disable", all_checks_passed,
                f"enabled={data.get('enabled')}, Failed: {failed_checks if failed_checks else 'none'}")
        
        return integration_id if all_checks_passed else None


async def test_sync_disabled_integration(token: str, integration_id: Optional[str]):
    """Test 6: POST /api/code-quality/integrations/{id}/sync on disabled integration - expect 400"""
    print("\n=== Test 6: Sync Disabled Integration ===")
    
    if not integration_id:
        log_test("Sync disabled integration - skipped", False, "No disabled integration ID available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/integrations/{integration_id}/sync",
            headers=headers
        )
        
        # Should return 400 (not 500)
        status_check = resp.status_code == 400
        
        # Check detail mentions disabled
        detail_check = False
        if resp.status_code in [400, 500]:
            try:
                error_data = resp.json()
                detail = error_data.get("detail", "")
                detail_check = "disabled" in detail.lower()
            except:
                pass
        
        checks = [
            (status_check, f"status is 400 (got {resp.status_code})"),
            (detail_check, "detail mentions 'disabled'"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Sync disabled integration", all_checks_passed,
                f"Status: {resp.status_code}, Failed: {failed_checks if failed_checks else 'none'}")


async def test_patch_integration_enable(token: str, integration_id: Optional[str]):
    """Test 7: PATCH /api/code-quality/integrations/{id} - re-enable integration"""
    print("\n=== Test 7: PATCH Integration - Re-enable ===")
    
    if not integration_id:
        log_test("PATCH integration enable - skipped", False, "No integration ID available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Re-enable integration
        resp = await client.patch(
            f"{BACKEND_URL}/code-quality/integrations/{integration_id}",
            headers=headers,
            json={"enabled": True}
        )
        
        if resp.status_code != 200:
            log_test("PATCH integration enable", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Verify response
        checks = [
            (data.get("enabled") == True, "enabled is true"),
            ("token" not in data, "token not in response"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("PATCH integration enable", all_checks_passed,
                f"enabled={data.get('enabled')}, Failed: {failed_checks if failed_checks else 'none'}")


async def test_patch_integration_rename(token: str, integration_id: Optional[str]):
    """Test 8: PATCH /api/code-quality/integrations/{id} - rename integration"""
    print("\n=== Test 8: PATCH Integration - Rename ===")
    
    if not integration_id:
        log_test("PATCH integration rename - skipped", False, "No integration ID available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    new_name = "Renamed Scanner X"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Rename integration
        resp = await client.patch(
            f"{BACKEND_URL}/code-quality/integrations/{integration_id}",
            headers=headers,
            json={"name": new_name}
        )
        
        if resp.status_code != 200:
            log_test("PATCH integration rename", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Verify response
        name_check = data.get("name") == new_name
        
        log_test("PATCH integration rename", name_check,
                f"name='{data.get('name')}' (expected '{new_name}')")


async def test_patch_integration_empty_body(token: str, integration_id: Optional[str]):
    """Test 9: PATCH /api/code-quality/integrations/{id} with empty body - expect 400"""
    print("\n=== Test 9: PATCH Integration - Empty Body ===")
    
    if not integration_id:
        log_test("PATCH integration empty body - skipped", False, "No integration ID available")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.patch(
            f"{BACKEND_URL}/code-quality/integrations/{integration_id}",
            headers=headers,
            json={}
        )
        
        status_check = resp.status_code == 400
        
        log_test("PATCH integration empty body", status_check,
                f"Status: {resp.status_code} (expected 400)")


async def test_patch_integration_not_found(token: str):
    """Test 10: PATCH /api/code-quality/integrations/{id} with non-existent ID - expect 404"""
    print("\n=== Test 10: PATCH Integration - Not Found ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    fake_id = "nonexistent123456789"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.patch(
            f"{BACKEND_URL}/code-quality/integrations/{fake_id}",
            headers=headers,
            json={"enabled": True}
        )
        
        status_check = resp.status_code == 404
        
        log_test("PATCH integration not found", status_check,
                f"Status: {resp.status_code} (expected 404)")


async def test_demo_seed_without_reset(token: str):
    """Test 11: POST /api/code-quality/demo/seed (reset=false) - cumulative"""
    print("\n=== Test 11: Demo Seed Without Reset (Cumulative) ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get current counts
        resp = await client.get(f"{BACKEND_URL}/code-quality/integrations", headers=headers)
        initial_integrations = len(resp.json()) if resp.status_code == 200 else 0
        
        resp = await client.get(f"{BACKEND_URL}/code-quality/scans", headers=headers)
        initial_scans = len(resp.json()) if resp.status_code == 200 else 0
        
        # Call seed with reset=false
        resp = await client.post(
            f"{BACKEND_URL}/code-quality/demo/seed?reset=false",
            headers=headers
        )
        
        if resp.status_code != 200:
            log_test("Demo seed without reset", False, f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Get new counts
        resp = await client.get(f"{BACKEND_URL}/code-quality/integrations", headers=headers)
        new_integrations = len(resp.json()) if resp.status_code == 200 else 0
        
        resp = await client.get(f"{BACKEND_URL}/code-quality/scans", headers=headers)
        new_scans = len(resp.json()) if resp.status_code == 200 else 0
        
        # Verify cumulative (should have more items)
        integrations_increased = new_integrations > initial_integrations
        scans_increased = new_scans > initial_scans
        
        checks = [
            (data.get("ok") == True, "ok is true"),
            (data.get("reset") == False, "reset is false"),
            (integrations_increased, f"integrations increased ({initial_integrations} -> {new_integrations})"),
            (scans_increased, f"scans increased ({initial_scans} -> {new_scans})"),
        ]
        
        all_checks_passed = all(check[0] for check in checks)
        failed_checks = [check[1] for check in checks if not check[0]]
        
        log_test("Demo seed without reset", all_checks_passed,
                f"Integrations: {initial_integrations} -> {new_integrations}, Scans: {initial_scans} -> {new_scans}, Failed: {failed_checks if failed_checks else 'none'}")


async def test_auth_enforcement(token: str):
    """Test 12: Auth enforcement - all new endpoints must 401 without Authorization"""
    print("\n=== Test 12: Auth Enforcement ===")
    
    endpoints = [
        ("POST", "/code-quality/demo/seed"),
        ("PATCH", "/code-quality/integrations/fake123"),
    ]
    
    all_passed = True
    async with httpx.AsyncClient(timeout=30.0) as client:
        for method, path in endpoints:
            if method == "POST":
                resp = await client.post(f"{BACKEND_URL}{path}", json={})
            elif method == "PATCH":
                resp = await client.patch(f"{BACKEND_URL}{path}", json={})
            
            if resp.status_code == 401:
                print(f"  ✓ {method} {path} correctly returns 401")
            else:
                print(f"  ✗ {method} {path} returned {resp.status_code} instead of 401")
                all_passed = False
    
    log_test("Auth enforcement - new endpoints", all_passed)


async def test_scans_smoke_check(token: str):
    """Test 13: Smoke check - GET /api/code-quality/scans still works"""
    print("\n=== Test 13: Scans Smoke Check ===")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BACKEND_URL}/code-quality/scans",
            headers=headers
        )
        
        # Should not return 500
        not_500 = resp.status_code != 500
        is_200 = resp.status_code == 200
        
        log_test("Scans smoke check", not_500 and is_200,
                f"Status: {resp.status_code} (expected 200, not 500)")


async def main():
    """Run all tests"""
    print("=" * 80)
    print("Code Quality v2 - Focused Regression Test")
    print("NEW endpoints: demo/seed and integrations PATCH")
    print("=" * 80)
    
    try:
        # Login
        print("\n=== Authentication ===")
        token = await login()
        print(f"✓ Logged in as {TEST_EMAIL}")
        
        # Run tests in order
        await test_demo_seed_with_reset(token)
        
        enabled_integration_id = await test_integrations_after_seed(token)
        
        github_scan_id = await test_scans_after_seed(token)
        
        await test_scan_issues_with_fix(token, github_scan_id)
        
        disabled_integration_id = await test_patch_integration_disable(token, enabled_integration_id)
        
        await test_sync_disabled_integration(token, disabled_integration_id)
        
        await test_patch_integration_enable(token, disabled_integration_id)
        
        await test_patch_integration_rename(token, disabled_integration_id)
        
        await test_patch_integration_empty_body(token, disabled_integration_id)
        
        await test_patch_integration_not_found(token)
        
        await test_demo_seed_without_reset(token)
        
        await test_auth_enforcement(token)
        
        await test_scans_smoke_check(token)
        
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
