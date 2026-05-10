from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import logging
import random
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

app = FastAPI(title="TriageAI API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("triageai")


# -------------------- MODELS --------------------
Severity = Literal["critical", "high", "medium", "low"]
AlertStatus = Literal["active", "resolved", "noise"]
IncidentStatus = Literal["open", "triaging", "resolved"]


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: f"ALT-{uuid.uuid4().hex[:8].upper()}")
    source: str  # cloudwatch | datadog | pagerduty | grafana | prometheus
    severity: Severity
    service: str
    region: str
    title: str
    description: Optional[str] = ""
    status: AlertStatus = "active"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AlertIngest(BaseModel):
    source: str
    severity: Severity
    service: str
    region: str
    title: str
    description: Optional[str] = ""


class TriageRequest(BaseModel):
    alert_ids: List[str]


class RootCause(BaseModel):
    rank: int
    hypothesis: str
    confidence: Literal["high", "medium", "low"]
    supporting_alert_ids: List[str] = []
    reasoning: str


class RemediationStep(BaseModel):
    phase: Literal["immediate", "short-term", "long-term"]
    action: str
    cli_command: Optional[str] = None


class TriageResult(BaseModel):
    id: str = Field(default_factory=lambda: f"TRG-{uuid.uuid4().hex[:8].upper()}")
    incident_id: str
    alert_ids: List[str]
    priority: Literal["P1", "P2", "P3", "P4"]
    blast_radius: str
    mttr_estimate_minutes: int
    affected_services: List[str]
    summary: str
    noise_alert_ids: List[str] = []
    root_causes: List[RootCause] = []
    remediation: List[RemediationStep] = []
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: f"INC-{uuid.uuid4().hex[:8].upper()}")
    title: str
    priority: Literal["P1", "P2", "P3", "P4"]
    blast_radius: str = ""
    status: IncidentStatus = "open"
    affected_services: List[str] = []
    alert_ids: List[str] = []
    triage_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None


# -------------------- HELPERS --------------------
async def _doc(model: BaseModel) -> dict:
    return model.model_dump()


def _strip_id(d: dict) -> dict:
    d.pop("_id", None)
    return d


# -------------------- ROUTES --------------------
@api_router.get("/")
async def root():
    return {"service": "TriageAI", "status": "operational"}


@api_router.post("/alerts/ingest", response_model=Alert)
async def ingest_alert(payload: AlertIngest):
    alert = Alert(**payload.model_dump())
    await db.alerts.insert_one(alert.model_dump())
    return alert


@api_router.get("/alerts", response_model=List[Alert])
async def list_alerts(status: Optional[AlertStatus] = None, limit: int = 200):
    q = {}
    if status:
        q["status"] = status
    docs = await db.alerts.find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs


