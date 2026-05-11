from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
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
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, EmailStr

from emergentintegrations.llm.chat import LlmChat, UserMessage

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
    triggers: List[TriggerEvent] = Field(default_factory=lambda: ["incident_created", "sla_breach"])
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


@api_router.post("/triage", response_model=TriageResult)
async def run_triage(req: TriageRequest, current_user: dict = Depends(get_current_user)):
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

    return triage


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
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"chat-{incident_id}",
            system_message=sys_msg,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
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
