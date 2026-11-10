"""Fast unit/integration checks with SQLite substitute; PostgreSQL CI test still required."""
import os
import tempfile
from datetime import datetime, timezone
from io import BytesIO

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///" + tempfile.mktemp(suffix=".sqlite3")
os.environ["OIDC_ISSUER"] = "https://issuer.invalid/realms/environment"
os.environ["OIDC_AUDIENCE"] = "environment-api"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
os.environ["VERIFIER_NOTIFICATION_EMAIL"] = "verify@example.invalid"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.core import Base, Category, SessionLocal, engine, get_actor, Outbox
from app.main import app
from app.manage import CATEGORIES


def person(role, org="ministry-a", sub="user-1", email="u@example.invalid"):
    return {"sub": sub, "roles": {role}, "orgs": [org], "email": email}


@pytest.fixture(autouse=True)
def db_reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        for code, en, ar in CATEGORIES:
            db.add(Category(code=code, label_en=en, label_ar=ar))
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as api:
        yield api


def as_user(actor):
    app.dependency_overrides[get_actor] = lambda: actor


def payload(**changes):
    obj = {"organization_id": "ministry-a", "category_id": 1, "severity": "high", "occurred_at": datetime.now(timezone.utc).isoformat(), "governorate": "Baghdad", "district": "Karkh", "latitude": 33.31, "longitude": 44.35, "description": "Recorded field report of an environmental incident"}
    return obj | changes


def test_health_and_fail_closed_token(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.get("/api/events", headers={"Authorization": "Bearer bogus"}).status_code == 401
    assert client.get("/api/events").status_code == 401


def test_event_lifecycle_authorization_and_scope(client):
    as_user(person("data_entry"))
    created = client.post("/api/events", json=payload())
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    assert client.post(f"/api/events/{event_id}/close", json={"decision": "verified", "comment": "Verified facts"}).status_code == 403
    assert client.post("/api/events", json=payload(organization_id="ministry-b")).status_code == 403
    assert client.get("/api/events").json()["total"] == 1
    as_user(person("viewer", org="ministry-b"))
    assert client.get("/api/events").json()["total"] == 0
    assert client.get(f"/api/events/{event_id}").status_code == 404
    assert client.get("/api/events/export.xlsx").status_code == 200
    as_user(person("verifier", sub="ver-1"))
    assert client.post(f"/api/events/{event_id}/close", json={"decision": "verified", "comment": "verified"}).status_code == 409
    assert client.post(f"/api/events/{event_id}/start-verification").status_code == 200
    assert client.post(f"/api/events/{event_id}/start-verification").status_code == 409
    as_user(person("verifier", sub="ver-2"))
    assert client.post(f"/api/events/{event_id}/close", json={"decision": "verified", "comment": "Strong evidence"}).status_code == 403
    as_user(person("verifier", sub="ver-1"))
    assert client.post(f"/api/events/{event_id}/close", json={"decision": "verified", "comment": ""}).status_code == 422
    closed = client.post(f"/api/events/{event_id}/close", json={"decision": "not_verified", "comment": "Not confirmed"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed_not_verified"
    assert client.post(f"/api/events/{event_id}/close", json={"decision": "verified", "comment": "duplicate"}).status_code == 409
    item = client.get(f"/api/events/{event_id}").json()
    assert len(item["history"]) == 3
    assert item["history"][-1]["comment"] == "Not confirmed"
    with SessionLocal() as db:
        assert len(db.scalars(select(Outbox)).all()) == 2


def test_validation_roles_and_exports(client):
    as_user(person("viewer"))
    assert client.post("/api/events", json=payload()).status_code == 403
    assert client.post("/api/categories", json={"code": "foo", "label_en": "Foo", "label_ar": "فوو"}).status_code == 403
    as_user(person("data_entry"))
    assert client.post("/api/events", json=payload(occurred_at="2026-11-10T12:00:00")).status_code == 422
    assert client.post("/api/events", json=payload(latitude=101)).status_code == 422
    assert client.post("/api/events", json=payload(category_id=1000)).status_code == 422
    assert client.post("/api/events", json=payload(description="=HYPERLINK(\"http://evil.invalid\") malicious text")).status_code == 201
    from openpyxl import load_workbook
    exported = client.get("/api/events/export.xlsx")
    wb = load_workbook(BytesIO(exported.content))
    assert wb.active["I2"].value.startswith("'=HYPERLINK")
    assert client.get("/api/events/summary").json()["total"] == 1
    assert len(client.get("/api/events/geojson").json()["features"]) == 1


def test_attachment_is_secure_and_scoped(client):
    as_user(person("data_entry"))
    event_id = client.post("/api/events", json=payload()).json()["id"]
    f = {"file": ("evidence.png", b"\x89PNG\r\n\x1a\nmore bytes", "image/png")}
    created = client.post(f"/api/events/{event_id}/attachments", files=f)
    assert created.status_code == 201, created.text
    attachment_id = created.json()["id"]
    assert client.get(f"/api/events/{event_id}/attachments/{attachment_id}").content.startswith(b"\x89PNG")
    assert client.post(f"/api/events/{event_id}/attachments", files={"file": ("attack.exe", b"MZdanger", "application/pdf")}).status_code == 415
    assert client.post(f"/api/events/{event_id}/attachments", files={"file": ("../bad.png", b"\x89PNG\r\n\x1a\n", "image/png")}).status_code == 422
    as_user(person("viewer", org="ministry-b"))
    assert client.get(f"/api/events/{event_id}/attachments/{attachment_id}").status_code == 404


def test_admin_audit_and_custom_categories(client):
    as_user(person("system_admin"))
    assert client.post("/api/categories", json={"code": "chemical_spill", "label_en": "Chemical spill", "label_ar": "تسرب كيميائي"}).status_code == 201
    assert len(client.get("/api/categories").json()) == 12
    assert client.post("/api/categories", json={"code": "chemical_spill", "label_en": "Chemical spill", "label_ar": "تسرب كيميائي"}).status_code == 409
    assert client.get("/api/audit").json()[0]["action"] == "category.create"


def test_failed_notification_retry(client):
    from app.notifications import send_pending
    as_user(person("data_entry"))
    client.post("/api/events", json=payload())
    def broken(_):
        raise OSError("smtp secret should never appear in audit")
    assert send_pending(send=broken) == 0
    with SessionLocal() as db:
        out = db.scalar(select(Outbox))
        assert out.status == "failed" and out.error == "OSError" and out.attempts == 1
    assert send_pending(send=lambda _: None) == 1
    with SessionLocal() as db:
        assert db.scalar(select(Outbox)).status == "sent"
