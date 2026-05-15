#!/usr/bin/env python3
"""
F-02 Predictive Triage Backend Test Suite
Tests all predictive triage endpoints, WebSocket, and auth requirements.
"""
import requests
import json
import time
import websocket
from typing import Optional, Dict, Any

# Backend URL from frontend/.env
BASE_URL = "https://code-snapshot-21.preview.emergentagent.com/api"
WS_URL = "wss://anomaly-detect-42.preview.emergentagent.com/api/ws/predictive-alerts"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@triage.ai"
ADMIN_PASSWORD = "admin123"

class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append(f"✅ {test_name}" + (f": {details}" if details else ""))
    
    def add_fail(self, test_name: str, error: str):
        self.failed.append(f"❌ {test_name}: {error}")
    
    def add_warning(self, test_name: str, warning: str):
        self.warnings.append(f"⚠️  {test_name}: {warning}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("F-02 PREDICTIVE TRIAGE TEST RESULTS")
        print("="*80)
        
        if self.passed:
            print(f"\n✅ PASSED ({len(self.passed)}):")
            for p in self.passed:
                print(f"  {p}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"  {w}")
        
        if self.failed:
            print(f"\n❌ FAILED ({len(self.failed)}):")
            for f in self.failed:
                print(f"  {f}")
        
        print("\n" + "="*80)
        print(f"TOTAL: {len(self.passed)} passed, {len(self.failed)} failed, {len(self.warnings)} warnings")
        print("="*80 + "\n")
        
        return len(self.failed) == 0

results = TestResult()

def login() -> Optional[str]:
    """Login and return JWT token"""
    try:
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token")
            results.add_pass("Login", f"Got JWT token for {ADMIN_EMAIL}")
            return token
        else:
            results.add_fail("Login", f"Status {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        results.add_fail("Login", str(e))
        return None

def test_auth_required(token: str):
    """Test that endpoints reject requests without auth"""
    endpoints = [
        ("GET", "/predictive-services/summary"),
        ("GET", "/predictive-incidents"),
        ("POST", "/predictive-triage"),
    ]
    
    all_rejected = True
    for method, path in endpoints:
        try:
            if method == "GET":
                resp = requests.get(f"{BASE_URL}{path}", timeout=10)
            else:
                resp = requests.post(f"{BASE_URL}{path}", json={}, timeout=10)
            
            if resp.status_code == 401:
                continue
            else:
                results.add_fail(f"Auth required for {method} {path}", 
                               f"Expected 401, got {resp.status_code}")
                all_rejected = False
        except Exception as e:
            results.add_fail(f"Auth required for {method} {path}", str(e))
            all_rejected = False
    
    if all_rejected:
        results.add_pass("Auth required", "All endpoints reject unauthenticated requests (401)")

def test_predictive_services_summary(token: str):
    """Test GET /api/predictive-services/summary"""
    try:
        resp = requests.get(
            f"{BASE_URL}/predictive-services/summary",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            results.add_fail("GET /predictive-services/summary", 
                           f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Should return list of 5 services
        if not isinstance(data, list):
            results.add_fail("GET /predictive-services/summary", 
                           f"Expected list, got {type(data)}")
            return
        
        if len(data) != 5:
            results.add_fail("GET /predictive-services/summary", 
                           f"Expected 5 services, got {len(data)}")
            return
        
        # Check structure of each service
        required_fields = ["service_name", "max_risk", "avg_risk", "predictions", "min_eta"]
        for svc in data:
            for field in required_fields:
                if field not in svc:
                    results.add_fail("GET /predictive-services/summary", 
                                   f"Missing field '{field}' in service {svc.get('service_name', 'unknown')}")
                    return
        
        results.add_pass("GET /predictive-services/summary", 
                        f"Returned {len(data)} services with correct structure")
        
    except Exception as e:
        results.add_fail("GET /predictive-services/summary", str(e))

def test_list_predictive_incidents(token: str) -> Optional[str]:
    """Test GET /api/predictive-incidents and return an incident ID"""
    try:
        resp = requests.get(
            f"{BASE_URL}/predictive-incidents?status=open",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            results.add_fail("GET /predictive-incidents?status=open", 
                           f"Status {resp.status_code}: {resp.text}")
            return None
        
        data = resp.json()
        
        if not isinstance(data, list):
            results.add_fail("GET /predictive-incidents?status=open", 
                           f"Expected list, got {type(data)}")
            return None
        
        if len(data) == 0:
            results.add_warning("GET /predictive-incidents?status=open", 
                              "No open incidents found (may need to run POST /predictive-triage first)")
            return None
        
        # Check structure of first incident
        incident = data[0]
        required_fields = [
            "id", "service_name", "metric_type", "current_value", "expected_value",
            "anomaly_score", "risk_score", "predicted_failure", 
            "estimated_time_to_incident", "recommended_action", "status", "created_at"
        ]
        
        missing_fields = [f for f in required_fields if f not in incident]
        if missing_fields:
            results.add_fail("GET /predictive-incidents?status=open", 
                           f"Missing fields: {', '.join(missing_fields)}")
            return None
        
        # Validate field types and values
        if not incident["id"].startswith("PRD-"):
            results.add_fail("GET /predictive-incidents?status=open", 
                           f"ID should start with 'PRD-', got {incident['id']}")
            return None
        
        valid_metrics = ["cpu_usage", "memory_usage", "db_connections", "api_latency_ms", "queue_depth"]
        if incident["metric_type"] not in valid_metrics:
            results.add_fail("GET /predictive-incidents?status=open", 
                           f"Invalid metric_type: {incident['metric_type']}")
            return None
        
        if not (0 <= incident["risk_score"] <= 100):
            results.add_fail("GET /predictive-incidents?status=open", 
                           f"risk_score should be 0-100, got {incident['risk_score']}")
            return None
        
        if not isinstance(incident["predicted_failure"], bool):
            results.add_fail("GET /predictive-incidents?status=open", 
                           f"predicted_failure should be bool, got {type(incident['predicted_failure'])}")
            return None
        
        if incident["status"] != "open":
            results.add_fail("GET /predictive-incidents?status=open", 
                           f"Expected status='open', got '{incident['status']}'")
            return None
        
        if not incident["recommended_action"] or len(incident["recommended_action"]) == 0:
            results.add_fail("GET /predictive-incidents?status=open", 
                           "recommended_action is empty")
            return None
        
        results.add_pass("GET /predictive-incidents?status=open", 
                        f"Returned {len(data)} incidents with correct structure")
        
        return incident["id"]
        
    except Exception as e:
        results.add_fail("GET /predictive-incidents?status=open", str(e))
        return None

def test_trigger_predictive_triage(token: str) -> int:
    """Test POST /api/predictive-triage"""
    try:
        resp = requests.post(
            f"{BASE_URL}/predictive-triage",
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=30  # May take longer due to Claude calls
        )
        
        if resp.status_code != 200:
            results.add_fail("POST /predictive-triage", 
                           f"Status {resp.status_code}: {resp.text}")
            return 0
        
        data = resp.json()
        
        if "generated" not in data:
            results.add_fail("POST /predictive-triage", 
                           "Missing 'generated' field in response")
            return 0
        
        if "predictions" not in data:
            results.add_fail("POST /predictive-triage", 
                           "Missing 'predictions' field in response")
            return 0
        
        if not isinstance(data["generated"], int):
            results.add_fail("POST /predictive-triage", 
                           f"'generated' should be int, got {type(data['generated'])}")
            return 0
        
        results.add_pass("POST /predictive-triage", 
                        f"Generated {data['generated']} predictions")
        
        return data["generated"]
        
    except Exception as e:
        results.add_fail("POST /predictive-triage", str(e))
        return 0

def test_incident_trend(token: str, incident_id: str):
    """Test GET /api/predictive-incidents/{id}/trend"""
    try:
        resp = requests.get(
            f"{BASE_URL}/predictive-incidents/{incident_id}/trend?points=60",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            results.add_fail(f"GET /predictive-incidents/{incident_id}/trend", 
                           f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        required_fields = ["incident", "threshold", "unit", "series"]
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            results.add_fail(f"GET /predictive-incidents/{incident_id}/trend", 
                           f"Missing fields: {', '.join(missing_fields)}")
            return
        
        if not isinstance(data["series"], list):
            results.add_fail(f"GET /predictive-incidents/{incident_id}/trend", 
                           f"'series' should be list, got {type(data['series'])}")
            return
        
        if len(data["series"]) < 30:
            results.add_fail(f"GET /predictive-incidents/{incident_id}/trend", 
                           f"Expected at least 30 points in series, got {len(data['series'])}")
            return
        
        # Check series structure
        if len(data["series"]) > 0:
            point = data["series"][0]
            if "value" not in point or "timestamp" not in point:
                results.add_fail(f"GET /predictive-incidents/{incident_id}/trend", 
                               "Series points missing 'value' or 'timestamp'")
                return
        
        results.add_pass(f"GET /predictive-incidents/{incident_id}/trend", 
                        f"Returned {len(data['series'])} data points")
        
    except Exception as e:
        results.add_fail(f"GET /predictive-incidents/{incident_id}/trend", str(e))

def test_acknowledge_incident(token: str, incident_id: str):
    """Test PATCH /api/predictive-incidents/{id}/acknowledge"""
    try:
        resp = requests.patch(
            f"{BASE_URL}/predictive-incidents/{incident_id}/acknowledge",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            results.add_fail(f"PATCH /predictive-incidents/{incident_id}/acknowledge", 
                           f"Status {resp.status_code}: {resp.text}")
            return False
        
        data = resp.json()
        
        if data.get("status") != "acknowledged":
            results.add_fail(f"PATCH /predictive-incidents/{incident_id}/acknowledge", 
                           f"Expected status='acknowledged', got '{data.get('status')}'")
            return False
        
        results.add_pass(f"PATCH /predictive-incidents/{incident_id}/acknowledge", 
                        "Status changed to 'acknowledged'")
        return True
        
    except Exception as e:
        results.add_fail(f"PATCH /predictive-incidents/{incident_id}/acknowledge", str(e))
        return False

def test_resolve_incident(token: str, incident_id: str):
    """Test PATCH /api/predictive-incidents/{id}/resolve"""
    try:
        resp = requests.patch(
            f"{BASE_URL}/predictive-incidents/{incident_id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            results.add_fail(f"PATCH /predictive-incidents/{incident_id}/resolve", 
                           f"Status {resp.status_code}: {resp.text}")
            return False
        
        data = resp.json()
        
        if data.get("status") != "resolved":
            results.add_fail(f"PATCH /predictive-incidents/{incident_id}/resolve", 
                           f"Expected status='resolved', got '{data.get('status')}'")
            return False
        
        if data.get("resolved_by") != ADMIN_EMAIL:
            results.add_fail(f"PATCH /predictive-incidents/{incident_id}/resolve", 
                           f"Expected resolved_by='{ADMIN_EMAIL}', got '{data.get('resolved_by')}'")
            return False
        
        results.add_pass(f"PATCH /predictive-incidents/{incident_id}/resolve", 
                        f"Status changed to 'resolved', resolved_by={ADMIN_EMAIL}")
        return True
        
    except Exception as e:
        results.add_fail(f"PATCH /predictive-incidents/{incident_id}/resolve", str(e))
        return False

def test_min_risk_filter(token: str):
    """Test GET /api/predictive-incidents?min_risk=60"""
    try:
        resp = requests.get(
            f"{BASE_URL}/predictive-incidents?min_risk=60",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            results.add_fail("GET /predictive-incidents?min_risk=60", 
                           f"Status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        if not isinstance(data, list):
            results.add_fail("GET /predictive-incidents?min_risk=60", 
                           f"Expected list, got {type(data)}")
            return
        
        # Check all returned incidents have risk_score >= 60
        for inc in data:
            if inc.get("risk_score", 0) < 60:
                results.add_fail("GET /predictive-incidents?min_risk=60", 
                               f"Found incident with risk_score={inc.get('risk_score')} < 60")
                return
        
        results.add_pass("GET /predictive-incidents?min_risk=60", 
                        f"All {len(data)} incidents have risk_score >= 60")
        
    except Exception as e:
        results.add_fail("GET /predictive-incidents?min_risk=60", str(e))

def test_websocket(token: str):
    """Test WebSocket /api/ws/predictive-alerts"""
    try:
        ws_url_with_token = f"{WS_URL}?token={token}"
        
        ws = websocket.create_connection(ws_url_with_token, timeout=10)
        
        # Should receive snapshot on connect
        msg = ws.recv()
        data = json.loads(msg)
        
        if data.get("event") != "snapshot":
            results.add_fail("WebSocket /api/ws/predictive-alerts", 
                           f"Expected first message event='snapshot', got '{data.get('event')}'")
            ws.close()
            return
        
        if "data" not in data:
            results.add_fail("WebSocket /api/ws/predictive-alerts", 
                           "Snapshot message missing 'data' field")
            ws.close()
            return
        
        if not isinstance(data["data"], list):
            results.add_fail("WebSocket /api/ws/predictive-alerts", 
                           f"Snapshot data should be list, got {type(data['data'])}")
            ws.close()
            return
        
        # Test ping/pong
        ws.send("ping")
        pong_msg = ws.recv()
        pong_data = json.loads(pong_msg)
        
        if pong_data.get("event") != "pong":
            results.add_fail("WebSocket /api/ws/predictive-alerts", 
                           f"Expected pong response, got '{pong_data.get('event')}'")
            ws.close()
            return
        
        ws.close()
        
        results.add_pass("WebSocket /api/ws/predictive-alerts", 
                        f"Connected, received snapshot with {len(data['data'])} items, ping/pong works")
        
    except Exception as e:
        results.add_fail("WebSocket /api/ws/predictive-alerts", str(e))

def test_websocket_auth_required():
    """Test WebSocket rejects invalid token"""
    try:
        ws_url_with_bad_token = f"{WS_URL}?token=invalid_token_12345"
        
        try:
            ws = websocket.create_connection(ws_url_with_bad_token, timeout=5)
            # If we get here, connection was accepted (should have been rejected)
            ws.close()
            results.add_fail("WebSocket auth required", 
                           "WebSocket accepted invalid token (should reject with 4401)")
        except websocket.WebSocketBadStatusException as e:
            # Expected - connection should be rejected
            results.add_pass("WebSocket auth required", 
                           "WebSocket correctly rejects invalid token")
        except Exception as e:
            # Connection closed immediately is also acceptable
            if "Connection is already closed" in str(e) or "4401" in str(e):
                results.add_pass("WebSocket auth required", 
                               "WebSocket correctly rejects invalid token")
            else:
                results.add_warning("WebSocket auth required", 
                                  f"Unexpected error: {str(e)}")
        
    except Exception as e:
        results.add_fail("WebSocket auth required", str(e))

def main():
    print("\n" + "="*80)
    print("Starting F-02 Predictive Triage Backend Tests")
    print("="*80 + "\n")
    
    # 1. Login
    token = login()
    if not token:
        print("\n❌ Cannot proceed without authentication token")
        results.print_summary()
        return 1
    
    # 2. Test auth required
    test_auth_required(token)
    
    # 3. Test POST /predictive-triage to generate predictions
    print("\n🔄 Triggering predictive triage (may take 20-30s due to Claude calls)...")
    generated = test_trigger_predictive_triage(token)
    
    # Wait a moment for data to be available
    if generated > 0:
        time.sleep(2)
    
    # 4. Test GET /predictive-services/summary
    test_predictive_services_summary(token)
    
    # 5. Test GET /predictive-incidents and get an incident ID
    incident_id = test_list_predictive_incidents(token)
    
    # If no incidents found, try triggering again
    if not incident_id and generated == 0:
        print("\n🔄 No incidents found, triggering predictive triage again...")
        generated = test_trigger_predictive_triage(token)
        if generated > 0:
            time.sleep(2)
            incident_id = test_list_predictive_incidents(token)
    
    # 6. Test min_risk filter
    test_min_risk_filter(token)
    
    # 7. Test incident-specific endpoints if we have an ID
    if incident_id:
        test_incident_trend(token, incident_id)
        test_acknowledge_incident(token, incident_id)
        test_resolve_incident(token, incident_id)
    else:
        results.add_warning("Incident-specific tests", 
                          "Skipped (no open incidents available)")
    
    # 8. Test WebSocket
    print("\n🔌 Testing WebSocket connection...")
    test_websocket(token)
    test_websocket_auth_required()
    
    # Print summary
    success = results.print_summary()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
