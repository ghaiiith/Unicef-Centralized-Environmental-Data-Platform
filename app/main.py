"""Organization-scoped environmental events API; DHIS2/Superset remain separate upstream systems."""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload
from openpyxl import Workbook

from .core import Category, Event, Transition, Attachment, Audit, Outbox, get_actor, get_db, require, audit, utcnow

app = FastAPI(title="Iraq Environmental Event Service", version="0.1.0", docs_url="/api/docs", redoc_url=None)


@app.middleware("http")
async def protective_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

SEVERITY = Literal["low", "medium", "high", "critical"]
DECISION = Literal["verified", "not_verified"]
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/srv/uploads"))
MAX_ATTACHMENT_BYTES = int(os.environ.get("MAX_ATTACHMENT_BYTES", "20971520"))


class EventInput(BaseModel):
    organization_id: str = Field(min_length=1, max_length=120)
    category_id: int = Field(gt=0)
    severity: SEVERITY
    occurred_at: datetime
    governorate: str = Field(min_length=1, max_length=120)
    district: str = Field(min_length=1, max_length=140)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    description: str = Field(min_length=10, max_length=10000)

    @field_validator("occurred_at")
    @classmethod
    def timezone_aware(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone offset")
        return value.astimezone(timezone.utc)


class CloseInput(BaseModel):
    decision: DECISION
    comment: str = Field(min_length=5, max_length=5000)


class CategoryInput(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,69}$")
    label_en: str = Field(min_length=2, max_length=160)
    label_ar: str = Field(min_length=2, max_length=160)


def visible(session: Session, actor: dict):
    return select(Event).where(Event.organization_id.in_(actor["orgs"]))


def event_or_404(session: Session, actor: dict, event_id: int) -> Event:
    event = session.scalar(visible(session, actor).where(Event.id == event_id).options(selectinload(Event.transitions), selectinload(Event.attachments), selectinload(Event.category)))
    if event is None:
        raise HTTPException(404, "Event not found")  # mask another organization's IDs
    return event


def present(event: Event) -> dict:
    return {
        "id": event.id, "event_number": event.event_number,
        "organization_id": event.organization_id, "reporter_sub": event.reporter_sub,
        "category_id": event.category_id, "category": event.category.label_en,
        "severity": event.severity, "occurred_at": event.occurred_at,
        "governorate": event.governorate, "district": event.district,
        "latitude": event.latitude, "longitude": event.longitude,
        "description": event.description, "status": event.status,
        "assigned_verifier": event.assigned_verifier, "close_comment": event.close_comment,
        "verified_at": event.verified_at, "created_at": event.created_at,
        "attachments": [{"id": a.id, "name": a.display_name, "size": a.size, "type": a.content_type} for a in event.attachments],
        "history": [{"from": t.from_status, "to": t.to_status, "actor": t.actor_sub, "at": t.happened_at, "comment": t.comment} for t in event.transitions],
    }


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready(session: Session = Depends(get_db)):
    session.execute(text("select 1"))
    return {"status": "ready"}


@app.get("/api/config")
def public_config():
    return {"issuer": os.getenv("OIDC_ISSUER", ""), "client_id": os.getenv("OIDC_BROWSER_CLIENT_ID", "environment-web")}


@app.get("/api/me")
def me(actor: dict = Depends(get_actor)):
    return {"sub": actor["sub"], "roles": sorted(actor["roles"]), "organizations": actor["orgs"]}


@app.get("/api/categories")
def categories(session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    return [{"id": c.id, "code": c.code, "label_en": c.label_en, "label_ar": c.label_ar} for c in session.scalars(select(Category).where(Category.active == True).order_by(Category.id))]


@app.post("/api/categories", status_code=201)
def add_category(payload: CategoryInput, session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    require(actor, "system_admin")
    if session.scalar(select(Category.id).where(Category.code == payload.code)):
        raise HTTPException(409, "Category already exists")
    category = Category(**payload.model_dump())
    session.add(category)
    session.flush()
    # Scope category audit to an explicitly granted organization.
    audit(session, actor, actor["orgs"][0], "category.create", "category", str(category.id))
    session.commit()
    return {"id": category.id}


@app.post("/api/events", status_code=201)
def create_event(payload: EventInput, session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    require(actor, "data_entry", "verifier", "system_admin")
    if payload.organization_id not in actor["orgs"]:
        raise HTTPException(403, "Organization not authorized")
    if not session.scalar(select(Category.id).where(Category.id == payload.category_id, Category.active == True)):
        raise HTTPException(422, "Unknown event category")
    event = Event(**payload.model_dump(), reporter_sub=actor["sub"], reporter_email=actor.get("email"),
                  event_number="ENV-" + uuid.uuid4().hex[:20].upper(), status="submitted")
    session.add(event)
    session.flush()
    session.add(Transition(event_id=event.id, actor_sub=actor["sub"], from_status=None, to_status="submitted"))
    audit(session, actor, event.organization_id, "event.create", "event", str(event.id))
    destination = os.getenv("VERIFIER_NOTIFICATION_EMAIL", "")
    if destination:
        session.add(Outbox(event_id=event.id, recipient=destination, subject=f"Environmental event {event.event_number} submitted", body=f"Event {event.event_number} awaits verification."))
    session.commit()
    return {"id": event.id, "event_number": event.event_number, "status": event.status}


@app.get("/api/events")
def list_events(limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), status: str | None = None,
                category_id: int | None = None, governorate: str | None = None, search: str | None = Query(None, max_length=100),
                session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    query = visible(session, actor)
    if status:
        query = query.where(Event.status == status)
    if category_id:
        query = query.where(Event.category_id == category_id)
    if governorate:
        query = query.where(Event.governorate == governorate)
    if search:
        escaped = search.replace("%", "\\%").replace("_", "\\_")
        query = query.where(Event.description.ilike(f"%{escaped}%", escape="\\"))
    count = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.scalars(query.options(selectinload(Event.category), selectinload(Event.transitions), selectinload(Event.attachments)).order_by(Event.created_at.desc(), Event.id.desc()).offset(offset).limit(limit)).all()
    return {"total": count, "items": [present(x) for x in items], "limit": limit, "offset": offset}


@app.get("/api/events/summary")
def summary(session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    rows = session.execute(select(Event.status, func.count(Event.id)).where(Event.organization_id.in_(actor["orgs"])).group_by(Event.status)).all()
    return {"total": sum(n for _, n in rows), "by_status": {status: n for status, n in rows}}


@app.get("/api/events/export.xlsx")
def export_events(session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    events = session.scalars(visible(session, actor).options(selectinload(Event.category)).order_by(Event.id).limit(10000)).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Events"
    ws.append(["Event #", "Organization", "Category", "Severity", "Status", "Governorate", "District", "Occurred (UTC)", "Description"])
    for e in events:
        values = [e.event_number, e.organization_id, e.category.label_en, e.severity, e.status, e.governorate, e.district, e.occurred_at.isoformat(), e.description]
        # Excel formula injection protection for values originating from users.
        ws.append(["'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v for v in values])
    data = BytesIO()
    wb.save(data)
    return Response(data.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=environment-events.xlsx", "Cache-Control": "no-store"})


@app.get("/api/events/geojson")
def geojson(session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    records = session.scalars(visible(session, actor).where(Event.latitude.is_not(None), Event.longitude.is_not(None)).order_by(Event.id.desc()).limit(1000)).all()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [e.longitude, e.latitude]}, "properties": {"id": e.id, "status": e.status, "severity": e.severity, "event_number": e.event_number}} for e in records]}


@app.get("/api/events/{event_id}")
def get_event(event_id: int, session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    return present(event_or_404(session, actor, event_id))


@app.post("/api/events/{event_id}/start-verification")
def start_verification(event_id: int, session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    require(actor, "verifier", "system_admin")
    event = event_or_404(session, actor, event_id)
    if event.status != "submitted":
        raise HTTPException(409, "Event is not awaiting verification")
    event.status = "under_verification"
    event.assigned_verifier = actor["sub"]
    session.add(Transition(event_id=event.id, actor_sub=actor["sub"], from_status="submitted", to_status=event.status))
    audit(session, actor, event.organization_id, "event.verification_start", "event", str(event.id))
    session.commit()
    return {"status": event.status, "assigned_verifier": event.assigned_verifier}


@app.post("/api/events/{event_id}/close")
def close_event(event_id: int, payload: CloseInput, session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    require(actor, "verifier", "system_admin")
    event = event_or_404(session, actor, event_id)
    if event.status != "under_verification":
        raise HTTPException(409, "Event must be under verification")
    if actor["sub"] != event.assigned_verifier and "system_admin" not in actor["roles"]:
        raise HTTPException(403, "Only assigned verifier may close")
    event.status = "closed_verified" if payload.decision == "verified" else "closed_not_verified"
    event.close_comment = payload.comment
    event.verified_at = utcnow()
    session.add(Transition(event_id=event.id, actor_sub=actor["sub"], from_status="under_verification", to_status=event.status, comment=payload.comment))
    audit(session, actor, event.organization_id, "event.close", "event", str(event.id))
    if event.reporter_email:
        session.add(Outbox(event_id=event.id, recipient=event.reporter_email, subject=f"Event {event.event_number} closed", body=f"Status: {event.status}\nVerifier comment: {event.close_comment}"))
    session.commit()
    return {"status": event.status, "verified_at": event.verified_at}


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


@app.post("/api/events/{event_id}/attachments", status_code=201)
async def upload_attachment(event_id: int, file: UploadFile = File(...), session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    require(actor, "data_entry", "verifier", "system_admin")
    event = event_or_404(session, actor, event_id)
    if "system_admin" not in actor["roles"] and actor["sub"] not in {event.reporter_sub, event.assigned_verifier}:
        raise HTTPException(403, "Only reporter or assigned verifier may attach evidence")
    if event.status.startswith("closed"):
        raise HTTPException(409, "Closed event cannot be modified")
    original = (file.filename or "evidence")[:250]
    if not original or any(ord(c) < 32 for c in original) or "/" in original or "\\" in original:
        raise HTTPException(422, "Invalid display filename")
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, "Attachment exceeds allowed size")
    kind = sniff(data)
    if kind is None or kind != file.content_type:
        raise HTTPException(415, "Only verified PDF, PNG and JPEG are accepted")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = uuid.uuid4().hex
    path = UPLOAD_DIR / key
    with path.open("xb") as out:
        out.write(data)
    try:
        item = Attachment(event_id=event.id, storage_key=key, display_name=original, content_type=kind, size=len(data), uploader_sub=actor["sub"])
        session.add(item)
        session.flush()
        audit(session, actor, event.organization_id, "event.attachment_add", "attachment", str(item.id))
        session.commit()
        return {"id": item.id, "name": item.display_name, "size": item.size}
    except Exception:
        session.rollback()
        path.unlink(missing_ok=True)
        raise


@app.get("/api/events/{event_id}/attachments/{attachment_id}")
def download_attachment(event_id: int, attachment_id: int, session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    event = event_or_404(session, actor, event_id)
    attachment = next((a for a in event.attachments if a.id == attachment_id), None)
    if attachment is None or not re.fullmatch(r"[0-9a-f]{32}", attachment.storage_key):
        raise HTTPException(404, "Attachment not found")
    path = UPLOAD_DIR / attachment.storage_key
    if not path.is_file():
        raise HTTPException(503, "Attachment storage unavailable")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.display_name, content_disposition_type="attachment", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@app.get("/api/audit")
def audit_records(limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_db), actor: dict = Depends(get_actor)):
    require(actor, "system_admin")
    records = session.scalars(select(Audit).where(Audit.organization_id.in_(actor["orgs"])).order_by(Audit.id.desc()).limit(limit)).all()
    return [{"id": a.id, "organization_id": a.organization_id, "actor": a.actor_sub, "action": a.action, "entity_id": a.entity_id, "at": a.at} for a in records]


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html", media_type="text/html")
