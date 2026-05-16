from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import logging
import random
import re
import uuid
import asyncio
import bcrypt
import jwt
import httpx
import resend
import base64
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, EmailStr
from cryptography.fernet import Fernet, InvalidToken

from emergentintegrations.llm.chat import LlmChat, UserMessage
from llm_provider import get_chat as llm_chat, llm_is_configured

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret')
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 24

app = FastAPI(title="TriageAI API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("triageai")


# -------------------- MODELS --------------------
Severity = Literal["critical", "high", "medium", "low"]
AlertStatus = Literal["active", "resolved", "noise"]
IncidentStatus = Literal["open", "triaging", "in_progress", "resolved"]
UserRole = Literal["admin", "on-call", "viewer"]


class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    role: UserRole


class LoginReq(BaseModel):
    email: str
    password: str


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: f"ALT-{uuid.uuid4().hex[:8].upper()}")
    source: str
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


class IncidentUpdate(BaseModel):
    user_email: str
    user_name: str
    text: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: f"INC-{uuid.uuid4().hex[:8].upper()}")
    title: str
    priority: Literal["P1", "P2", "P3", "P4"]
    blast_radius: str = ""
    status: IncidentStatus = "open"
    affected_services: List[str] = []
    alert_ids: List[str] = []
    triage_id: Optional[str] = None
    created_by: Optional[str] = None  # email
    assignee: Optional[str] = None    # email
    collaborators: List[str] = []     # emails
    updates: List[IncidentUpdate] = []
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None


class Source(BaseModel):
    id: str = Field(default_factory=lambda: f"SRC-{uuid.uuid4().hex[:8].upper()}")
    name: str
    type: str          # cloudwatch | datadog | grafana | prometheus | pagerduty | custom
    webhook_url: Optional[str] = None
    api_key: Optional[str] = None
    ingest_token: str = Field(default_factory=lambda: uuid.uuid4().hex)
    enabled: bool = True
    last_ingested_at: Optional[str] = None
    ingest_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SourceIn(BaseModel):
    name: str
    type: str
    webhook_url: Optional[str] = ""
    api_key: Optional[str] = ""
    enabled: bool = True