@api_router.patch("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    res = await db.alerts.update_one({"id": alert_id}, {"$set": {"status": "resolved"}})
    if res.matched_count == 0:
        raise HTTPException(404, "Alert not found")
    return {"id": alert_id, "status": "resolved"}


@api_router.post("/alerts/resolve-bulk")
async def resolve_alerts(body: TriageRequest):
    await db.alerts.update_many({"id": {"$in": body.alert_ids}}, {"$set": {"status": "resolved"}})
    # mark related incidents as resolved if all alerts resolved
    incidents = await db.incidents.find({"alert_ids": {"$in": body.alert_ids}}, {"_id": 0}).to_list(100)
    now = datetime.now(timezone.utc).isoformat()
    for inc in incidents:
        await db.incidents.update_one(
            {"id": inc["id"]},
            {"$set": {"status": "resolved", "resolved_at": now}}
        )
    return {"resolved": len(body.alert_ids)}


@api_router.get("/incidents", response_model=List[Incident])
async def list_incidents(limit: int = 100):
    docs = await db.incidents.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return docs


@api_router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    inc = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not inc:
        raise HTTPException(404, "Not found")
    triage = None
    if inc.get("triage_id"):
        triage = await db.triage_results.find_one({"id": inc["triage_id"]}, {"_id": 0})
    alerts = await db.alerts.find({"id": {"$in": inc.get("alert_ids", [])}}, {"_id": 0}).to_list(100)
    return {"incident": inc, "triage": triage, "alerts": alerts}


# ---------- AI TRIAGE ----------
TRIAGE_SYSTEM = """You are TriageAI, an expert SRE/DevOps incident triage engine.
You analyze a batch of cloud monitoring alerts and produce a structured triage report.

ALWAYS respond with ONLY a valid JSON object (no prose, no markdown fences) matching this schema:
{
  "priority": "P1" | "P2" | "P3" | "P4",
  "blast_radius": "<short string e.g. 'Single AZ', 'Multi-region', 'Customer-facing'>",
  "mttr_estimate_minutes": <integer>,
  "affected_services": ["svc-a", "svc-b"],
  "summary": "<one paragraph executive summary>",
  "noise_alert_ids": ["ALT-..."],
  "root_causes": [
     {"rank": 1, "hypothesis": "...", "confidence": "high|medium|low",
      "supporting_alert_ids": ["ALT-..."], "reasoning": "..."}
  ],
  "remediation": [
     {"phase": "immediate", "action": "...", "cli_command": "kubectl ..."},
     {"phase": "short-term", "action": "...", "cli_command": null},
     {"phase": "long-term", "action": "...", "cli_command": null}
  ]
}

Provide 3 ranked root cause hypotheses. Provide at least 3 remediation steps spanning all three phases.
Identify alerts you believe are likely false-positives/noise by their IDs."""


def _extract_json(text: str) -> dict:
    # strip code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rsplit("```", 1)[0].strip()
    # find first { ... }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


@api_router.post("/triage", response_model=TriageResult)
async def run_triage(req: TriageRequest):
    if not req.alert_ids:
        raise HTTPException(400, "alert_ids required")
    alerts = await db.alerts.find({"id": {"$in": req.alert_ids}}, {"_id": 0}).to_list(200)
    if not alerts:
        raise HTTPException(404, "No alerts found")

    user_payload = {
        "alerts": [
            {
                "id": a["id"], "source": a["source"], "severity": a["severity"],
                "service": a["service"], "region": a["region"],
                "title": a["title"], "description": a.get("description", ""),
                "timestamp": a["timestamp"],
            } for a in alerts
        ]
    }

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"triage-{uuid.uuid4().hex[:8]}",
            system_message=TRIAGE_SYSTEM,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        msg = UserMessage(text=f"Analyze these alerts and produce the triage JSON:\n{json.dumps(user_payload, indent=2)}")
        raw = await chat.send_message(msg)
        parsed = _extract_json(raw)
    except Exception as e:
        logger.exception("Triage LLM failed: %s", e)
        # graceful fallback
        parsed = {
            "priority": "P2",
            "blast_radius": "Unknown",
            "mttr_estimate_minutes": 30,
            "affected_services": list({a["service"] for a in alerts}),
            "summary": f"Automated fallback triage for {len(alerts)} alerts. LLM unavailable.",
            "noise_alert_ids": [],
            "root_causes": [{
                "rank": 1, "hypothesis": "LLM analysis unavailable - manual review required",
                "confidence": "low", "supporting_alert_ids": [a["id"] for a in alerts],
                "reasoning": str(e)[:200]
            }],
            "remediation": [
                {"phase": "immediate", "action": "Manually review alert details", "cli_command": None},
                {"phase": "short-term", "action": "Verify LLM API connectivity", "cli_command": None},
                {"phase": "long-term", "action": "Improve fallback runbooks", "cli_command": None},
            ],
        }

    # Build incident
    inc_title = parsed.get("summary", "Untitled incident")[:120]
    incident = Incident(
        title=inc_title,
        priority=parsed.get("priority", "P3"),
        blast_radius=parsed.get("blast_radius", ""),
        status="triaging",
        affected_services=parsed.get("affected_services", []),
        alert_ids=req.alert_ids,
    )
    triage = TriageResult(
        incident_id=incident.id,
        alert_ids=req.alert_ids,
        priority=parsed.get("priority", "P3"),
        blast_radius=parsed.get("blast_radius", ""),
        mttr_estimate_minutes=int(parsed.get("mttr_estimate_minutes", 30)),
        affected_services=parsed.get("affected_services", []),
        summary=parsed.get("summary", ""),
        noise_alert_ids=parsed.get("noise_alert_ids", []),
        root_causes=[RootCause(**r) for r in parsed.get("root_causes", [])],
        remediation=[RemediationStep(**s) for s in parsed.get("remediation", [])],
    )
    incident.triage_id = triage.id

    await db.triage_results.insert_one(triage.model_dump())
    await db.incidents.insert_one(incident.model_dump())

    # mark noise alerts
    if triage.noise_alert_ids:
        await db.alerts.update_many(
            {"id": {"$in": triage.noise_alert_ids}}, {"$set": {"status": "noise"}}
        )
    return triage


# ---------- ANALYTICS ----------
@api_router.get("/analytics/summary")
async def analytics_summary():
    alerts = await db.alerts.find({}, {"_id": 0}).to_list(5000)
    incidents = await db.incidents.find({}, {"_id": 0}).to_list(1000)

    by_source: dict = {}
    by_severity: dict = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in alerts:
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1
        if a["severity"] in by_severity:
            by_severity[a["severity"]] += 1

    # MTTR trend (last 7 buckets)
    now = datetime.now(timezone.utc)
    buckets = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date().isoformat()
        buckets.append({"day": day, "mttr": 0, "count": 0})
    for inc in incidents:
        if inc.get("status") == "resolved" and inc.get("resolved_at"):
            try:
                created = datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00"))
                resolved = datetime.fromisoformat(inc["resolved_at"].replace("Z", "+00:00"))
                mttr = (resolved - created).total_seconds() / 60.0
                day = created.date().isoformat()
                for b in buckets:
                    if b["day"] == day:
                        b["mttr"] += mttr
                        b["count"] += 1
            except Exception:
                pass
    for b in buckets:
        b["mttr"] = round(b["mttr"] / b["count"], 1) if b["count"] else 0

    top_incidents = sorted(incidents, key=lambda x: x.get("created_at", ""), reverse=True)[:5]

    return {
        "totals": {
            "alerts": len(alerts),
            "active_alerts": sum(1 for a in alerts if a["status"] == "active"),
            "incidents": len(incidents),
            "open_incidents": sum(1 for i in incidents if i["status"] != "resolved"),
        },
        "by_source": [{"source": k, "count": v} for k, v in by_source.items()],
        "by_severity": [{"severity": k, "count": v} for k, v in by_severity.items()],
        "mttr_trend": buckets,
        "top_incidents": top_incidents,
    }


# ---------- SEED ----------
SAMPLE_ALERTS = [
    ("cloudwatch", "critical", "payments-api", "us-east-1", "5xx error rate > 25% on /charge"),
    ("datadog", "critical", "payments-api", "us-east-1", "p99 latency 8.4s on /charge"),
    ("prometheus", "high", "payments-db", "us-east-1", "RDS CPU 96% sustained 5m"),
    ("grafana", "high", "payments-db", "us-east-1", "DB connection pool exhausted"),
    ("pagerduty", "medium", "auth-service", "us-east-1", "Token refresh latency p95 1.2s"),
    ("datadog", "low", "marketing-site", "us-west-2", "404 spike on /promo-2024"),
    ("cloudwatch", "high", "checkout-svc", "eu-west-1", "Memory utilization 92% on pod-7"),
    ("prometheus", "medium", "checkout-svc", "eu-west-1", "Pod restart count = 4 in 10m"),
    ("grafana", "critical", "edge-cdn", "global", "Cache hit ratio dropped to 41%"),
    ("datadog", "low", "logs-pipeline", "us-east-1", "Kafka lag 12k messages on topic billing-events"),
]


@api_router.post("/seed")
async def seed_data():
    await db.alerts.delete_many({})
    await db.incidents.delete_many({})
    await db.triage_results.delete_many({})

    now = datetime.now(timezone.utc)
    docs = []
    for i, (source, sev, svc, region, title) in enumerate(SAMPLE_ALERTS):
        a = Alert(
            source=source, severity=sev, service=svc, region=region, title=title,
            description=f"Auto-generated sample alert from {source}.",
            timestamp=(now - timedelta(minutes=random.randint(1, 90))).isoformat(),
        )
        docs.append(a.model_dump())
    await db.alerts.insert_many(docs)
    return {"seeded": len(docs)}


@api_router.post("/alerts/simulate")
async def simulate_alert():
    """Generate one random alert (for the live demo button)."""
    src, sev, svc, region, title = random.choice(SAMPLE_ALERTS)
    a = Alert(
        source=src, severity=sev, service=svc, region=region,
        title=title + f" (sim {datetime.now(timezone.utc).strftime('%H:%M:%S')})",
        description="Simulated alert."
    )
    await db.alerts.insert_one(a.model_dump())
    return a


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
