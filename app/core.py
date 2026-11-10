"""PostgreSQL persistence and identity boundary. No account passwords are held here."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session


def utcnow():
    return datetime.now(timezone.utc)


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured; implicit production database is forbidden")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "event_category"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(70), unique=True)
    label_en: Mapped[str] = mapped_column(String(160))
    label_ar: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(default=True)


class Event(Base):
    __tablename__ = "environmental_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    organization_id: Mapped[str] = mapped_column(String(120), index=True)
    reporter_sub: Mapped[str] = mapped_column(String(160))
    reporter_email: Mapped[str | None] = mapped_column(String(250))
    category_id: Mapped[int] = mapped_column(ForeignKey("event_category.id"))
    severity: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    governorate: Mapped[str] = mapped_column(String(120), index=True)
    district: Mapped[str] = mapped_column(String(140))
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="submitted", index=True)
    assigned_verifier: Mapped[str | None] = mapped_column(String(160))
    close_comment: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    category: Mapped[Category] = relationship()
    transitions: Mapped[list[Transition]] = relationship(back_populates="event", order_by="Transition.id")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="event")
    __table_args__ = (
        CheckConstraint("severity in ('low','medium','high','critical')", name="event_severity_valid"),
        CheckConstraint("status in ('submitted','under_verification','closed_verified','closed_not_verified')", name="event_status_valid"),
        Index("ix_event_scope_date", "organization_id", "occurred_at"),
    )


class Transition(Base):
    __tablename__ = "event_transition"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("environmental_event.id"), index=True)
    actor_sub: Mapped[str] = mapped_column(String(160))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text)
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event: Mapped[Event] = relationship(back_populates="transitions")


class Attachment(Base):
    __tablename__ = "event_attachment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("environmental_event.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(250))
    content_type: Mapped[str] = mapped_column(String(70))
    size: Mapped[int]
    uploader_sub: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event: Mapped[Event] = relationship(back_populates="attachments")


class Audit(Base):
    __tablename__ = "environment_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), index=True)
    actor_sub: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(70))
    entity_kind: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(70))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outbox(Base):
    __tablename__ = "notification_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("environmental_event.id"))
    recipient: Mapped[str] = mapped_column(String(250))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(350))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def get_db():
    with SessionLocal() as session:
        yield session


bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def jwks_client():
    uri = os.environ.get("OIDC_JWKS_URL")
    if not uri or not uri.startswith("https://") and os.environ.get("ALLOW_HTTP_OIDC") != "1":
        raise RuntimeError("OIDC_JWKS_URL requires HTTPS except explicit local development")
    return jwt.PyJWKClient(uri, timeout=5)


def get_actor(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    issuer = os.environ.get("OIDC_ISSUER")
    audience = os.environ.get("OIDC_AUDIENCE")
    if not issuer or not audience:
        raise HTTPException(503, "Identity provider is not configured")
    if credentials is None:
        raise HTTPException(401, "Bearer access token required", headers={"WWW-Authenticate": "Bearer"})
    try:
        key = jwks_client().get_signing_key_from_jwt(credentials.credentials).key
        claims = jwt.decode(credentials.credentials, key=key, algorithms=["RS256"], audience=audience, issuer=issuer, options={"require": ["exp", "iss", "aud", "sub"]})
    except (jwt.PyJWTError, jwt.PyJWKClientError, ValueError, RuntimeError):
        raise HTTPException(401, "Invalid or expired token") from None
    roles = set(claims.get("realm_access", {}).get("roles", [])) & {"system_admin", "data_entry", "verifier", "viewer"}
    orgs = claims.get("org_ids", [])
    if not isinstance(orgs, list) or not all(isinstance(v, str) and v.strip() for v in orgs):
        orgs = []
    if isinstance(claims.get("org_id"), str) and claims["org_id"].strip():
        orgs.append(claims["org_id"])
    orgs = sorted(set(orgs))
    if not roles or not orgs:
        raise HTTPException(403, "Role and organization claims required")
    # No global override for admins: all access must be explicitly scoped.
    return {"sub": claims["sub"], "email": claims.get("email"), "roles": roles, "orgs": orgs}


def require(actor: dict, *roles: str):
    if not actor["roles"].intersection(roles):
        raise HTTPException(403, "Insufficient role")


def audit(session: Session, actor: dict, organization_id: str, action: str, kind: str, entity_id: str):
    session.add(Audit(actor_sub=actor["sub"], organization_id=organization_id, action=action, entity_kind=kind, entity_id=entity_id))