class ChatMsg(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    user_email: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChatPrompt(BaseModel):
    text: str


class CollabIn(BaseModel):
    email: str


class UpdateIn(BaseModel):
    text: str


# Notification channels
ChannelType = Literal["slack", "teams", "discord", "webhook", "email"]
TriggerEvent = Literal["incident_created", "incident_resolved", "sla_breach"]


class NotificationChannel(BaseModel):
    id: str = Field(default_factory=lambda: f"NCH-{uuid.uuid4().hex[:8].upper()}")
    name: str
    type: ChannelType
    config: Dict[str, Any] = Field(default_factory=dict)
    # config keys per type:
    #   slack/teams/discord/webhook: {"webhook_url": "..."}
    #   email: {"api_key": "re_...", "from_email": "...", "to_email": "..."}
    triggers: List[TriggerEvent] = Field(default_factory=lambda: ["incident_created", "sla_breach"])
    enabled: bool = True
    created_by: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used_at: Optional[str] = None
    last_status: Optional[str] = None  # "ok" | "error: ..."


class NotificationChannelIn(BaseModel):
    name: str
    type: ChannelType
    config: Dict[str, Any] = Field(default_factory=dict)
    triggers: List[TriggerEvent] = Field(default_factory=lambda: ["incident_created", "sla_breach", "incident_resolved"])
    enabled: bool = True


# -------------------- AUTH --------------------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def create_token(user: dict) -> str:
    payload = {
        "sub": user["email"],
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    token = auth[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"email": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return current_user


SEED_USERS = [
    {"email": "admin@triage.ai",  "name": "Admin User",   "password": "admin123",  "role": "admin"},
    {"email": "sre1@triage.ai",   "name": "Alex Chen",    "password": "sre123",    "role": "on-call"},
    {"email": "sre2@triage.ai",   "name": "Maya Patel",   "password": "sre123",    "role": "on-call"},
    {"email": "viewer@triage.ai", "name": "View Only",    "password": "viewer123", "role": "viewer"},
]


@app.on_event("startup")
async def on_startup():
    # Seed users
    for u in SEED_USERS:
        existing = await db.users.find_one({"email": u["email"]})
        if not existing:
            await db.users.insert_one({
                "id": str(uuid.uuid4()),
                "email": u["email"],
                "name": u["name"],
                "password_hash": hash_password(u["password"]),
                "role": u["role"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    # Default sources
    if await db.sources.count_documents({}) == 0:
        defaults = [
            ("AWS CloudWatch", "cloudwatch"),
            ("Datadog Production", "datadog"),
            ("PagerDuty V2", "pagerduty"),
            ("Grafana 9", "grafana"),
        ]
        for name, t in defaults:
            await db.sources.insert_one(Source(name=name, type=t).model_dump())
    # Backfill ingest_token for any pre-existing sources missing it
    async for s in db.sources.find({"$or": [{"ingest_token": {"$exists": False}}, {"ingest_token": None}, {"ingest_token": ""}]}, {"_id": 0, "id": 1}):
        await db.sources.update_one({"id": s["id"]}, {"$set": {"ingest_token": uuid.uuid4().hex}})
    logger.info("Startup seeding complete")


# -------------------- AUTH ROUTES --------------------
@api_router.post("/auth/login")
async def login(body: LoginReq):
    user = await db.users.find_one({"email": body.email.lower().strip()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user)
    safe = {k: v for k, v in user.items() if k not in ("_id", "password_hash")}
    return {"access_token": token, "token_type": "bearer", "user": safe}


@api_router.get("/auth/me")
async def me(current_user: dict = Depends(get_current_user)):
    return current_user


@api_router.get("/auth/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    docs = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(100)
    return docs


# -------------------- MAIN ROUTES --------------------
@api_router.get("/")
async def root():
    return {"service": "TriageAI", "status": "operational"}


@api_router.post("/alerts/ingest", response_model=Alert)
async def ingest_alert(payload: AlertIngest, current_user: dict = Depends(get_current_user)):
    alert = Alert(**payload.model_dump())
    await db.alerts.insert_one(alert.model_dump())
    return alert


@api_router.get("/alerts", response_model=List[Alert])
async def list_alerts(status: Optional[AlertStatus] = None, limit: int = 200,
                      current_user: dict = Depends(get_current_user)):
    q = {}
    if status:
        q["status"] = status
    docs = await db.alerts.find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs


@api_router.get("/alerts/unattended")
async def unattended_alerts(current_user: dict = Depends(get_current_user)):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    docs = await db.alerts.find(
        {"status": "active", "timestamp": {"$lt": cutoff}}, {"_id": 0}
    ).sort("timestamp", 1).to_list(200)

    # Fire SLA breach notification, but only once per alert (track notified IDs)
    if docs:
        new_ids = []
        for a in docs:
            existing = await db.notification_log.find_one({"event": "sla_breach", "alert_id": a["id"]})
            if not existing:
                new_ids.append(a["id"])
        if new_ids:
            subj = f"[TriageAI] SLA BREACH · {len(new_ids)} alert(s) unattended > 5 days"
            body = "\n".join([f"- {a['id']} · {a['severity']} · {a['title']} · {a['service']} ({a['region']})"
                              for a in docs if a["id"] in new_ids])
            # mark notified
            now_iso = datetime.now(timezone.utc).isoformat()
            for aid in new_ids:
                await db.notification_log.insert_one({
                    "id": str(uuid.uuid4()), "alert_id": aid, "event": "sla_breach",
                    "channel_id": None, "channel_name": "(marker)", "channel_type": "marker",
                    "subject": subj, "status": "pending", "timestamp": now_iso,
                })
            asyncio.create_task(dispatch_event("sla_breach", subj, body))

    return {"count": len(docs), "alerts": docs, "threshold_days": 5}


@api_router.patch("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, current_user: dict = Depends(get_current_user)):
    res = await db.alerts.update_one({"id": alert_id}, {"$set": {"status": "resolved"}})
    if res.matched_count == 0:
        raise HTTPException(404, "Alert not found")
    return {"id": alert_id, "status": "resolved"}


@api_router.post("/alerts/resolve-bulk")
async def resolve_alerts(body: TriageRequest, current_user: dict = Depends(get_current_user)):
    await db.alerts.update_many({"id": {"$in": body.alert_ids}}, {"$set": {"status": "resolved"}})
    return {"resolved": len(body.alert_ids)}


# ---------- INCIDENTS ----------
@api_router.get("/incidents", response_model=List[Incident])
async def list_incidents(scope: Optional[str] = None, limit: int = 200,
                         current_user: dict = Depends(get_current_user)):
    q = {}
    email = current_user["email"]
    if scope == "mine":
        q = {"$or": [{"assignee": email}, {"collaborators": email}, {"created_by": email}]}
    elif scope == "others":
        q = {"$nor": [{"assignee": email}, {"collaborators": email}, {"created_by": email}]}
    docs = await db.incidents.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return docs


@api_router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, current_user: dict = Depends(get_current_user)):
    inc = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not inc:
        raise HTTPException(404, "Not found")
    triage = None
    if inc.get("triage_id"):
        triage = await db.triage_results.find_one({"id": inc["triage_id"]}, {"_id": 0})
    alerts = await db.alerts.find({"id": {"$in": inc.get("alert_ids", [])}}, {"_id": 0}).to_list(100)
    return {"incident": inc, "triage": triage, "alerts": alerts}


@api_router.post("/incidents/{incident_id}/pickup")
async def pickup_incident(incident_id: str, current_user: dict = Depends(get_current_user)):
    inc = await db.incidents.find_one({"id": incident_id})
    if not inc:
        raise HTTPException(404, "Not found")
    update = IncidentUpdate(
        user_email=current_user["email"], user_name=current_user["name"],
        text=f"{current_user['name']} picked up this incident."
    )
    await db.incidents.update_one(
        {"id": incident_id},
        {"$set": {"assignee": current_user["email"], "status": "in_progress"},
         "$push": {"updates": update.model_dump()}}
    )
    return {"id": incident_id, "assignee": current_user["email"]}


@api_router.post("/incidents/{incident_id}/collaborators")
async def add_collaborator(incident_id: str, body: CollabIn,
                           current_user: dict = Depends(get_current_user)):
    user = await db.users.find_one({"email": body.email.lower().strip()})
    if not user:
        raise HTTPException(404, "User not found")
    update = IncidentUpdate(
        user_email=current_user["email"], user_name=current_user["name"],
        text=f"Added {user['name']} ({user['email']}) as collaborator."
    )
    await db.incidents.update_one(
        {"id": incident_id},
        {"$addToSet": {"collaborators": user["email"]},
         "$push": {"updates": update.model_dump()}}
    )
    return {"id": incident_id, "collaborator": user["email"]}


@api_router.post("/incidents/{incident_id}/updates")
async def post_update(incident_id: str, body: UpdateIn,
                      current_user: dict = Depends(get_current_user)):
    update = IncidentUpdate(
        user_email=current_user["email"], user_name=current_user["name"], text=body.text.strip()
    )
    res = await db.incidents.update_one(
        {"id": incident_id}, {"$push": {"updates": update.model_dump()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return update


@api_router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, current_user: dict = Depends(get_current_user)):
    inc = await db.incidents.find_one({"id": incident_id})
    if not inc:
        raise HTTPException(404, "Not found")
    now = datetime.now(timezone.utc).isoformat()
    update = IncidentUpdate(
        user_email=current_user["email"], user_name=current_user["name"],
        text=f"Incident marked as RESOLVED by {current_user['name']}."
    )
    await db.incidents.update_one(
        {"id": incident_id},
        {"$set": {"status": "resolved", "resolved_at": now},
         "$push": {"updates": update.model_dump()}}
    )
    # also resolve linked alerts
    if inc.get("alert_ids"):
        await db.alerts.update_many(
            {"id": {"$in": inc["alert_ids"]}}, {"$set": {"status": "resolved"}}
        )

    # Notify resolution
    subj = f"[TriageAI] RESOLVED · {inc['title'][:80]}"
    body = (
        f"Incident {inc['id']} resolved by {current_user['name']} ({current_user['email']}).\n"
        f"Priority: {inc.get('priority')}\n"
        f"Services: {', '.join(inc.get('affected_services', []))}\n"
    )
    asyncio.create_task(dispatch_event("incident_resolved", subj, body))

    return {"id": incident_id, "status": "resolved"}


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
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rsplit("```", 1)[0].strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


@api_router.post("/triage")
async def run_triage(req: TriageRequest, current_user: dict = Depends(get_current_user)):
    if not req.alert_ids:
        raise HTTPException(400, "alert_ids required")
    alerts = await db.alerts.find({"id": {"$in": req.alert_ids}}, {"_id": 0}).to_list(200)
    if not alerts:
        raise HTTPException(404, "No alerts found")

    # F-01: correlate deployments BEFORE LLM call so we can enrich the prompt
    try:
        correlated_deployments = await DeploymentCorrelator.find_for_alerts(
            alerts, window_minutes=30, confidence_min=0.3
        )
    except Exception as e:
        logger.exception("Deployment correlation failed: %s", e)
        correlated_deployments = []
    deployment_prompt_block = _build_deployment_prompt_block(correlated_deployments)

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
    user_text = f"Analyze these alerts and produce the triage JSON:\n{json.dumps(user_payload, indent=2)}"
    if deployment_prompt_block:
        user_text += "\n" + deployment_prompt_block
    try:
        chat = llm_chat(
            session_id=f"triage-{uuid.uuid4().hex[:8]}",
            system_message=TRIAGE_SYSTEM,
            model_hint="anthropic:claude-sonnet-4-5-20250929",
        )
        msg = UserMessage(text=user_text)
        raw = await chat.send_message(msg)
        parsed = _extract_json(raw)
    except Exception as e:
        logger.exception("Triage LLM failed: %s", e)
        parsed = {
            "priority": "P2", "blast_radius": "Unknown", "mttr_estimate_minutes": 30,
            "affected_services": list({a["service"] for a in alerts}),
            "summary": f"Automated fallback triage for {len(alerts)} alerts. LLM unavailable.",
            "noise_alert_ids": [],
            "root_causes": [{"rank": 1, "hypothesis": "LLM analysis unavailable - manual review required",
                             "confidence": "low", "supporting_alert_ids": [a["id"] for a in alerts],
                             "reasoning": str(e)[:200]}],
            "remediation": [
                {"phase": "immediate", "action": "Manually review alert details", "cli_command": None},
                {"phase": "short-term", "action": "Verify LLM API connectivity", "cli_command": None},
                {"phase": "long-term", "action": "Improve fallback runbooks", "cli_command": None},
            ],
        }

    inc_title = parsed.get("summary", "Untitled incident")[:120]
    incident = Incident(
        title=inc_title, priority=parsed.get("priority", "P3"),
        blast_radius=parsed.get("blast_radius", ""), status="triaging",
        affected_services=parsed.get("affected_services", []), alert_ids=req.alert_ids,
        created_by=current_user["email"],
    )
    triage = TriageResult(
        incident_id=incident.id, alert_ids=req.alert_ids,
        priority=parsed.get("priority", "P3"), blast_radius=parsed.get("blast_radius", ""),
        mttr_estimate_minutes=int(parsed.get("mttr_estimate_minutes", 30)),
        affected_services=parsed.get("affected_services", []),
        summary=parsed.get("summary", ""), noise_alert_ids=parsed.get("noise_alert_ids", []),
        root_causes=[RootCause(**r) for r in parsed.get("root_causes", [])],
        remediation=[RemediationStep(**s) for s in parsed.get("remediation", [])],
    )
    incident.triage_id = triage.id

    await db.triage_results.insert_one(triage.model_dump())
    await db.incidents.insert_one(incident.model_dump())

    if triage.noise_alert_ids:
        await db.alerts.update_many(
            {"id": {"$in": triage.noise_alert_ids}}, {"$set": {"status": "noise"}}
        )

    # Fire notification for P1/P2 incidents
    if incident.priority in ("P1", "P2"):
        subj = f"[TriageAI] {incident.priority} · {incident.title[:80]}"
        body = (
            f"Priority: {incident.priority}\n"
            f"Blast radius: {incident.blast_radius}\n"
            f"Services: {', '.join(incident.affected_services)}\n"
            f"ETA: {triage.mttr_estimate_minutes}m\n"
            f"Top hypothesis: {triage.root_causes[0].hypothesis if triage.root_causes else 'n/a'}\n"
            f"Incident ID: {incident.id}\n"
        )
        asyncio.create_task(dispatch_event("incident_created", subj, body))

    # F-01: attach correlated deployments to triage response
    response = triage.model_dump()
    response["deployments"] = correlated_deployments
    return response


# ---------- INCIDENT CHAT ----------
CHAT_SYSTEM = """You are TriageAI Assistant, an expert SRE copilot embedded in a specific incident.
You help on-call engineers diagnose, debug, and resolve the incident. You have full context of the
incident's alerts, root cause hypotheses, and remediation playbook.

Be concise, technical, and practical. Provide CLI commands when relevant. Reference specific alert IDs
when it helps. If asked something outside the incident's scope, redirect politely back to the incident."""


def _build_incident_context(inc: dict, triage: Optional[dict], alerts: List[dict]) -> str:
    ctx = {
        "incident": {
            "id": inc["id"], "title": inc["title"], "priority": inc["priority"],
            "status": inc["status"], "blast_radius": inc.get("blast_radius", ""),
            "affected_services": inc.get("affected_services", []),
            "assignee": inc.get("assignee"),
        },
        "alerts": [{"id": a["id"], "severity": a["severity"], "service": a["service"],
                    "region": a["region"], "title": a["title"], "source": a["source"]} for a in alerts],
    }
    if triage:
        ctx["triage"] = {
            "summary": triage.get("summary", ""),
            "root_causes": triage.get("root_causes", []),
            "remediation": triage.get("remediation", []),
        }
    return json.dumps(ctx, indent=2)


@api_router.get("/incidents/{incident_id}/chat")
async def get_chat(incident_id: str, current_user: dict = Depends(get_current_user)):
    chat = await db.incident_chats.find_one({"incident_id": incident_id}, {"_id": 0})
    return chat or {"incident_id": incident_id, "messages": []}


@api_router.post("/incidents/{incident_id}/chat")
async def chat_message(incident_id: str, body: ChatPrompt,
                       current_user: dict = Depends(get_current_user)):
    inc = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
    if not inc:
        raise HTTPException(404, "Not found")
    if inc["status"] == "resolved":
        raise HTTPException(400, "Incident is resolved; chat is read-only")

    triage = None
    if inc.get("triage_id"):
        triage = await db.triage_results.find_one({"id": inc["triage_id"]}, {"_id": 0})
    alerts = await db.alerts.find({"id": {"$in": inc.get("alert_ids", [])}}, {"_id": 0}).to_list(100)
    context = _build_incident_context(inc, triage, alerts)

    chat_doc = await db.incident_chats.find_one({"incident_id": incident_id}, {"_id": 0})
    messages = chat_doc["messages"] if chat_doc else []

    user_msg = ChatMsg(role="user", text=body.text, user_email=current_user["email"])
    messages.append(user_msg.model_dump())

    # Build conversational history into a single system message + latest user message
    sys_msg = f"{CHAT_SYSTEM}\n\nINCIDENT CONTEXT:\n{context}"
    history_text = ""
    for m in messages[-12:-1]:  # last 11 prior messages, excluding the new one
        prefix = "User" if m["role"] == "user" else "Assistant"
        history_text += f"\n{prefix}: {m['text']}"

    try:
        chat = llm_chat(
            session_id=f"chat-{incident_id}",
            system_message=sys_msg,
            model_hint="anthropic:claude-sonnet-4-5-20250929",
        )
        prompt = (history_text + "\n\nUser: " + body.text) if history_text else body.text
        reply = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("Chat LLM failed: %s", e)
        reply = f"_(AI assistant unavailable: {str(e)[:120]})_"

    asst_msg = ChatMsg(role="assistant", text=reply)
    messages.append(asst_msg.model_dump())

    await db.incident_chats.update_one(
        {"incident_id": incident_id},
        {"$set": {"incident_id": incident_id, "messages": messages,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"user_message": user_msg.model_dump(), "assistant_message": asst_msg.model_dump()}


# ---------- SOURCES (monitoring tools) ----------
@api_router.get("/sources", response_model=List[Source])
async def list_sources(current_user: dict = Depends(get_current_user)):
    docs = await db.sources.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return docs


@api_router.post("/sources", response_model=Source)
async def add_source(body: SourceIn, current_user: dict = Depends(get_current_user)):
    src = Source(**body.model_dump())
    await db.sources.insert_one(src.model_dump())
    return src


@api_router.delete("/sources/{source_id}")
async def delete_source(source_id: str, current_user: dict = Depends(get_current_user)):
    await db.sources.delete_one({"id": source_id})
    return {"deleted": source_id}


@api_router.patch("/sources/{source_id}")
async def toggle_source(source_id: str, current_user: dict = Depends(get_current_user)):
    src = await db.sources.find_one({"id": source_id}, {"_id": 0})
    if not src:
        raise HTTPException(404, "Not found")
    new_state = not src.get("enabled", True)
    await db.sources.update_one({"id": source_id}, {"$set": {"enabled": new_state}})
    return {"id": source_id, "enabled": new_state}


# ---------- WEBHOOK INGESTION ADAPTERS ----------
def _norm_severity(val: str) -> Severity:
    if not val:
        return "medium"
    v = val.lower().strip()
    if v in ("critical", "crit", "p1", "fatal", "sev1", "alarm"): return "critical"
    if v in ("high", "error", "p2", "sev2", "warning"): return "high"
    if v in ("medium", "med", "warn", "p3", "sev3", "info"): return "medium"
    if v in ("low", "p4", "sev4", "ok", "resolved"): return "low"
    return "medium"


def _adapt_payload(stype: str, payload: dict) -> List[dict]:
    """Return a list of normalized alert dicts ({source, severity, service, region, title, description})."""
    out: List[dict] = []
    try:
        if stype == "cloudwatch":
            # SNS message wrapper or direct alarm
            msg = payload
            if "Records" in payload and payload["Records"]:
                inner = payload["Records"][0].get("Sns", {}).get("Message", "{}")
                if isinstance(inner, str):
                    try: msg = json.loads(inner)
                    except Exception: msg = {}
            sev_map = {"ALARM": "critical", "OK": "low", "INSUFFICIENT_DATA": "medium"}
            out.append({
                "source": "cloudwatch",
                "severity": sev_map.get(msg.get("NewStateValue", ""), "high"),
                "service": msg.get("Trigger", {}).get("Namespace", msg.get("AlarmName", "unknown")),
                "region": msg.get("Region", "us-east-1"),
                "title": msg.get("AlarmName", "CloudWatch alarm"),
                "description": msg.get("AlarmDescription", "") or msg.get("NewStateReason", ""),
            })
        elif stype == "datadog":
            sev = _norm_severity(payload.get("alert_type") or payload.get("priority"))
            out.append({
                "source": "datadog",
                "severity": sev,
                "service": payload.get("source_type_name") or payload.get("aggreg_key", "unknown"),
                "region": payload.get("org", {}).get("region") if isinstance(payload.get("org"), dict) else payload.get("region", "us-east-1"),
                "title": payload.get("title") or payload.get("event_title", "Datadog alert"),
                "description": payload.get("body") or payload.get("text", ""),
            })
        elif stype == "pagerduty":
            ev = payload.get("event") or payload
            data = ev.get("data") or ev
            out.append({
                "source": "pagerduty",
                "severity": _norm_severity(data.get("urgency") or data.get("severity")),
                "service": (data.get("service") or {}).get("summary") if isinstance(data.get("service"), dict) else (data.get("service") or "unknown"),
                "region": data.get("region", "us-east-1"),
                "title": data.get("summary") or data.get("title", "PagerDuty incident"),
                "description": data.get("description", ""),
            })
        elif stype in ("grafana", "prometheus"):
            # Both use Alertmanager-style payload
            for a in payload.get("alerts", [payload]):
                labels = a.get("labels", {}) or {}
                anns = a.get("annotations", {}) or {}
                out.append({
                    "source": stype,
                    "severity": _norm_severity(labels.get("severity") or a.get("severity")),
                    "service": labels.get("service") or labels.get("job") or labels.get("alertname", "unknown"),
                    "region": labels.get("region") or labels.get("instance", "global"),
                    "title": anns.get("summary") or labels.get("alertname") or "Alert",
                    "description": anns.get("description", ""),
                })
        else:  # custom / passthrough
            out.append({
                "source": stype or "custom",
                "severity": _norm_severity(payload.get("severity")),
                "service": payload.get("service", "unknown"),
                "region": payload.get("region", "global"),
                "title": payload.get("title", "Custom alert"),
                "description": payload.get("description", ""),
            })
    except Exception as e:
        logger.exception("Adapter failed: %s", e)
    return out


SAMPLE_PAYLOADS = {
    "cloudwatch": {
        "AlarmName": "payments-api-5xx",
        "AlarmDescription": "5xx error rate exceeded threshold",
        "NewStateValue": "ALARM",
        "NewStateReason": "Threshold crossed: 1 datapoint > 5%",
        "Region": "us-east-1",
        "Trigger": {"Namespace": "payments-api"},
    },
    "datadog": {
        "title": "[Triggered] High CPU on payments-db",
        "body": "host:payments-db-01 cpu=96%",
        "alert_type": "error",
        "source_type_name": "payments-db",
        "region": "us-east-1",
    },
    "pagerduty": {
        "event": {"event_type": "incident.trigger", "data": {
            "summary": "Auth service degraded",
            "urgency": "high",
            "service": {"summary": "auth-service"},
            "description": "p95 latency > 1s",
        }},
    },
    "grafana": {
        "alerts": [{
            "status": "firing",
            "labels": {"severity": "critical", "service": "edge-cdn", "region": "global", "alertname": "CacheHitRatioLow"},
            "annotations": {"summary": "Cache hit ratio dropped to 41%", "description": "Below 80% threshold for 5m"},
        }],
    },
    "prometheus": {
        "alerts": [{
            "status": "firing",
            "labels": {"severity": "high", "service": "checkout-svc", "region": "eu-west-1", "alertname": "PodMemoryHigh"},
            "annotations": {"summary": "Memory utilization 92% on pod-7", "description": "Sustained for 10m"},
        }],
    },
    "custom": {
        "severity": "high",
        "service": "my-service",
        "region": "us-east-1",
        "title": "Custom alert from external system",
        "description": "Some context here",
    },
}


@api_router.post("/sources/{source_id}/ingest")
async def webhook_ingest(source_id: str, payload: dict, request: Request):
    """Public endpoint — external monitoring tools push alerts here.
    Auth: ?token=<ingest_token> query param OR X-Ingest-Token header."""
    src = await db.sources.find_one({"id": source_id}, {"_id": 0})
    if not src:
        raise HTTPException(404, "Source not found")
    if not src.get("enabled", True):
        raise HTTPException(403, "Source disabled")

    provided = request.query_params.get("token") or request.headers.get("X-Ingest-Token", "")
    if not provided or provided != src.get("ingest_token"):
        raise HTTPException(401, "Invalid or missing ingest token")

    normalized = _adapt_payload(src["type"], payload)
    if not normalized:
        raise HTTPException(400, "Could not parse payload")

    created = []
    for n in normalized:
        a = Alert(**n)
        await db.alerts.insert_one(a.model_dump())
        created.append(a.model_dump())

    await db.sources.update_one(
        {"id": source_id},
        {"$set": {"last_ingested_at": datetime.now(timezone.utc).isoformat()},
         "$inc": {"ingest_count": len(created)}}
    )
    return {"ingested": len(created), "alerts": created}


@api_router.post("/sources/{source_id}/test")
async def test_source(source_id: str, current_user: dict = Depends(get_current_user)):
    """Auth-protected: fires a sample payload at the source's own ingest endpoint to verify wiring."""
    src = await db.sources.find_one({"id": source_id}, {"_id": 0})
    if not src:
        raise HTTPException(404, "Not found")
    sample = SAMPLE_PAYLOADS.get(src["type"], SAMPLE_PAYLOADS["custom"])
    normalized = _adapt_payload(src["type"], sample)
    created = []
    for n in normalized:
        a = Alert(**n)
        await db.alerts.insert_one(a.model_dump())
        created.append(a.model_dump())
    await db.sources.update_one(
        {"id": source_id},
        {"$set": {"last_ingested_at": datetime.now(timezone.utc).isoformat()},
         "$inc": {"ingest_count": len(created)}}
    )
    return {"ingested": len(created), "sample_payload": sample, "alerts": created}


# ---------- NOTIFICATIONS ----------
async def _send_via_channel(channel: dict, subject: str, text: str, html: Optional[str] = None) -> str:
    """Send a single notification via the given channel. Returns 'ok' or 'error: ...'"""
    t = channel["type"]
    cfg = channel.get("config", {}) or {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            if t == "slack":
                url = cfg.get("webhook_url")
                if not url: return "error: webhook_url missing"
                body = {"text": f"*{subject}*\n{text}"}
                r = await http.post(url, json=body)
                return "ok" if r.status_code < 300 else f"error: HTTP {r.status_code}"
            if t == "teams":
                url = cfg.get("webhook_url")
                if not url: return "error: webhook_url missing"
                body = {"@type": "MessageCard", "@context": "https://schema.org/extensions",
                        "summary": subject, "title": subject, "text": text}
                r = await http.post(url, json=body)
                return "ok" if r.status_code < 300 else f"error: HTTP {r.status_code}"
            if t == "discord":
                url = cfg.get("webhook_url")
                if not url: return "error: webhook_url missing"
                body = {"content": f"**{subject}**\n{text}"}
                r = await http.post(url, json=body)
                return "ok" if r.status_code < 300 else f"error: HTTP {r.status_code}"
            if t == "webhook":
                url = cfg.get("webhook_url")
                if not url: return "error: webhook_url missing"
                body = {"subject": subject, "text": text, "html": html, "service": "TriageAI"}
                r = await http.post(url, json=body)
                return "ok" if r.status_code < 300 else f"error: HTTP {r.status_code}"
        if t == "email":
            api_key = cfg.get("api_key")
            from_email = cfg.get("from_email") or "onboarding@resend.dev"
            to_email = cfg.get("to_email")
            if not api_key: return "error: api_key missing"
            if not to_email: return "error: to_email missing"
            resend.api_key = api_key
            params = {"from": from_email, "to": [to_email], "subject": subject,
                      "html": html or f"<pre style='font-family:monospace'>{text}</pre>"}
            res = await asyncio.to_thread(resend.Emails.send, params)
            return "ok" if res and res.get("id") else f"error: {res}"
    except Exception as e:
        return f"error: {str(e)[:120]}"
    return "error: unknown type"


async def dispatch_event(event: TriggerEvent, subject: str, text: str, html: Optional[str] = None):
    """Find all enabled channels listening for this event and fire them in parallel."""
    channels = await db.notification_channels.find(
        {"enabled": True, "triggers": event}, {"_id": 0}
    ).to_list(100)
    if not channels:
        return
    async def _do(ch):
        status = await _send_via_channel(ch, subject, text, html)
        await db.notification_channels.update_one(
            {"id": ch["id"]},
            {"$set": {"last_used_at": datetime.now(timezone.utc).isoformat(), "last_status": status}}
        )
        # log
        await db.notification_log.insert_one({
            "id": str(uuid.uuid4()),
            "channel_id": ch["id"], "channel_name": ch["name"], "channel_type": ch["type"],
            "event": event, "subject": subject, "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    await asyncio.gather(*[_do(c) for c in channels], return_exceptions=True)


@api_router.get("/notifications/channels", response_model=List[NotificationChannel])
async def list_channels(current_user: dict = Depends(get_current_user)):
    docs = await db.notification_channels.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return docs


@api_router.post("/notifications/channels", response_model=NotificationChannel)
async def add_channel(body: NotificationChannelIn, current_user: dict = Depends(require_admin)):
    ch = NotificationChannel(**body.model_dump(), created_by=current_user["email"])
    await db.notification_channels.insert_one(ch.model_dump())
    return ch


@api_router.patch("/notifications/channels/{channel_id}")
async def update_channel(channel_id: str, body: NotificationChannelIn,
                         current_user: dict = Depends(require_admin)):
    res = await db.notification_channels.update_one(
        {"id": channel_id}, {"$set": body.model_dump()}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"id": channel_id, "updated": True}


@api_router.delete("/notifications/channels/{channel_id}")
async def delete_channel(channel_id: str, current_user: dict = Depends(require_admin)):
    await db.notification_channels.delete_one({"id": channel_id})
    return {"deleted": channel_id}


@api_router.post("/notifications/channels/{channel_id}/test")
async def test_channel(channel_id: str, current_user: dict = Depends(require_admin)):
    ch = await db.notification_channels.find_one({"id": channel_id}, {"_id": 0})
    if not ch:
        raise HTTPException(404, "Not found")
    status = await _send_via_channel(
        ch,
        subject="[TriageAI] Test notification",
        text=f"Hello from TriageAI! This is a test notification sent by {current_user['name']} ({current_user['email']}) at {datetime.now(timezone.utc).isoformat()}.",
        html=f"<h3>TriageAI Test</h3><p>Hello from <b>TriageAI</b>. This is a test notification sent by {current_user['name']}.</p>",
    )
    await db.notification_channels.update_one(
        {"id": channel_id},
        {"$set": {"last_used_at": datetime.now(timezone.utc).isoformat(), "last_status": status}}
    )
    return {"id": channel_id, "status": status}


@api_router.get("/notifications/log")
async def notification_log(limit: int = 50, current_user: dict = Depends(get_current_user)):
    docs = await db.notification_log.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs


# ---------- ANALYTICS ----------
@api_router.get("/analytics/summary")
async def analytics_summary(current_user: dict = Depends(get_current_user)):
    alerts = await db.alerts.find({}, {"_id": 0}).to_list(5000)
    incidents = await db.incidents.find({}, {"_id": 0}).to_list(1000)

    by_source: dict = {}
    by_severity: dict = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in alerts:
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1
        if a["severity"] in by_severity:
            by_severity[a["severity"]] += 1

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


# ---------- SEED & DEMO ----------
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
async def seed_data(current_user: dict = Depends(get_current_user)):
    await db.alerts.delete_many({})
    await db.incidents.delete_many({})
    await db.triage_results.delete_many({})
    await db.incident_chats.delete_many({})

    now = datetime.now(timezone.utc)
    docs = []
    for source, sev, svc, region, title in SAMPLE_ALERTS:
        a = Alert(
            source=source, severity=sev, service=svc, region=region, title=title,
            description=f"Auto-generated sample alert from {source}.",
            timestamp=(now - timedelta(minutes=random.randint(1, 90))).isoformat(),
        )
        docs.append(a.model_dump())
    await db.alerts.insert_many(docs)
    return {"seeded": len(docs)}


@api_router.post("/demo/age-alerts")
async def age_alerts(current_user: dict = Depends(get_current_user)):
    """Set 3 active alerts to be 6 days old so the unattended notification fires."""
    six_days_ago = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    actives = await db.alerts.find({"status": "active"}, {"_id": 0}).limit(3).to_list(3)
    if not actives:
        return {"aged": 0}
    ids = [a["id"] for a in actives]
    await db.alerts.update_many({"id": {"$in": ids}}, {"$set": {"timestamp": six_days_ago}})
    return {"aged": len(ids), "ids": ids}


@api_router.post("/alerts/simulate")
async def simulate_alert(current_user: dict = Depends(get_current_user)):
    src, sev, svc, region, title = random.choice(SAMPLE_ALERTS)
    a = Alert(
        source=src, severity=sev, service=svc, region=region,
        title=title + f" (sim {datetime.now(timezone.utc).strftime('%H:%M:%S')})",
        description="Simulated alert."
    )
    await db.alerts.insert_one(a.model_dump())
    return a


# ====================================================================================================
# F-01 DEPLOYMENT CHANGE CORRELATION
# ====================================================================================================

# -------------------- Token encryption (Fernet) --------------------
def _fernet() -> Fernet:
    key = hashlib.sha256(JWT_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_token(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_token(enc: str) -> str:
    if not enc:
        return ""
    try:
        return _fernet().decrypt(enc.encode()).decode()
    except (InvalidToken, Exception):
        return ""


# -------------------- CI/CD Models --------------------
CICDType = Literal["github", "gitlab", "circle", "argocd", "mock"]


class CICDTool(BaseModel):
    id: str = Field(default_factory=lambda: f"CCT-{uuid.uuid4().hex[:8].upper()}")
    name: str
    type: CICDType
    api_token_enc: str = ""           # encrypted at rest
    base_url: str = ""                # e.g. "https://api.github.com/repos/org/repo"
    watch_services: List[str] = []    # e.g. ["payments-api", "auth-service"]
    active: bool = True
    last_sync_at: Optional[str] = None
    last_sync_status: Optional[str] = None  # "ok" | "error: ..."
    sync_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CICDToolIn(BaseModel):
    name: str
    type: CICDType
    api_token: Optional[str] = ""       # plain — will be encrypted before storage
    base_url: Optional[str] = ""
    watch_services: List[str] = []
    active: bool = True


class Deployer(BaseModel):
    name: str = ""
    handle: str = ""
    avatar_url: Optional[str] = None


class DeploymentEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"DEP-{uuid.uuid4().hex[:8].upper()}")
    cicd_tool_id: str
    service: str
    version: str = ""
    deployed_by_name: str = ""
    deployed_by_handle: str = ""
    deployed_by_avatar: Optional[str] = None
    deployed_at: str
    changed_files: List[str] = []
    diff_summary: str = ""
    pr_title: str = ""
    pr_url: str = ""
    rollback_command: str = ""
    ci_run_url: str = ""
    external_id: Optional[str] = None  # to dedupe upstream
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# -------------------- CI/CD Adapters --------------------
class BaseCICDAdapter:
    """Adapter interface. Subclasses fetch deployment events from a specific CI/CD provider."""
    type_name: str = "base"

    def __init__(self, tool: dict):
        self.tool = tool
        self.token = decrypt_token(tool.get("api_token_enc", ""))
        self.base_url = (tool.get("base_url") or "").rstrip("/")
        self.watch_services = tool.get("watch_services", []) or []

    async def fetch_recent_deployments(self, since: datetime, force: bool = False) -> List[Dict[str, Any]]:
        """Return list of normalized deployment dicts (matching DeploymentEvent fields, no id/created_at).
        If `force=True`, always return at least one event (used for /test endpoint)."""
        raise NotImplementedError


class GitHubActionsAdapter(BaseCICDAdapter):
    """Fetch successful workflow runs (= deployments) from GitHub Actions.

    base_url should be: https://api.github.com/repos/{owner}/{repo}
    api_token is a PAT with `repo` + `actions:read` scopes.
    """
    type_name = "github"

    async def fetch_recent_deployments(self, since: datetime, force: bool = False) -> List[Dict[str, Any]]:
        if not self.token or not self.base_url:
            raise RuntimeError("api_token and base_url are required for GitHub Actions")
        if not self.base_url.startswith("http"):
            raise RuntimeError("base_url must be a full URL")
        # GitHub Actions API
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        since_str = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        async with httpx.AsyncClient(timeout=20.0) as http:
            runs_url = f"{self.base_url}/actions/runs"
            r = await http.get(
                runs_url,
                headers=headers,
                params={
                    "status": "success",
                    "created": f">={since_str}",
                    "per_page": 30,
                },
            )
            r.raise_for_status()
            runs = r.json().get("workflow_runs", [])
            out: List[Dict[str, Any]] = []
            for run in runs:
                head_sha = run.get("head_sha", "")
                run_id = str(run.get("id", ""))
                deployed_at_iso = run.get("updated_at") or run.get("created_at")
                actor = run.get("actor") or {}
                ci_run_url = run.get("html_url", "")
                # Map service: first watch_service or derive from workflow name
                service = (self.watch_services[0] if self.watch_services
                           else (run.get("name") or "unknown"))
                # Fetch diff via /compare for changed files (best-effort)
                changed_files: List[str] = []
                diff_summary = ""
                pr_title = run.get("display_title") or run.get("name", "")
                pr_url = ""
                # Pull request associated
                prs = run.get("pull_requests", []) or []
                if prs:
                    pr_url = prs[0].get("url", "")
                    # html PR url
                    if pr_url.startswith("https://api.github.com/repos/"):
                        pr_url = (pr_url.replace("https://api.github.com/repos/",
                                                 "https://github.com/")
                                        .replace("/pulls/", "/pull/"))
                try:
                    if head_sha:
                        commit_resp = await http.get(
                            f"{self.base_url}/commits/{head_sha}", headers=headers
                        )
                        if commit_resp.status_code == 200:
                            commit = commit_resp.json()
                            files = commit.get("files", []) or []
                            changed_files = [f.get("filename", "") for f in files][:20]
                            patches = [f.get("patch", "") for f in files[:3] if f.get("patch")]
                            diff_summary = "\n".join(patches)[:1500]
                except Exception:
                    pass
                out.append({
                    "service": service,
                    "version": (head_sha[:7] if head_sha else (run.get("run_number") and f"run#{run['run_number']}" or "")),
                    "deployed_by_name": actor.get("login", ""),
                    "deployed_by_handle": actor.get("login", ""),
                    "deployed_by_avatar": actor.get("avatar_url"),
                    "deployed_at": deployed_at_iso,
                    "changed_files": changed_files,
                    "diff_summary": diff_summary,
                    "pr_title": pr_title,
                    "pr_url": pr_url,
                    "rollback_command": f"kubectl rollout undo deploy/{service}",
                    "ci_run_url": ci_run_url,
                    "external_id": f"gh:{run_id}",
                })
            return out


class MockAdapter(BaseCICDAdapter):
    """Synthetic adapter for demo/testing. Each sync MAY create a deployment in the last few minutes
    for one of the watched services. Idempotent via external_id."""
    type_name = "mock"

    MOCK_PRS = [
        ("Perf: tune DB connection pool limits", [
            "src/OrderController.java",
            "src/PaymentService.java",
            "db/migrations/V42_add_indexes.sql",
            "config/application.yml",
        ], "-connection_limit=100\n+connection_limit=20"),
        ("Feat: switch payments to async queue", [
            "services/payments/queue.py",
            "services/payments/handler.py",
            "config/queue.yml",
        ], "+await queue.publish(event)\n-sync_publish(event)"),
        ("Fix: retry policy on auth token refresh", [
            "auth/token_refresh.py",
            "auth/retry.py",
        ], "-max_retries=3\n+max_retries=1"),
        ("Chore: bump cache TTL to reduce origin load", [
            "edge/cache_config.ts",
            "edge/headers.ts",
        ], "-ttl: 60\n+ttl: 3600"),
        ("Refactor: extract checkout validation", [
            "checkout/validate.go",
            "checkout/order.go",
        ], "+func validateOrder(...) {...}"),
    ]
    MOCK_DEPLOYERS = [
        ("Jane Smith",   "jane",   "https://avatars.githubusercontent.com/u/1?v=4"),
        ("Alex Chen",    "alexc",  "https://avatars.githubusercontent.com/u/2?v=4"),
        ("Maya Patel",   "mayap",  "https://avatars.githubusercontent.com/u/3?v=4"),
        ("Sam Rivera",   "samr",   "https://avatars.githubusercontent.com/u/4?v=4"),
    ]

    async def fetch_recent_deployments(self, since: datetime, force: bool = False) -> List[Dict[str, Any]]:
        # Generate 0-1 fresh deployments per sync, deployed within (since, now)
        services = self.watch_services or ["payments-api", "auth-service", "checkout-svc", "edge-cdn"]
        # Probability gate: 25% chance per sync to "deploy" (always if force=True)
        if not force and random.random() > 0.25:
            return []
        svc = random.choice(services)
        deployer = random.choice(self.MOCK_DEPLOYERS)
        pr_title, files, diff = random.choice(self.MOCK_PRS)
        now = datetime.now(timezone.utc)
        # Pick a time between `since` and `now`
        span_s = max(60, int((now - since).total_seconds()))
        deployed_at = now - timedelta(seconds=random.randint(0, span_s - 30))
        version = f"v{random.randint(1, 5)}.{random.randint(0, 12)}.{random.randint(0, 30)}"
        run_id = uuid.uuid4().hex[:10]
        return [{
            "service": svc,
            "version": version,
            "deployed_by_name": deployer[0],
            "deployed_by_handle": deployer[1],
            "deployed_by_avatar": deployer[2],
            "deployed_at": deployed_at.isoformat(),
            "changed_files": files,
            "diff_summary": diff,
            "pr_title": pr_title,
            "pr_url": f"https://github.com/triageai-demo/{svc}/pull/{random.randint(100, 999)}",
            "rollback_command": f"kubectl rollout undo deploy/{svc}",
            "ci_run_url": f"https://github.com/triageai-demo/{svc}/actions/runs/{run_id}",
            "external_id": f"mock:{run_id}",
        }]


class _StubAdapter(BaseCICDAdapter):
    async def fetch_recent_deployments(self, since: datetime, force: bool = False) -> List[Dict[str, Any]]:
        raise NotImplementedError(f"{self.type_name} adapter is not yet implemented")


class GitLabAdapter(_StubAdapter):
    type_name = "gitlab"


class CircleCIAdapter(_StubAdapter):
    type_name = "circle"


class ArgoCDAdapter(_StubAdapter):
    type_name = "argocd"


def _adapter_for(tool: dict) -> BaseCICDAdapter:
    t = tool.get("type")
    if t == "github": return GitHubActionsAdapter(tool)
    if t == "gitlab": return GitLabAdapter(tool)
    if t == "circle": return CircleCIAdapter(tool)
    if t == "argocd": return ArgoCDAdapter(tool)
    if t == "mock":   return MockAdapter(tool)
    raise RuntimeError(f"Unknown CI/CD type: {t}")


# -------------------- CI/CD Service (sync) --------------------
class CICDToolService:
    @staticmethod
    async def sync_tool(tool: dict, lookback_minutes: int = 120, force: bool = False) -> Dict[str, Any]:
        """Pull recent deployments from the adapter and upsert into deployment_events."""
        adapter = _adapter_for(tool)
        since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
        try:
            events = await adapter.fetch_recent_deployments(since, force=force)
        except Exception as e:
            logger.exception("CICD sync failed for %s (%s): %s", tool.get("name"), tool.get("type"), e)
            await db.cicd_tools.update_one(
                {"id": tool["id"]},
                {"$set": {"last_sync_at": datetime.now(timezone.utc).isoformat(),
                          "last_sync_status": f"error: {str(e)[:140]}"}},
            )
            return {"ok": False, "error": str(e), "ingested": 0}

        ingested = 0
        for ev in events:
            ext_id = ev.get("external_id")
            if ext_id:
                existing = await db.deployment_events.find_one({"external_id": ext_id, "cicd_tool_id": tool["id"]})
                if existing:
                    continue
            doc = DeploymentEvent(cicd_tool_id=tool["id"], **ev).model_dump()
            await db.deployment_events.insert_one(doc)
            ingested += 1

        await db.cicd_tools.update_one(
            {"id": tool["id"]},
            {"$set": {"last_sync_at": datetime.now(timezone.utc).isoformat(),
                      "last_sync_status": "ok"},
             "$inc": {"sync_count": 1}},
        )
        return {"ok": True, "ingested": ingested}

    @staticmethod
    async def sync_all() -> Dict[str, Any]:
        tools = await db.cicd_tools.find({"active": True}, {"_id": 0}).to_list(50)
        results = []
        for t in tools:
            r = await CICDToolService.sync_tool(t)
            results.append({"tool_id": t["id"], "name": t["name"], **r})
        return {"synced": len(results), "results": results}


# -------------------- DeploymentCorrelator --------------------
class DeploymentCorrelator:
    RISKY_KEYWORDS = [
        "migration", "config", "connection", "pool", "limit", "timeout",
        "database", "db", "auth", "index", "cache", "queue", "retry",
        "memory", "throttle", "ratelimit", "deploy", "k8s", "kubernetes",
    ]

    @staticmethod
    def _parse_dt(s: str) -> Optional[datetime]:
        if not s: return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    @classmethod
    def score(cls, deployment: dict, incident_services: List[str], first_alert_at: datetime) -> float:
        deployed_at = cls._parse_dt(deployment.get("deployed_at", ""))
        if not deployed_at:
            return 0.0

        # 1) Time delta score (50% weight)
        delta_min = (first_alert_at - deployed_at).total_seconds() / 60.0
        if delta_min < 0:
            time_score = 0.0
        elif delta_min <= 5:
            time_score = 1.0
        elif delta_min <= 15:
            time_score = 0.85
        elif delta_min <= 30:
            time_score = 0.6
        elif delta_min <= 60:
            time_score = 0.3
        elif delta_min <= 120:
            time_score = 0.1
        else:
            time_score = 0.0

        # 2) Service match score (35% weight)
        inc_services = {s.lower().strip() for s in incident_services if s}
        dep_service = (deployment.get("service") or "").lower().strip()
        if not dep_service:
            service_score = 0.0
        elif dep_service in inc_services:
            service_score = 1.0
        elif any(dep_service in s or s in dep_service for s in inc_services):
            service_score = 0.6
        else:
            service_score = 0.1

        # 3) Changed-files relevance score (15% weight)
        changed_text = " ".join(deployment.get("changed_files", []) or []).lower()
        kw_hits = sum(1 for kw in cls.RISKY_KEYWORDS if kw in changed_text)
        if any(s in changed_text for s in inc_services if s):
            kw_hits += 2
        file_score = min(1.0, kw_hits / 4.0)

        total = (time_score * 0.5) + (service_score * 0.35) + (file_score * 0.15)
        return round(total, 3)

    @staticmethod
    def label(score: float) -> str:
        if score >= 0.7: return "high"
        if score >= 0.4: return "medium"
        return "low"

    @classmethod
    async def find_for_alerts(cls, alerts: List[dict], window_minutes: int = 30,
                              confidence_min: float = 0.3) -> List[dict]:
        """Find deployments correlated with the given alerts (used during triage prompt enrichment)."""
        if not alerts:
            return []
        first_alert_at = None
        for a in alerts:
            dt = cls._parse_dt(a.get("timestamp", ""))
            if dt and (first_alert_at is None or dt < first_alert_at):
                first_alert_at = dt
        if not first_alert_at:
            return []
        return await cls._find(first_alert_at, [a.get("service", "") for a in alerts],
                               window_minutes, confidence_min)

    @classmethod
    async def find_for_incident(cls, incident_id: str, window_minutes: int = 30,
                                confidence_min: float = 0.3) -> List[dict]:
        inc = await db.incidents.find_one({"id": incident_id}, {"_id": 0})
        if not inc:
            raise HTTPException(404, "Incident not found")
        alerts = await db.alerts.find({"id": {"$in": inc.get("alert_ids", [])}}, {"_id": 0}).to_list(200)
        first_alert_at = None
        for a in alerts:
            dt = cls._parse_dt(a.get("timestamp", ""))
            if dt and (first_alert_at is None or dt < first_alert_at):
                first_alert_at = dt
        if not first_alert_at:
            # fall back to incident creation time
            first_alert_at = cls._parse_dt(inc.get("created_at", "")) or datetime.now(timezone.utc)
        return await cls._find(first_alert_at,
                               inc.get("affected_services") or [a.get("service", "") for a in alerts],
                               window_minutes, confidence_min)

    @classmethod
    async def _find(cls, first_alert_at: datetime, incident_services: List[str],
                    window_minutes: int, confidence_min: float) -> List[dict]:
        # query: deployed_at in [wide_start, first_alert_at]; we widen to 2h then filter in memory by score (since
        # the time portion of confidence already drops to 0 beyond 2h).
        wide_start = (first_alert_at - timedelta(minutes=max(window_minutes, 120))).isoformat()
        wide_end = first_alert_at.isoformat()
        docs = await db.deployment_events.find(
            {"deployed_at": {"$gte": wide_start, "$lte": wide_end}},
            {"_id": 0},
        ).sort("deployed_at", -1).to_list(100)
        scored: List[dict] = []
        for d in docs:
            sc = cls.score(d, incident_services, first_alert_at)
            if sc < confidence_min:
                continue
            deployed_at = cls._parse_dt(d.get("deployed_at", "")) or first_alert_at
            minutes_before = max(0, int((first_alert_at - deployed_at).total_seconds() / 60))
            scored.append({
                "id": d["id"],
                "service": d.get("service", ""),
                "version": d.get("version", ""),
                "deployed_by": {
                    "name": d.get("deployed_by_name", ""),
                    "handle": d.get("deployed_by_handle", ""),
                    "avatar_url": d.get("deployed_by_avatar"),
                },
                "deployed_at": d.get("deployed_at"),
                "minutes_before_incident": minutes_before,
                "confidence": sc,
                "confidence_label": cls.label(sc),
                "changed_files": d.get("changed_files", []) or [],
                "diff_summary": d.get("diff_summary", ""),
                "pr_title": d.get("pr_title", ""),
                "pr_url": d.get("pr_url", ""),
                "ci_run_url": d.get("ci_run_url", ""),
                "rollback_command": d.get("rollback_command", ""),
                "cicd_tool_id": d.get("cicd_tool_id"),
            })
        scored.sort(key=lambda x: x["confidence"], reverse=True)
        return scored


def _build_deployment_prompt_block(deployments: List[dict]) -> str:
    """Render the deployment context for the Claude triage prompt (only confidence >= 0.3)."""
    if not deployments:
        return ""
    relevant = [d for d in deployments if d.get("confidence", 0) >= 0.3]
    if not relevant:
        return ""
    lines = ["", "RECENT DEPLOYMENTS (before first alert):"]
    for d in relevant[:5]:
        deployer = (d["deployed_by"].get("name")
                    or d["deployed_by"].get("handle") or "unknown")
        lines.append(
            f"- {d['service']} {d.get('version','')} by @{d['deployed_by'].get('handle') or deployer}, "
            f"{d['minutes_before_incident']} min before incident "
            f"(confidence: {d['confidence_label']} {d['confidence']})"
        )
        if d.get("changed_files"):
            lines.append("  Changed files: " + ", ".join(d["changed_files"][:5]))
        if d.get("diff_summary"):
            excerpt = d["diff_summary"].replace("\n", " | ")[:200]
            lines.append(f"  Diff excerpt: {excerpt}")
        if d.get("pr_title"):
            lines.append(f"  PR: '{d['pr_title']}'")
    lines.append("")
    lines.append("Consider whether any recent deployment is the root cause.")
    lines.append("If confident, rank it #1 hypothesis and include rollback as step 1.")
    return "\n".join(lines)


# -------------------- CI/CD Tool routes --------------------
def _tool_view(t: dict) -> dict:
    """Strip encrypted token from API view, expose has_token flag."""
    out = {k: v for k, v in t.items() if k != "_id" and k != "api_token_enc"}
    out["has_token"] = bool(t.get("api_token_enc"))
    return out


@api_router.get("/cicd/tools")
async def list_cicd_tools(current_user: dict = Depends(get_current_user)):
    docs = await db.cicd_tools.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return [_tool_view(d) for d in docs]


@api_router.post("/cicd/tools")
async def add_cicd_tool(body: CICDToolIn, current_user: dict = Depends(require_admin)):
    tool = CICDTool(
        name=body.name, type=body.type,
        api_token_enc=encrypt_token(body.api_token or ""),
        base_url=body.base_url or "",
        watch_services=body.watch_services or [],
        active=body.active,
    )
    await db.cicd_tools.insert_one(tool.model_dump())
    return _tool_view(tool.model_dump())


@api_router.patch("/cicd/tools/{tool_id}")
async def update_cicd_tool(tool_id: str, body: CICDToolIn,
                           current_user: dict = Depends(require_admin)):
    existing = await db.cicd_tools.find_one({"id": tool_id})
    if not existing:
        raise HTTPException(404, "Tool not found")
    update: Dict[str, Any] = {
        "name": body.name, "type": body.type,
        "base_url": body.base_url or "",
        "watch_services": body.watch_services or [],
        "active": body.active,
    }
    # Only replace token if a new one was provided (non-empty)
    if body.api_token:
        update["api_token_enc"] = encrypt_token(body.api_token)
    await db.cicd_tools.update_one({"id": tool_id}, {"$set": update})
    doc = await db.cicd_tools.find_one({"id": tool_id}, {"_id": 0})
    return _tool_view(doc)


@api_router.delete("/cicd/tools/{tool_id}")
async def delete_cicd_tool(tool_id: str, current_user: dict = Depends(require_admin)):
    await db.cicd_tools.delete_one({"id": tool_id})
    return {"deleted": tool_id}


@api_router.post("/cicd/tools/{tool_id}/test")
async def test_cicd_tool(tool_id: str, current_user: dict = Depends(require_admin)):
    """Run a single sync immediately and return ingested count + any error. Forces a deployment for mock tools."""
    tool = await db.cicd_tools.find_one({"id": tool_id}, {"_id": 0})
    if not tool:
        raise HTTPException(404, "Not found")
    res = await CICDToolService.sync_tool(tool, lookback_minutes=30, force=True)
    return res


@api_router.post("/cicd/sync-all")
async def sync_all_cicd(current_user: dict = Depends(require_admin)):
    return await CICDToolService.sync_all()


@api_router.get("/cicd/deployments")
async def list_deployments(limit: int = 50, current_user: dict = Depends(get_current_user)):
    docs = await db.deployment_events.find({}, {"_id": 0}).sort("deployed_at", -1).to_list(limit)
    return docs


@api_router.get("/incidents/{incident_id}/deployments")
async def get_incident_deployments(
    incident_id: str,
    window_minutes: int = 30,
    confidence_min: float = 0.3,
    current_user: dict = Depends(get_current_user),
):
    # Clamp window
    window_minutes = max(1, min(window_minutes, 120))
    confidence_min = max(0.0, min(confidence_min, 1.0))
    deployments = await DeploymentCorrelator.find_for_incident(
        incident_id, window_minutes=window_minutes, confidence_min=confidence_min
    )
    return {"deployments": deployments, "window_minutes": window_minutes,
            "confidence_min": confidence_min}


# -------------------- Background sync loop --------------------
_sync_task_started = False


async def _periodic_cicd_sync():
    """Background task: run CICDToolService.sync_all() every 60s."""
    await asyncio.sleep(10)  # let app warm up
    while True:
        try:
            await CICDToolService.sync_all()
        except Exception as e:
            logger.exception("Periodic CICD sync failed: %s", e)
        await asyncio.sleep(60)


@app.on_event("startup")
async def seed_cicd_demo_tool():
    """Seed one mock CI/CD tool on first startup so the demo works out-of-the-box."""
    count = await db.cicd_tools.count_documents({})
    if count == 0:
        mock = CICDTool(
            name="Demo CI/CD (mock)",
            type="mock",
            api_token_enc="",
            base_url="https://example.com/mock-ci",
            watch_services=["payments-api", "payments-db", "auth-service",
                            "checkout-svc", "edge-cdn"],
            active=True,
        )
        await db.cicd_tools.insert_one(mock.model_dump())
        logger.info("Seeded demo mock CICD tool: %s", mock.id)

    # Start background sync loop exactly once
    global _sync_task_started
    if not _sync_task_started:
        _sync_task_started = True
        asyncio.create_task(_periodic_cicd_sync())
        logger.info("CICD periodic sync task started (every 60s)")


# ====================================================================================================
# END F-01
# ====================================================================================================


# ====================================================================================================
# F-02 PREDICTIVE TRIAGE
# Anomaly-detection-based incident prediction with risk scoring, ETA, AI recommendations & live WS.
# Adapted to repo stack: MongoDB (no InfluxDB), Mongo collections (no Alembic), Claude via
# emergentintegrations, asyncio background loop (5 min cadence), FastAPI WebSocket.
# ====================================================================================================
import numpy as np
from sklearn.ensemble import IsolationForest


# -------------------- F-02 Models --------------------
PredictiveStatus = Literal["open", "acknowledged", "resolved", "false_positive"]
MetricType = Literal["cpu_usage", "memory_usage", "db_connections", "api_latency_ms", "queue_depth"]

# Soft thresholds used for ETA + risk weighting (per metric, "critical" threshold).
METRIC_CRITICAL_THRESHOLDS: Dict[str, float] = {
    "cpu_usage": 90.0,           # %
    "memory_usage": 92.0,        # %
    "db_connections": 180.0,     # active connections (pool of 200)
    "api_latency_ms": 1500.0,    # ms p95
    "queue_depth": 5000.0,       # messages
}

METRIC_UNITS: Dict[str, str] = {
    "cpu_usage": "%",
    "memory_usage": "%",
    "db_connections": "conns",
    "api_latency_ms": "ms",
    "queue_depth": "msgs",
}


class MetricSample(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = "default"
    service_name: str
    metric_type: MetricType
    value: float
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PredictiveIncident(BaseModel):
    id: str = Field(default_factory=lambda: f"PRD-{uuid.uuid4().hex[:8].upper()}")
    org_id: str = "default"
    service_name: str
    metric_type: MetricType
    current_value: float
    expected_value: float
    anomaly_score: float                       # raw IsolationForest score (≈ -0.5..0.5; lower = more anomalous)
    risk_score: int                            # 0..100
    predicted_failure: bool                    # True if risk_score ≥ 70 OR ETA finite
    estimated_time_to_incident: Optional[int]  # minutes; None if no clear trend toward threshold
    recommended_action: str                    # AI-generated remediation
    status: PredictiveStatus = "open"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


# -------------------- F-02 Synthetic metric seeding --------------------
# Demo services & their per-metric baselines (mean, stdev). One service ("checkout-svc") is configured
# to drift upward on cpu_usage so the predictor reliably surfaces a real prediction in demos.
PREDICTIVE_SERVICES: List[str] = [
    "payments-api", "auth-service", "checkout-svc", "search-api", "notifications-worker",
]

_BASELINES: Dict[str, Dict[str, Dict[str, float]]] = {
    "payments-api":         {"cpu_usage": {"mu": 42.0, "sd": 4.0},  "memory_usage": {"mu": 55.0, "sd": 3.5},
                             "db_connections": {"mu": 60.0, "sd": 7.0}, "api_latency_ms": {"mu": 180.0, "sd": 25.0},
                             "queue_depth": {"mu": 120.0, "sd": 40.0}},
    "auth-service":         {"cpu_usage": {"mu": 28.0, "sd": 3.0},  "memory_usage": {"mu": 48.0, "sd": 3.0},
                             "db_connections": {"mu": 30.0, "sd": 5.0},  "api_latency_ms": {"mu": 90.0,  "sd": 12.0},
                             "queue_depth": {"mu": 60.0,  "sd": 20.0}},
    "checkout-svc":         {"cpu_usage": {"mu": 55.0, "sd": 4.5},  "memory_usage": {"mu": 62.0, "sd": 4.0},
                             "db_connections": {"mu": 95.0, "sd": 9.0},  "api_latency_ms": {"mu": 220.0, "sd": 30.0},
                             "queue_depth": {"mu": 200.0, "sd": 60.0}},
    "search-api":           {"cpu_usage": {"mu": 38.0, "sd": 3.5},  "memory_usage": {"mu": 51.0, "sd": 3.0},
                             "db_connections": {"mu": 25.0, "sd": 4.0},  "api_latency_ms": {"mu": 140.0, "sd": 18.0},
                             "queue_depth": {"mu": 40.0,  "sd": 15.0}},
    "notifications-worker": {"cpu_usage": {"mu": 22.0, "sd": 3.0},  "memory_usage": {"mu": 45.0, "sd": 3.0},
                             "db_connections": {"mu": 18.0, "sd": 3.0},  "api_latency_ms": {"mu": 70.0,  "sd": 10.0},
                             "queue_depth": {"mu": 350.0, "sd": 90.0}},
}


def _next_sample_value(service: str, metric: MetricType, last_value: Optional[float], step_idx: int) -> float:
    """Generate next synthetic sample. The 'checkout-svc' cpu_usage drifts upward each step so
    the predictor reliably triggers (otherwise the dashboard looks empty in demos)."""
    base = _BASELINES[service][metric]
    mu, sd = base["mu"], base["sd"]
    rng = np.random.default_rng()
    val = float(rng.normal(mu, sd))
    # Anomaly injection for demo realism
    if service == "checkout-svc" and metric == "cpu_usage":
        drift = min(35.0, 0.7 * step_idx)  # gradual upward drift, capped
        val = float(rng.normal(mu + drift, sd))
    elif service == "checkout-svc" and metric == "memory_usage":
        drift = min(20.0, 0.3 * step_idx)
        val = float(rng.normal(mu + drift, sd))
    elif service == "payments-api" and metric == "api_latency_ms" and step_idx % 9 == 0:
        # occasional latency spike
        val = float(rng.normal(mu * 3.0, sd * 2))
    # Smooth with last value to avoid wild swings
    if last_value is not None:
        val = 0.7 * val + 0.3 * last_value
    # Clip to sensible ranges
    if metric in ("cpu_usage", "memory_usage"):
        val = max(1.0, min(100.0, val))
    else:
        val = max(0.0, val)
    return round(val, 2)


async def _seed_metric_history():
    """Seed ~4 hours of 1-min-resolution synthetic samples for every (service, metric)."""
    if await db.metrics.count_documents({}) > 0:
        return
    now = datetime.now(timezone.utc)
    samples: List[dict] = []
    points = 240  # 4 hours x 60
    for service in PREDICTIVE_SERVICES:
        for metric in METRIC_CRITICAL_THRESHOLDS.keys():
            last: Optional[float] = None
            for i in range(points):
                step = i  # 0 = oldest
                last = _next_sample_value(service, metric, last, step)
                ts = (now - timedelta(minutes=(points - i))).isoformat()
                samples.append(MetricSample(
                    service_name=service, metric_type=metric, value=last, timestamp=ts,
                ).model_dump())
    # Bulk insert in chunks
    chunk = 2000
    for i in range(0, len(samples), chunk):
        await db.metrics.insert_many(samples[i:i + chunk])
    # Index for fast time-range queries
    try:
        await db.metrics.create_index([("service_name", 1), ("metric_type", 1), ("timestamp", -1)])
    except Exception:
        pass
    logger.info("Seeded %d metric samples across %d services × %d metrics",
                len(samples), len(PREDICTIVE_SERVICES), len(METRIC_CRITICAL_THRESHOLDS))


# -------------------- F-02 WebSocket connection manager --------------------
class _PredictiveWSManager:
    def __init__(self):
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def broadcast(self, payload: dict):
        msg = json.dumps(payload, default=str)
        dead: List[WebSocket] = []
        async with self._lock:
            conns = list(self._connections)
        for ws in conns:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self._connections:
                        self._connections.remove(ws)


predictive_ws_manager = _PredictiveWSManager()


# -------------------- F-02 Predictor service --------------------
class PredictorService:
    """
    Pipeline:
      1. Pull recent metric samples per (service, metric) from Mongo.
      2. Run IsolationForest to score anomalies.
      3. Compute deviation from baseline (rolling mean) → risk score 0..100.
      4. Estimate time-to-incident via linear extrapolation toward critical threshold.
      5. If risk_score ≥ 60 OR predicted_failure: ask Claude for preventive recommendation.
      6. Upsert PredictiveIncident and broadcast over WS.
    """
    LOOKBACK_POINTS = 120        # ~2 hours at 1-min resolution
    TRAIN_CONTAMINATION = 0.05   # IsolationForest expected outlier fraction
    RISK_THRESHOLD_OPEN = 50     # below this we don't persist an incident
    RECOMMEND_THRESHOLD = 60

    @staticmethod
    async def _fetch_series(service: str, metric: str, n: int = 120) -> List[dict]:
        cur = db.metrics.find(
            {"service_name": service, "metric_type": metric},
            {"_id": 0, "value": 1, "timestamp": 1},
        ).sort("timestamp", -1).limit(n)
        rows = await cur.to_list(n)
        rows.reverse()  # chronological
        return rows

    @staticmethod
    def _score_series(values: np.ndarray) -> Dict[str, float]:
        """Return anomaly_score (raw IF, lower=more anomalous), normalized_anomaly (0..1),
        expected_value (rolling mean of all but last 10), trend_slope (units / minute)."""
        if len(values) < 30:
            return {"anomaly_score": 0.0, "normalized_anomaly": 0.0,
                    "expected_value": float(values.mean()) if len(values) else 0.0,
                    "trend_slope": 0.0}
        x = values.reshape(-1, 1)
        try:
            model = IsolationForest(
                n_estimators=80, contamination=PredictorService.TRAIN_CONTAMINATION, random_state=42,
            )
            model.fit(x[:-10] if len(x) > 15 else x)  # train on older data, evaluate on recent
            raw = float(model.score_samples(x[-1:].reshape(1, -1))[0])  # ≈ -0.5..0.5
        except Exception as e:
            logger.warning("IsolationForest failed: %s", e)
            raw = 0.0
        # Map raw IF score (typical range ~ -0.5..0.2; more negative = more anomalous) → 0..1
        normalized = max(0.0, min(1.0, (0.0 - raw) / 0.3 + 0.1))
        expected = float(values[:-10].mean()) if len(values) > 10 else float(values.mean())
        # Trend slope via simple linear regression on last 30 points (samples are ~1 min apart)
        recent = values[-30:] if len(values) >= 30 else values
        t = np.arange(len(recent), dtype=float)
        if recent.std() > 0:
            slope = float(np.polyfit(t, recent, 1)[0])
        else:
            slope = 0.0
        return {
            "anomaly_score": raw,
            "normalized_anomaly": normalized,
            "expected_value": expected,
            "trend_slope": slope,
        }

    @staticmethod
    def _risk_and_eta(metric: str, current: float, expected: float, normalized_anomaly: float,
                      trend_slope: float) -> Dict[str, Any]:
        threshold = METRIC_CRITICAL_THRESHOLDS[metric]
        # Deviation component: how much over baseline relative to (threshold - baseline)
        denom = max(1e-6, threshold - expected)
        deviation = max(0.0, (current - expected) / denom)  # 0..1+ when approaching threshold
        deviation_norm = max(0.0, min(1.0, deviation))
        # Composite: 60% anomaly, 30% deviation, 10% headroom-to-threshold
        headroom = max(0.0, min(1.0, current / threshold))
        risk = 0.6 * normalized_anomaly + 0.3 * deviation_norm + 0.1 * headroom
        risk_score = int(round(max(0.0, min(1.0, risk)) * 100))
        # ETA in minutes via linear extrapolation
        eta_min: Optional[int] = None
        if trend_slope > 1e-4 and current < threshold:
            minutes = (threshold - current) / trend_slope
            if 0 < minutes < 8 * 60:  # only show ETA within 8 hours
                eta_min = int(round(minutes))
        predicted_failure = risk_score >= 70 or (eta_min is not None and eta_min <= 60)
        return {
            "risk_score": risk_score,
            "estimated_time_to_incident": eta_min,
            "predicted_failure": predicted_failure,
        }

    @staticmethod
    async def _generate_recommendation(service: str, metric: str, current: float,
                                       expected: float, risk_score: int,
                                       eta_min: Optional[int]) -> str:
        """Ask Claude for a concise, actionable preventive remediation. Falls back to a static
        template if the LLM is unavailable."""
        unit = METRIC_UNITS.get(metric, "")
        threshold = METRIC_CRITICAL_THRESHOLDS[metric]
        prompt = (
            f"You are an SRE copilot. A predictive anomaly detector found a developing issue "
            f"in service '{service}' on metric '{metric}'.\n\n"
            f"Context:\n"
            f"- Current value: {current:.2f}{unit}\n"
            f"- Expected baseline: {expected:.2f}{unit}\n"
            f"- Critical threshold: {threshold}{unit}\n"
            f"- Risk score: {risk_score}/100\n"
            f"- Estimated time to incident: {eta_min if eta_min is not None else 'unclear'} minutes\n\n"
            f"Reply with 1-3 specific PREVENTIVE actions an on-call engineer should take RIGHT NOW "
            f"to avoid this incident. Include exact kubectl/SQL/CLI commands where relevant. "
            f"Keep total length under 600 characters. Plain text only — no markdown headings."
        )
        if not llm_is_configured():
            return PredictorService._fallback_recommendation(service, metric, current, expected, eta_min)
        try:
            chat = llm_chat(
                session_id=f"predict-{service}-{metric}-{uuid.uuid4().hex[:6]}",
                system_message="You are TriageAI's predictive remediation engine. Be concise and operational.",
                model_hint="anthropic:claude-sonnet-4-5-20250929",
            )
            text = await chat.send_message(UserMessage(text=prompt))
            return (text or "").strip()[:1500] or PredictorService._fallback_recommendation(
                service, metric, current, expected, eta_min)
        except Exception as e:
            logger.warning("Claude recommendation failed for %s/%s: %s", service, metric, e)
            return PredictorService._fallback_recommendation(service, metric, current, expected, eta_min)

    @staticmethod
    def _fallback_recommendation(service: str, metric: str, current: float, expected: float,
                                 eta_min: Optional[int]) -> str:
        eta = f"~{eta_min}m to threshold" if eta_min is not None else "trend unclear"
        recipes = {
            "cpu_usage": (f"CPU on {service} is {current:.1f}% (baseline {expected:.1f}%). "
                          f"1) Scale out replicas: kubectl scale deploy/{service} --replicas=+2  "
                          f"2) Profile hot code paths and check for runaway loops. ({eta})"),
            "memory_usage": (f"Memory on {service} at {current:.1f}%. "
                             f"1) Bump request/limit memory by 25%  2) Trigger a rolling restart: "
                             f"kubectl rollout restart deploy/{service}  3) Look for leaks in last deploy. ({eta})"),
            "db_connections": (f"DB connections on {service} = {current:.0f}. "
                               f"1) Increase pool max_size or add a pgbouncer pool  "
                               f"2) Audit long-running queries (pg_stat_activity).  ({eta})"),
            "api_latency_ms": (f"p95 latency on {service} = {current:.0f}ms (baseline {expected:.0f}ms). "
                               f"1) Check downstream service health  2) Inspect slow query log  "
                               f"3) Enable circuit breaker on noisy callers. ({eta})"),
            "queue_depth": (f"Queue depth on {service} = {current:.0f} msgs. "
                            f"1) Scale workers: kubectl scale deploy/{service}-worker --replicas=+3  "
                            f"2) Verify consumer lag in Kafka.  ({eta})"),
        }
        return recipes.get(metric, f"Investigate anomalous {metric} on {service}. ({eta})")

    @classmethod
    async def run(cls, org_id: str = "default", services: Optional[List[str]] = None) -> List[dict]:
        """Run full prediction pipeline. Returns list of new/updated PredictiveIncident dicts."""
        target_services = services or PREDICTIVE_SERVICES
        created: List[dict] = []
        for service in target_services:
            for metric in METRIC_CRITICAL_THRESHOLDS.keys():
                series = await cls._fetch_series(service, metric, cls.LOOKBACK_POINTS)
                if len(series) < 30:
                    continue
                values = np.array([s["value"] for s in series], dtype=float)
                current_value = float(values[-1])
                stats = cls._score_series(values)
                risk = cls._risk_and_eta(
                    metric, current_value, stats["expected_value"],
                    stats["normalized_anomaly"], stats["trend_slope"],
                )
                if risk["risk_score"] < cls.RISK_THRESHOLD_OPEN:
                    # Auto-resolve any lingering open prediction for this (service, metric)
                    await db.predictive_incidents.update_many(
                        {"org_id": org_id, "service_name": service, "metric_type": metric,
                         "status": {"$in": ["open", "acknowledged"]}},
                        {"$set": {"status": "resolved",
                                  "resolved_at": datetime.now(timezone.utc).isoformat(),
                                  "resolved_by": "auto:trend-normalized"}},
                    )
                    continue
                # Skip if there's already an open incident for the same (service, metric)
                existing = await db.predictive_incidents.find_one(
                    {"org_id": org_id, "service_name": service, "metric_type": metric,
                     "status": {"$in": ["open", "acknowledged"]}},
                    {"_id": 0},
                )
                if existing:
                    # Refresh dynamic fields on the existing open incident
                    update = {
                        "current_value": current_value,
                        "expected_value": round(stats["expected_value"], 2),
                        "anomaly_score": round(stats["anomaly_score"], 4),
                        "risk_score": risk["risk_score"],
                        "predicted_failure": risk["predicted_failure"],
                        "estimated_time_to_incident": risk["estimated_time_to_incident"],
                    }
                    await db.predictive_incidents.update_one({"id": existing["id"]}, {"$set": update})
                    existing.update(update)
                    created.append(existing)
                    continue
                # New prediction → optionally ask Claude
                if risk["risk_score"] >= cls.RECOMMEND_THRESHOLD or risk["predicted_failure"]:
                    rec = await cls._generate_recommendation(
                        service, metric, current_value, stats["expected_value"],
                        risk["risk_score"], risk["estimated_time_to_incident"],
                    )
                else:
                    rec = cls._fallback_recommendation(
                        service, metric, current_value, stats["expected_value"],
                        risk["estimated_time_to_incident"],
                    )
                inc = PredictiveIncident(
                    org_id=org_id,
                    service_name=service,
                    metric_type=metric,
                    current_value=current_value,
                    expected_value=round(stats["expected_value"], 2),
                    anomaly_score=round(stats["anomaly_score"], 4),
                    risk_score=risk["risk_score"],
                    predicted_failure=risk["predicted_failure"],
                    estimated_time_to_incident=risk["estimated_time_to_incident"],
                    recommended_action=rec,
                )
                await db.predictive_incidents.insert_one(inc.model_dump())
                created.append(inc.model_dump())
                # Broadcast over WS
                await predictive_ws_manager.broadcast({"event": "prediction.new", "data": inc.model_dump()})
        return created


# -------------------- F-02 API endpoints --------------------
@api_router.post("/predictive-triage")
async def trigger_predictive_triage(current_user: dict = Depends(get_current_user)):
    """Force-run the predictor pipeline immediately. Useful for the 'Refresh' button and tests."""
    results = await PredictorService.run(org_id="default")
    return {"generated": len(results), "predictions": results}


@api_router.get("/predictive-incidents")
async def list_predictive_incidents(
    status: Optional[PredictiveStatus] = None,
    service: Optional[str] = None,
    min_risk: int = 0,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    q: Dict[str, Any] = {"org_id": "default"}
    if status:
        q["status"] = status
    if service:
        q["service_name"] = service
    if min_risk:
        q["risk_score"] = {"$gte": int(min_risk)}
    docs = await db.predictive_incidents.find(q, {"_id": 0}).sort([
        ("risk_score", -1), ("created_at", -1),
    ]).to_list(limit)
    return docs


@api_router.patch("/predictive-incidents/{incident_id}/resolve")
async def resolve_predictive_incident(
    incident_id: str,
    current_user: dict = Depends(get_current_user),
):
    res = await db.predictive_incidents.update_one(
        {"id": incident_id},
        {"$set": {
            "status": "resolved",
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolved_by": current_user["email"],
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Predictive incident not found")
    doc = await db.predictive_incidents.find_one({"id": incident_id}, {"_id": 0})
    await predictive_ws_manager.broadcast({"event": "prediction.resolved", "data": doc})
    return doc


@api_router.patch("/predictive-incidents/{incident_id}/acknowledge")
async def acknowledge_predictive_incident(
    incident_id: str,
    current_user: dict = Depends(get_current_user),
):
    res = await db.predictive_incidents.update_one(
        {"id": incident_id, "status": "open"}, {"$set": {"status": "acknowledged"}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Predictive incident not found or already acknowledged")
    doc = await db.predictive_incidents.find_one({"id": incident_id}, {"_id": 0})
    return doc


@api_router.get("/predictive-incidents/{incident_id}/trend")
async def predictive_incident_trend(
    incident_id: str,
    points: int = Query(120, ge=10, le=480),
    current_user: dict = Depends(get_current_user),
):
    """Return the underlying metric series + threshold so the frontend can draw a trend graph."""
    inc = await db.predictive_incidents.find_one({"id": incident_id}, {"_id": 0})
    if not inc:
        raise HTTPException(404, "Predictive incident not found")
    series = await PredictorService._fetch_series(inc["service_name"], inc["metric_type"], points)
    return {
        "incident": inc,
        "threshold": METRIC_CRITICAL_THRESHOLDS.get(inc["metric_type"]),
        "unit": METRIC_UNITS.get(inc["metric_type"], ""),
        "series": series,
    }


@api_router.get("/predictive-services/summary")
async def predictive_services_summary(current_user: dict = Depends(get_current_user)):
    """Per-service rollup used for the 'High Risk Services' strip + Risk Score Cards."""
    pipeline = [
        {"$match": {"org_id": "default", "status": {"$in": ["open", "acknowledged"]}}},
        {"$group": {
            "_id": "$service_name",
            "max_risk": {"$max": "$risk_score"},
            "avg_risk": {"$avg": "$risk_score"},
            "predictions": {"$sum": 1},
            "min_eta": {"$min": "$estimated_time_to_incident"},
        }},
        {"$sort": {"max_risk": -1}},
    ]
    rows = await db.predictive_incidents.aggregate(pipeline).to_list(50)
    # Ensure every known service appears (even healthy ones)
    by_service = {r["_id"]: r for r in rows}
    out = []
    for svc in PREDICTIVE_SERVICES:
        r = by_service.get(svc)
        if r:
            out.append({
                "service_name": svc,
                "max_risk": int(r["max_risk"] or 0),
                "avg_risk": int(round(r["avg_risk"] or 0)),
                "predictions": int(r["predictions"] or 0),
                "min_eta": r["min_eta"],
            })
        else:
            out.append({"service_name": svc, "max_risk": 0, "avg_risk": 0,
                        "predictions": 0, "min_eta": None})
    return out


# -------------------- F-02 WebSocket --------------------
# NB: routed under /api/* so the k8s ingress maps it to the backend container on :8001.
@app.websocket("/api/ws/predictive-alerts")
async def ws_predictive_alerts(ws: WebSocket):
    # Optional token auth via query param (?token=...). Falls back to anonymous read-only for demos.
    token = ws.query_params.get("token", "")
    if token:
        try:
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            await ws.close(code=4401)
            return
    await predictive_ws_manager.connect(ws)
    try:
        # Greet the client with current open predictions
        opens = await db.predictive_incidents.find(
            {"org_id": "default", "status": {"$in": ["open", "acknowledged"]}}, {"_id": 0},
        ).sort("risk_score", -1).to_list(50)
        await ws.send_text(json.dumps({"event": "snapshot", "data": opens}, default=str))
        while True:
            # We mostly broadcast → client doesn't need to send anything, but support a ping.
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("Predictive WS error: %s", e)
    finally:
        await predictive_ws_manager.disconnect(ws)


# -------------------- F-02 Background loop --------------------
_predictive_task_started = False


async def _periodic_predictive_run():
    """Every 5 minutes: append a fresh sample per (service, metric) to simulate live metrics,
    then run the predictor and broadcast new findings."""
    await asyncio.sleep(15)  # warm-up after startup
    step = 240  # continues from where seeding left off (so checkout-svc keeps drifting)
    while True:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            new_samples: List[dict] = []
            for service in PREDICTIVE_SERVICES:
                for metric in METRIC_CRITICAL_THRESHOLDS.keys():
                    last = await db.metrics.find_one(
                        {"service_name": service, "metric_type": metric},
                        {"_id": 0, "value": 1}, sort=[("timestamp", -1)],
                    )
                    last_v = float(last["value"]) if last else None
                    v = _next_sample_value(service, metric, last_v, step)
                    new_samples.append(MetricSample(
                        service_name=service, metric_type=metric, value=v, timestamp=now_iso,
                    ).model_dump())
            if new_samples:
                await db.metrics.insert_many(new_samples)
            await PredictorService.run(org_id="default")
            step += 1
        except Exception as e:
            logger.exception("Periodic predictive run failed: %s", e)
        await asyncio.sleep(300)  # 5 minutes


@app.on_event("startup")
async def f02_startup():
    await _seed_metric_history()
    # Index for predictive_incidents
    try:
        await db.predictive_incidents.create_index([("org_id", 1), ("status", 1), ("risk_score", -1)])
    except Exception:
        pass
    global _predictive_task_started
    if not _predictive_task_started:
        _predictive_task_started = True
        asyncio.create_task(_periodic_predictive_run())
        # Also do an initial run immediately so the dashboard isn't empty on first load
        asyncio.create_task(PredictorService.run(org_id="default"))
        logger.info("F-02 Predictive Triage started (5-min cadence)")


# ====================================================================================================
# END F-02
# ====================================================================================================


# ====================================================================================================
# SonarQube Integration - Code Quality Metrics
# ====================================================================================================
# Mock SonarQube endpoints for code quality analysis
# To connect to real SonarQube: Set SONARQUBE_URL and SONAR_TOKEN in .env
# ====================================================================================================

SONAR_ALLOWED_STATUSES = ["OPEN", "CLAIMED", "IN_PROGRESS", "FIXED", "WONT_FIX"]
# Severity → simplified bucket (mirrors frontend lib/severity.js)
SONAR_SEVERITY_BUCKET = {
    "BLOCKER":  "HIGH",
    "CRITICAL": "HIGH",
    "MAJOR":    "MEDIUM",
    "MINOR":    "LOW",
    "INFO":     "LOW",
}

# In-memory mutable state for mocked SonarQube issues (assignee + status overrides).
# Keyed by issue key. Resets on backend restart — sufficient for the mock workflow.
_SQ_ISSUE_STATE: dict = {}


def _create_mock_sonarqube_issues():
    """Helper function to create mock SonarQube issue data."""
    return [
        {
            "key": "AYxyz123",
            "type": "CODE_SMELL",
            "severity": "MINOR",
            "component": "frontend/src/components/IncidentChat.jsx",
            "line": 45,
            "message": "Consider extracting this conditional into a separate function",
            "title": "Refactor nested conditional in IncidentChat",
            "description": (
                "The render branch at line 45 contains a deeply nested ternary that mixes "
                "loading, error and empty states. Extract the branching into a small helper "
                "component or function to improve readability and lower cognitive complexity."
            ),
            "rule": "javascript:S3358 — Ternary operators should not be nested",
            "suggestedFix": (
                "Replace the nested ternary with an early-return helper, e.g.\n"
                "function renderBody(state) {\n"
                "  if (state.loading) return <Spinner />;\n"
                "  if (state.error)   return <ErrorBanner msg={state.error} />;\n"
                "  if (!state.items.length) return <EmptyState />;\n"
                "  return <MessageList items={state.items} />;\n"
                "}"
            ),
            "effort": "10min",
            "status": "OPEN",
            "assignee": None,
            "creationDate": "2025-07-15T09:20:00+0000",
            "tags": ["complexity"],
        },
        {
            "key": "AYxyz124",
            "type": "CODE_SMELL",
            "severity": "MINOR",
            "component": "backend/server.py",
            "line": 892,
            "message": "Function has too many return statements (6 > 5)",
            "title": "Reduce return statements in resolve_alerts",
            "description": (
                "`resolve_alerts` has 6 explicit return paths which makes the control flow "
                "hard to reason about. Consolidate the validation branches at the top and "
                "have a single happy-path return at the end."
            ),
            "rule": "python:S1142 — Functions should not contain too many return statements",
            "suggestedFix": (
                "Collect validation errors first and raise once, then return a single response.\n"
                "Example: build an `errors = []` list, raise HTTPException(400, errors) if any, "
                "and return the result dict at the end."
            ),
            "effort": "15min",
            "status": "OPEN",
            "assignee": None,
            "creationDate": "2025-07-15T09:20:00+0000",
            "tags": ["complexity"],
        },
        {
            "key": "AYxyz125",
            "type": "CODE_SMELL",
            "severity": "INFO",
            "component": "frontend/src/components/TriagePanel.jsx",
            "line": 128,
            "message": "Consider using a more descriptive variable name",
            "title": "Rename ambiguous variable `d` in TriagePanel",
            "description": (
                "Single-letter variable `d` at line 128 obscures intent. Use a descriptive "
                "name such as `deployment` or `diagnostic` to make the code self-documenting."
            ),
            "rule": "javascript:S117 — Local variables should comply with a naming convention",
            "suggestedFix": "Rename `d` → `deployment` throughout the function scope.",
            "effort": "5min",
            "status": "OPEN",
            "assignee": None,
            "creationDate": "2025-07-15T09:20:00+0000",
            "tags": ["convention"],
        },
        {
            "key": "AYxyz126",
            "type": "BUG",
            "severity": "MAJOR",
            "component": "backend/server.py",
            "line": 456,
            "message": "Null pointer dereference may occur here",
            "title": "Potential None dereference on incident.assignee",
            "description": (
                "`incident.assignee` is read without a None check after a Mongo lookup that "
                "may return a document missing the `assignee` key (e.g. freshly created "
                "incidents). Accessing `.lower()` on None will raise AttributeError at runtime."
            ),
            "rule": "python:S5713 — Null pointers should not be dereferenced",
            "suggestedFix": (
                "Guard the access:\n"
                "assignee = (incident.get('assignee') or '').lower()\n"
                "if not assignee:\n"
                "    raise HTTPException(409, 'Incident is unassigned')"
            ),
            "effort": "20min",
            "status": "OPEN",
            "assignee": None,
            "creationDate": "2025-07-14T15:30:00+0000",
            "tags": ["bug"],
        },
    ]


def _apply_sq_state(issue: dict) -> dict:
    """Merge in-memory mutable state (assignee/status) onto a base mock issue."""
    state = _SQ_ISSUE_STATE.get(issue["key"])
    if state:
        return {**issue, **state}
    return issue


def _get_sq_issue_or_404(issue_key: str) -> dict:
    for base in _create_mock_sonarqube_issues():
        if base["key"] == issue_key:
            return _apply_sq_state(base)
    raise HTTPException(404, f"SonarQube issue '{issue_key}' not found")


def _create_sonarqube_breakdown():
    """Helper function to create issues breakdown"""
    return {
        "breakdown": {
            "bugs": 1,
            "vulnerabilities": 0,
            "codeSmells": 3,
            "securityHotspots": 0
        },
        "severityBreakdown": {
            "BLOCKER": 0,
            "CRITICAL": 0,
            "MAJOR": 1,
            "MINOR": 2,
            "INFO": 1
        }
    }


@api_router.get("/sonarqube/summary")
async def get_sonarqube_summary():
    """
    Get SonarQube project summary with overall metrics
    Returns code quality metrics for TriageAI codebase
    """
    return {
        "projectKey": "triageai",
        "projectName": "TriageAI Platform",
        "version": "2.0.0",
        "analysisDate": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "bugs": {
                "value": 1,
                "rating": "A"
            },
            "vulnerabilities": {
                "value": 0,
                "rating": "A"
            },
            "codeSmells": {
                "value": 3,
                "rating": "A"
            },
            "coverage": {
                "value": 78.5,
                "percentage": "78.5%"
            },
            "duplications": {
                "value": 2.1,
                "percentage": "2.1%"
            },
            "lines": {
                "value": 5847,
                "linesOfCode": 5847
            },
            "sqaleRating": {
                "value": "A",
                "debtRatio": 0.5
            },
            "reliabilityRating": "A",
            "securityRating": "A",
            "securityHotspots": 0
        },
        "qualityGateStatus": "PASSED"
    }


@api_router.get("/sonarqube/issues")
async def get_sonarqube_issues(
    severity: Optional[str] = None,   # exact: BLOCKER/CRITICAL/MAJOR/MINOR/INFO
    bucket: Optional[str] = None,     # simplified: HIGH/MEDIUM/LOW
    type: Optional[str] = Query(None, alias="type"),  # BUG/VULNERABILITY/CODE_SMELL/SECURITY_HOTSPOT
    status: Optional[str] = None,     # OPEN/CLAIMED/IN_PROGRESS/FIXED/WONT_FIX
    assignee: Optional[str] = None,   # "unassigned" or an email
    q: Optional[str] = None,          # free-text search across title/message/component/rule
):
    """
    Get SonarQube code-quality issues with optional filters.

    All filter args are optional and combine with AND. The response also includes a
    breakdown (by type + severity bucket) and total technical-debt minutes so the
    dashboard can render the summary bar in a single round-trip.
    """
    base = [_apply_sq_state(i) for i in _create_mock_sonarqube_issues()]

    def keep(it: dict) -> bool:
        if severity and (it.get("severity") or "").upper() != severity.upper():
            return False
        if bucket:
            b = SONAR_SEVERITY_BUCKET.get((it.get("severity") or "").upper(), "LOW")
            if b != bucket.upper():
                return False
        if type and (it.get("type") or "").upper() != type.upper():
            return False
        if status and (it.get("status") or "").upper() != status.upper():
            return False
        if assignee:
            a = (it.get("assignee") or "").lower()
            if assignee.lower() == "unassigned":
                if a:
                    return False
            elif a != assignee.lower():
                return False
        if q:
            needle = q.lower()
            hay = " ".join([
                str(it.get("title") or ""),
                str(it.get("message") or ""),
                str(it.get("component") or ""),
                str(it.get("rule") or ""),
                str(it.get("description") or ""),
            ]).lower()
            if needle not in hay:
                return False
        return True

    filtered = [it for it in base if keep(it)]

    # Breakdown is computed on the *unfiltered* base so the dashboard summary
    # always reflects the whole project, independent of active filters.
    breakdown_data = _create_sonarqube_breakdown()
    total_debt_minutes = sum(_parse_effort_minutes(i.get("effort")) for i in base)

    # Per-bucket counts (BLOCKER is special-cased and surfaced separately).
    bucket_counts = {"BLOCKER": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for it in base:
        sev = (it.get("severity") or "").upper()
        if sev == "BLOCKER":
            bucket_counts["BLOCKER"] += 1
        elif sev == "CRITICAL":
            bucket_counts["HIGH"] += 1
        elif sev == "MAJOR":
            bucket_counts["MEDIUM"] += 1
        else:  # MINOR / INFO
            bucket_counts["LOW"] += 1

    return {
        "total": len(filtered),
        "total_unfiltered": len(base),
        "issues": filtered,
        "buckets": bucket_counts,
        "technical_debt_minutes": total_debt_minutes,
        **breakdown_data,
    }


@api_router.get("/sonarqube/issues/{issue_key}")
async def get_sonarqube_issue_detail(
    issue_key: str,
    current_user: dict = Depends(get_current_user),
):
    """Return full detail for a single SonarQube issue (with current assignment/status)."""
    return _get_sq_issue_or_404(issue_key)


class SonarAssignBody(BaseModel):
    email: str


class SonarStatusBody(BaseModel):
    status: str


@api_router.post("/sonarqube/issues/{issue_key}/claim")
async def claim_sonarqube_issue(
    issue_key: str,
    current_user: dict = Depends(get_current_user),
):
    """Current user claims the issue → assignee = self, status = CLAIMED."""
    _get_sq_issue_or_404(issue_key)  # validates existence
    _SQ_ISSUE_STATE.setdefault(issue_key, {})
    _SQ_ISSUE_STATE[issue_key]["assignee"] = current_user["email"]
    _SQ_ISSUE_STATE[issue_key]["status"] = "CLAIMED"
    return _get_sq_issue_or_404(issue_key)


@api_router.post("/sonarqube/issues/{issue_key}/assign")
async def assign_sonarqube_issue(
    issue_key: str,
    body: SonarAssignBody,
    current_user: dict = Depends(get_current_user),
):
    """Assign issue to another user by email."""
    _get_sq_issue_or_404(issue_key)
    target = await db.users.find_one({"email": body.email}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(404, f"User '{body.email}' not found")
    _SQ_ISSUE_STATE.setdefault(issue_key, {})
    _SQ_ISSUE_STATE[issue_key]["assignee"] = body.email
    # If issue is still OPEN, bump it to CLAIMED on assignment.
    if _get_sq_issue_or_404(issue_key).get("status") == "OPEN":
        _SQ_ISSUE_STATE[issue_key]["status"] = "CLAIMED"
    return _get_sq_issue_or_404(issue_key)


@api_router.patch("/sonarqube/issues/{issue_key}/status")
async def update_sonarqube_issue_status(
    issue_key: str,
    body: SonarStatusBody,
    current_user: dict = Depends(get_current_user),
):
    """Update issue status. Allowed: OPEN, CLAIMED, IN_PROGRESS, FIXED."""
    new_status = body.status.upper().strip()
    if new_status not in SONAR_ALLOWED_STATUSES:
        raise HTTPException(
            400,
            f"Invalid status '{body.status}'. Allowed: {', '.join(SONAR_ALLOWED_STATUSES)}",
        )
    _get_sq_issue_or_404(issue_key)
    _SQ_ISSUE_STATE.setdefault(issue_key, {})
    _SQ_ISSUE_STATE[issue_key]["status"] = new_status
    # Resetting to OPEN clears assignee for clarity.
    if new_status == "OPEN":
        _SQ_ISSUE_STATE[issue_key]["assignee"] = None
    return _get_sq_issue_or_404(issue_key)


@api_router.get("/sonarqube/quality-gate")
async def get_sonarqube_quality_gate():
    """
    Get SonarQube quality gate status with conditions
    Returns quality gate evaluation for TriageAI
    """
    return {
        "projectKey": "triageai",
        "qualityGate": {
            "name": "TriageAI Quality Standards",
            "status": "PASSED"
        },
        "conditions": [
            {
                "metric": "new_reliability_rating",
                "operator": "GREATER_THAN",
                "threshold": "1",
                "status": "PASSED",
                "actualValue": "1.0"
            },
            {
                "metric": "new_security_rating",
                "operator": "GREATER_THAN",
                "threshold": "1",
                "status": "PASSED",
                "actualValue": "1.0"
            },
            {
                "metric": "new_maintainability_rating",
                "operator": "GREATER_THAN",
                "threshold": "1",
                "status": "PASSED",
                "actualValue": "1.0"
            },
            {
                "metric": "new_coverage",
                "operator": "LESS_THAN",
                "threshold": "70",
                "status": "PASSED",
                "actualValue": "78.5"
            },
            {
                "metric": "new_duplicated_lines_density",
                "operator": "GREATER_THAN",
                "threshold": "3",
                "status": "PASSED",
                "actualValue": "2.1"
            }
        ],
        "analysisDate": datetime.now(timezone.utc).isoformat()
    }


# ----------------------------------------------------------------------------------------------------
# F-02 — Helpers & extra endpoints for the enhanced Code Quality dashboard.
# ----------------------------------------------------------------------------------------------------

_EFFORT_RE = re.compile(r"(\d+)\s*([hm])", re.IGNORECASE)


def _parse_effort_minutes(effort: Optional[str]) -> int:
    """Turn '10min' / '1h' / '1h 30min' into total minutes. Returns 0 on parse failure."""
    if not effort:
        return 0
    total = 0
    for num, unit in _EFFORT_RE.findall(effort):
        n = int(num)
        total += n * 60 if unit.lower() == "h" else n
    return total


class SonarCommentIn(BaseModel):
    text: str


def _generate_mock_sonar_fix(issue: dict) -> dict:
    """
    Build a deterministic, synthetic unified-diff "fix" for a Sonar issue.

    This is a pure mock: we synthesize a plausible diff from `issue.suggestedFix`
    and the file/line that Sonar reported. The function returns the contract
    {explanation, unified_diff, confidence, safe_to_apply, language} so the
    frontend FixPreview modal can render side-by-side, and so a real LLM-backed
    implementation can later replace this body without changing the API shape.
    """
    component = issue.get("component", "path/to/file")
    line = int(issue.get("line") or 1)
    rule = issue.get("rule", "unknown")
    severity = (issue.get("severity") or "").upper()
    itype = (issue.get("type") or "CODE_SMELL").upper()
    suggested = (issue.get("suggestedFix") or "").rstrip()
    description = (issue.get("description") or issue.get("message") or "").strip()

    # Language inference for syntax-coloring hints on the frontend.
    ext = component.rsplit(".", 1)[-1].lower() if "." in component else ""
    lang = {
        "py": "python", "js": "javascript", "jsx": "javascript",
        "ts": "typescript", "tsx": "typescript", "java": "java",
        "go": "go", "rs": "rust", "rb": "ruby",
    }.get(ext, "text")

    # Confidence model: presence of a Sonar suggestedFix is the strongest signal,
    # then the issue type, then severity. Bounded to [0.30, 0.92].
    base = 0.55
    if suggested:
        base += 0.25
    if itype == "CODE_SMELL":
        base += 0.10
    elif itype == "BUG":
        base += 0.05
    elif itype == "VULNERABILITY":
        base -= 0.05
    if severity in ("BLOCKER", "CRITICAL"):
        base -= 0.05
    confidence = max(0.30, min(0.92, round(base, 2)))

    # `safe_to_apply` gates the one-click Apply CTA on the FE. We err conservative:
    # never auto-mark security findings safe.
    safe_to_apply = confidence >= 0.70 and itype not in ("VULNERABILITY", "SECURITY_HOTSPOT")

    # Synthesize a unified diff. We don't have the original source, so we use a
    # short placeholder "before" block and the suggestedFix as the "after" block.
    before_lines = (description.splitlines() or ["// existing implementation"])[:3]
    after_lines = suggested.splitlines() or ["// (no prebuilt fix available — see explanation)"]
    hunk_start = max(1, line - 1)
    hunk_len_before = len(before_lines)
    hunk_len_after = len(after_lines)

    diff_lines = [
        f"--- a/{component}",
        f"+++ b/{component}",
        f"@@ -{hunk_start},{hunk_len_before} +{hunk_start},{hunk_len_after} @@",
    ]
    for bl in before_lines:
        diff_lines.append(f"-{bl}")
    for al in after_lines:
        diff_lines.append(f"+{al}")
    unified_diff = "\n".join(diff_lines)

    explanation = (
        f"**Why this fix?**\n\n"
        f"`{rule}` flagged `{component}:{line}` as a {itype.replace('_', ' ').lower()} "
        f"({severity.lower() or 'unranked'} severity). "
        f"The recommended change applies SonarQube's prebuilt remediation to "
        f"eliminate the rule violation with minimal blast radius.\n\n"
        f"**What the patch does**\n"
        f"- Replaces the flagged block at line {line} with the suggested implementation.\n"
        f"- Preserves surrounding behaviour and exported API.\n"
        f"- Mirrors patterns used elsewhere in the codebase.\n\n"
        f"**Before merging**\n"
        f"1. Run unit tests covering `{component.split('/')[-1]}`.\n"
        f"2. Re-run SonarQube analysis to confirm `{rule}` is cleared.\n"
        f"3. Add a regression test if this is a BUG-class finding."
    )

    return {
        "explanation": explanation,
        "unified_diff": unified_diff,
        "confidence": confidence,
        "safe_to_apply": safe_to_apply,
        "language": lang,
        "issue_key": issue.get("key"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "mock",  # swap to "claude" / "gpt" when wired to real LLM
    }


@api_router.post("/sonarqube/issues/{issue_key}/generate-fix")
async def generate_sonar_fix(
    issue_key: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Generate an AI-assisted fix proposal for a Sonar issue.

    Returns a contract designed for the FixPreview modal:
        { explanation, unified_diff, confidence (0..1), safe_to_apply, language }

    Implementation is currently mocked deterministically from `issue.suggestedFix`;
    the `source` field is set to "mock" so the UI can flag it. Swap the body of
    `_generate_mock_sonar_fix` to an LlmChat call to upgrade to a real model.
    """
    issue = _get_sq_issue_or_404(issue_key)
    return _generate_mock_sonar_fix(issue)


@api_router.get("/sonarqube/issues/{issue_key}/comments")
async def list_sonar_comments(
    issue_key: str,
    current_user: dict = Depends(get_current_user),
):
    """List comments on a SonarQube issue, oldest first."""
    _get_sq_issue_or_404(issue_key)  # 404 if unknown
    docs = await db.sonarqube_comments.find(
        {"issue_key": issue_key}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    return {"issue_key": issue_key, "comments": docs}


@api_router.post("/sonarqube/issues/{issue_key}/comments")
async def add_sonar_comment(
    issue_key: str,
    body: SonarCommentIn,
    current_user: dict = Depends(get_current_user),
):
    """Append a comment to a SonarQube issue."""
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "text must not be empty")
    _get_sq_issue_or_404(issue_key)

    doc = {
        "id": str(uuid.uuid4()),
        "issue_key": issue_key,
        "author_email": current_user["email"],
        "author_name": current_user.get("name") or current_user["email"],
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.sonarqube_comments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/sonarqube/trend")
async def get_sonarqube_trend(days: int = Query(7, ge=1, le=30)):
    """
    Return a daily trend series for the project's main quality counters, for the
    requested number of days (default 7). Pure deterministic mock so the dashboard
    sparkline has stable, plausible data across reloads.
    """
    # Seed by date so the curve is stable per-day.
    today = datetime.now(timezone.utc).date()
    bugs_base, vuln_base, smells_base = 1, 0, 3
    series = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        seed = sum(ord(c) for c in d.isoformat()) % 7
        series.append({
            "date": d.isoformat(),
            "bugs": max(0, bugs_base + (seed % 3) - 1),
            "vulnerabilities": max(0, vuln_base + (seed % 2)),
            "code_smells": max(0, smells_base + ((seed * 3) % 4) - 1),
            "total": 0,  # filled below
        })
    for row in series:
        row["total"] = row["bugs"] + row["vulnerabilities"] + row["code_smells"]
    return {"days": days, "series": series}


@api_router.get("/sonarqube/config")
async def get_sonarqube_config(current_user: dict = Depends(get_current_user)):
    """
    Report whether the backend is wired to a real SonarQube server or running on
    mocks. The frontend uses this to render a small badge on the dashboard.

    To go live, set SONAR_BASE_URL (and optionally SONAR_TOKEN, SONAR_PROJECT_KEY)
    in backend/.env — the data layer can then branch on `source == "live"`.
    """
    base_url = os.environ.get("SONAR_BASE_URL", "").strip()
    project_key = os.environ.get("SONAR_PROJECT_KEY", "triageai").strip() or "triageai"
    has_token = bool(os.environ.get("SONAR_TOKEN", "").strip())
    return {
        "source": "live" if base_url and has_token else "mock",
        "base_url": base_url or None,
        "project_key": project_key,
        "has_token": has_token,
    }


# ====================================================================================================
# END SonarQube Integration
# ====================================================================================================


# ====================================================================================================
# SonarQube AI Remediation Assistant (Mocked)
# ----------------------------------------------------------------------------------------------------
# Architecture: keep the response generator (`_mock_sonar_ai_reply`) isolated behind a single
# async function so a real LLM call (e.g. emergentintegrations.LlmChat) can be swapped in later
# without touching the route or the frontend.
# ====================================================================================================

SONAR_AI_INTENTS = [
    # New canonical 5 (used by the enhanced quick-action chips):
    "explain_rule",
    "generate_fix",
    "alternative_fix",
    "write_test",
    "pr_description",
    # Back-compat: original 5 still accepted so persisted chats keep working.
    "explain",
    "suggest_fix",
    "refactor",
    "severity",
    "best_practices",
]

# Aliases route NEW canonical intents onto the existing back-compat branches so
# we don't duplicate the longer text bodies. Old codes render their own branches.
_SONAR_INTENT_ALIAS = {
    "explain_rule":    "explain",
    "generate_fix":    "suggest_fix",
    "alternative_fix": "refactor",
    # `write_test` and `pr_description` have dedicated branches (handled above).
    # `severity` and `best_practices` keep their own branches.
}


class SonarChatPrompt(BaseModel):
    text: str
    intent: Optional[str] = None  # one of SONAR_AI_INTENTS; falls back to keyword routing


def _detect_intent(text: str) -> str:
    """Crude keyword router used when caller doesn't pass an explicit intent."""
    t = (text or "").lower()
    if any(k in t for k in ["rule", "why is this flagged", "what does this rule", "rule mean"]):
        return "explain_rule"
    if any(k in t for k in ["alternative", "another way", "different approach", "other option"]):
        return "alternative_fix"
    if any(k in t for k in ["test", "unit test", "spec", "coverage"]):
        return "write_test"
    if any(k in t for k in ["pr description", "pull request", "commit message", "changelog"]):
        return "pr_description"
    if any(k in t for k in ["fix", "patch", "solution", "how do i fix", "remedy"]):
        return "generate_fix"
    if any(k in t for k in ["why", "explain", "what is", "what's this", "what does"]):
        return "explain_rule"
    if any(k in t for k in ["refactor", "restructure", "rewrite", "clean up"]):
        return "alternative_fix"
    if any(k in t for k in ["severity", "priority", "how bad", "impact"]):
        return "severity"
    if any(k in t for k in ["best practice", "guideline", "convention", "standard"]):
        return "pr_description"
    return "explain_rule"


def _mock_sonar_ai_reply(issue: dict, intent: str, user_text: str) -> str:
    """
    Produce a deterministic, context-aware mocked reply for a SonarQube issue.

    Each intent composes a short multi-section answer using the issue's real fields
    (rule, severity, component, suggestedFix, description). When swapping to a real
    LLM, replace this function's body with an LlmChat call and keep the signature.
    """
    if intent not in SONAR_AI_INTENTS:
        intent = _detect_intent(user_text)

    title = issue.get("title") or issue.get("message", "this issue")
    rule = issue.get("rule", "unknown rule")
    component = issue.get("component", "unknown file")
    line = issue.get("line")
    severity = issue.get("severity", "INFO")
    itype = issue.get("type", "CODE_SMELL").replace("_", " ").title()
    description = issue.get("description") or issue.get("message", "")
    suggested = issue.get("suggestedFix") or "No prebuilt fix available."
    location = f"{component}" + (f":{line}" if line else "")

    # New canonical intent branches (priority order). The original 5 are still
    # handled below for back-compat with persisted chats.

    if intent == "write_test":
        fname = (component.rsplit("/", 1)[-1] or "module").rsplit(".", 1)[0]
        return (
            f"**Regression test for `{rule}`**\n\n"
            f"Target: `{location}`\n\n"
            f"Before applying the fix, capture the *current* behaviour so any future "
            f"regression on this rule fails fast in CI:\n\n"
            f"```\n"
            f"// {fname}.test  — verifies the refactor preserves observable behaviour\n"
            f"describe('{fname} — {rule}', () => {{\n"
            f"  it('produces the same output for representative inputs', () => {{\n"
            f"    // arrange: build the minimal input that triggers the flagged branch\n"
            f"    // act:     call the function/component under test\n"
            f"    // assert:  compare output to a snapshot captured BEFORE the fix\n"
            f"  }});\n"
            f"  it('handles the edge case the rule warns about', () => {{\n"
            f"    // e.g. nested-state input that previously hit the deep ternary\n"
            f"  }});\n"
            f"}});\n"
            f"```\n\n"
            f"Pin this test to the PR that applies the fix so reviewers can see green-on-fix."
        )

    if intent == "pr_description":
        eff = issue.get("effort") or "low"
        return (
            f"**PR description draft**\n\n"
            f"### Fix `{rule}` in `{component}`\n\n"
            f"**Why**\n"
            f"SonarQube flagged this as a **{itype}** ({severity}). "
            f"{description.splitlines()[0] if description else 'See attached issue.'}\n\n"
            f"**What changed**\n"
            f"- Refactored `{component}`"
            f"{' around line ' + str(line) if line else ''} to apply the suggested remediation.\n"
            f"- Added a regression test mirroring the rule's failure mode.\n"
            f"- No public API changes; behaviour preserved.\n\n"
            f"**How to verify**\n"
            f"1. `yarn test` — new test should pass.\n"
            f"2. Re-run SonarQube analysis — `{rule}` should no longer surface this file.\n"
            f"3. Spot-check the diff in the FixPreview modal before merge.\n\n"
            f"**Effort**: ~{eff} · **Risk**: low · **Type**: tech-debt"
        )

    # Alias new canonical intents onto the existing back-compat branches so we
    # don't duplicate the longer texts:
    #   explain_rule    -> "explain"
    #   generate_fix    -> "suggest_fix"
    #   alternative_fix -> "refactor"
    intent_for_branch = _SONAR_INTENT_ALIAS.get(intent, intent)

    if intent_for_branch == "explain":
        return (
            f"**{title}**\n\n"
            f"This is a **{itype}** flagged by `{rule}` at `{location}`.\n\n"
            f"What it means:\n{description}\n\n"
            f"In plain terms: SonarQube detected a pattern that does not violate the runtime "
            f"behaviour today but reduces maintainability or hides a latent defect. Addressing "
            f"it early keeps the codebase healthy and prevents the issue from compounding."
        )

    if intent_for_branch == "suggest_fix":
        return (
            f"**Suggested fix for {title}**\n\n"
            f"Target: `{location}`\n"
            f"Rule: `{rule}`\n\n"
            f"Recommended change:\n```\n{suggested}\n```\n"
            f"Validation steps:\n"
            f"1. Apply the change locally.\n"
            f"2. Run the project linter / unit tests covering this module.\n"
            f"3. Re-run SonarQube analysis (or the mocked dashboard) and confirm this key disappears.\n"
            f"4. Open a small focused PR — one rule per PR keeps review easy."
        )

    if intent_for_branch == "refactor":
        return (
            f"**Alternative approach**\n\n"
            f"Beyond the minimal fix, consider these structural alternatives around `{location}`:\n\n"
            f"- Extract the affected logic into a small, testable helper with a descriptive name.\n"
            f"- Add a unit test that captures the original behaviour BEFORE refactoring.\n"
            f"- Prefer early-return / guard clauses over deeply nested branches.\n"
            f"- If the same pattern appears in sibling files, batch the change to avoid drift.\n\n"
            f"Cost estimate: ~{issue.get('effort', 'low')} of focused work. "
            f"Tag the PR `tech-debt` so it is visible in your weekly review."
        )

    if intent_for_branch == "severity":
        sev_map = {
            "BLOCKER": "Blocks release — must be fixed before merging to main.",
            "CRITICAL": "High likelihood of production impact — schedule within the current sprint.",
            "MAJOR": "Real defect or significant smell — plan within the next 1–2 sprints.",
            "MINOR": "Quality/maintainability concern — pick up opportunistically.",
            "INFO": "Informational — fix when touching nearby code.",
        }
        return (
            f"**Severity: {severity}**\n\n"
            f"Type: {itype}\n"
            f"What `{severity}` means for this codebase:\n{sev_map.get(severity, '—')}\n\n"
            f"For this specific issue (`{rule}` at `{location}`), the practical impact is that the "
            f"surrounding code will become progressively harder to change. There is no immediate "
            f"runtime risk, but each unrelated change in this file pays a small readability tax "
            f"until the issue is resolved."
        )

    if intent_for_branch == "best_practices":
        return (
            f"**Best-practice guidance**\n\n"
            f"Rule context: `{rule}`\n\n"
            f"Principles to keep in mind:\n"
            f"- Keep functions small and single-purpose (≤ ~20 lines is a good ceiling).\n"
            f"- Prefer named, intention-revealing variables over abbreviations.\n"
            f"- Treat lint and SonarQube findings as design feedback, not noise.\n"
            f"- Add a regression test whenever you fix a BUG-class finding so it cannot return.\n"
            f"- When you cannot fix immediately, mark the issue **CLAIMED** and link the PR ID "
            f"in your team's tracker so progress is visible.\n\n"
            f"Applying these for `{location}` will compound across the codebase — small, "
            f"consistent improvements outperform occasional big rewrites."
        )

    return f"_(no mocked reply for intent '{intent}')_"


@api_router.get("/sonarqube/issues/{issue_key}/chat")
async def get_sonar_issue_chat(
    issue_key: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the chat history for the given SonarQube issue."""
    _get_sq_issue_or_404(issue_key)  # validates existence
    chat = await db.sonarqube_chats.find_one({"issue_key": issue_key}, {"_id": 0})
    return chat or {"issue_key": issue_key, "messages": []}


@api_router.post("/sonarqube/issues/{issue_key}/chat")
async def post_sonar_issue_chat(
    issue_key: str,
    body: SonarChatPrompt,
    current_user: dict = Depends(get_current_user),
):
    """
    Append a user message and produce a mocked AI assistant reply for the given issue.
    Intents: explain / suggest_fix / refactor / severity / best_practices.
    """
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "text must not be empty")

    issue = _get_sq_issue_or_404(issue_key)
    intent = body.intent if body.intent in SONAR_AI_INTENTS else _detect_intent(text)

    chat_doc = await db.sonarqube_chats.find_one({"issue_key": issue_key}, {"_id": 0})
    messages = chat_doc["messages"] if chat_doc else []

    user_msg = ChatMsg(role="user", text=text, user_email=current_user["email"])
    messages.append(user_msg.model_dump())

    reply_text = _mock_sonar_ai_reply(issue, intent, text)
    asst_msg = ChatMsg(role="assistant", text=reply_text)
    # Attach intent metadata on the assistant message for the UI (and future analytics).
    asst_payload = {**asst_msg.model_dump(), "intent": intent}
    messages.append(asst_payload)

    await db.sonarqube_chats.update_one(
        {"issue_key": issue_key},
        {"$set": {
            "issue_key": issue_key,
            "messages": messages,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"user_message": user_msg.model_dump(), "assistant_message": asst_payload}


# ====================================================================================================
# END SonarQube AI Remediation Assistant
# ====================================================================================================


# ====================================================================================================
# Code Quality v2 — GitHub URL scans, .zip uploads, external scanner integrations (Claude-powered)
# ====================================================================================================
from code_quality_v2 import build_router as build_code_quality_v2_router  # noqa: E402

api_router.include_router(build_code_quality_v2_router(db, get_current_user))

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


# ====================================================================================================
# Static frontend (production / all-in-one container)
# When `frontend_build/` exists next to /backend (created at Docker build time),
# we serve the React SPA from the same FastAPI process. In local dev this
# directory does not exist, so the block is a no-op.
# ====================================================================================================
from pathlib import Path  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend_build"

if _FRONTEND_DIR.is_dir() and (_FRONTEND_DIR / "index.html").exists():
    _STATIC_DIR = _FRONTEND_DIR / "static"
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="frontend-static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_spa(full_path: str):
        # `/api/*` is registered above this catch-all and wins via FastAPI's
        # ordering, but guard against shadowing edge cases.
        if full_path.startswith("api/") or full_path.startswith("api"):
            raise StarletteHTTPException(status_code=404)
        candidate = _FRONTEND_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIR / "index.html"))

    logger.info("Serving static frontend from %s", _FRONTEND_DIR)
else:
    logger.info("No frontend_build/ found — running in API-only / dev mode.")
