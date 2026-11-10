# Centralized Environmental Data Platform · Iraq

**Status: tested incremental implementation, NOT the complete UNICEF ToR platform and NOT production approved.**

Project beneficiary: Ministry of Environment — Republic of Iraq. Implementing contractor identity: **Advanced Solutions / الحلول المتقدمة**. The source document is UNICEF Iraq's 12-page institutional contractor ToR (Annex J), with requirements ordered above implementation suggestions.

This repository currently implements the **environmental event monitoring service**, a justified custom workflow gap designed to integrate with an established open-source collection/analytics platform. It does **not** yet deploy DHIS2, Apache Superset, an identity provider, scheduled national reports, or the six annex forms. The interface shows this limitation prominently. The full contract is approximately **12 implementation weeks plus 12 support months**; no claim of contractual acceptance is implied.

## Verified features (isolated SQLite tests)

- PostgreSQL-targeted SQLAlchemy event schema; reference categories; explicit database initialization.
- Event creation and strict `Submitted → Under Verification → Closed (Verified / Not Verified)` workflow, mandatory close comment, history and audit.
- RS256 OIDC access-token verification against configured issuer / JWKS / audience. Roles and explicit organization scope are enforced server-side; **no default global-admin bypass**.
- Event registry pagination, search and status filters; summary counts from persisted rows; GeoJSON points; Excel export guarded against formula injection.
- PDF/PNG/JPEG evidence uploads with magic-byte checks, size cap (default 20 MiB), generated keys, permission-checked download.
- Transactional email outbox and separate retryable SMTP sender; no plaintext credentials in source.
- Responsive English/Arabic event workflow screen with RTL, OIDC Authorization Code + PKCE, and **real API operations**.
- Six deterministic tests covering workflow, cross-organization access denial, validation, upload, export, audit and notification retries.

## Quick start (new, empty database only)

Prerequisites: Docker Compose, a real reachable OIDC provider such as Keycloak configured with a **public PKCE client** `environment-web`, audience `environment-api`, role claim (`realm_access.roles`) and organization claims (`org_id` or `org_ids`). Provision account/role policy, admin MFA and session controls in your identity provider. Production services require real credentials and HTTPS.

```bash
cp .env.example .env
# Edit all settings and choose a strong POSTGRES_PASSWORD.
docker compose up -d --build
# Safe only for a NEW empty database. Never rerun blindly against a production DB.
docker compose run --rm api python -m app.manage init
curl -fsS http://127.0.0.1:8088/health/ready
```

Browse `http://127.0.0.1:8088/`. Configure your OIDC provider to allow the browser redirect URI and origin; no implicit development identity, default administrator credentials, or authentication bypass exists. Keep port `8088` bound only to loopback, and place the application behind an approved HTTPS reverse proxy for nonlocal users. OIDC browser callback requires accessible issuer URL and browser CORS.

To exercise the API without browser login, obtain an access token from the configured provider and call `GET /api/me` with `Authorization: Bearer <token>`; OpenAPI documentation is at `/api/docs`.

Email notifications are recorded in the outbox in the same transaction as event submission/closure. Process the queue with a **separate secured scheduled job** that has SMTP credentials and access to the same PostgreSQL database:

```bash
# One scheduled batch; SMTP_HOST, SMTP_SENDER, SMTP_USERNAME,
# SMTP_PASSWORD, SMTP_PORT must be provided in the JOB environment.
python -m app.notifications
```

There is no default scheduler container in this increment. The verifier distribution address is configured by `VERIFIER_NOTIFICATION_EMAIL`. An event reporter's token `email` claim is used for closure mail. Never use this sample outbox in production without confirming mailbox ownership, retry policy and configured organization routing.

## Local tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app
```

These tests run on **SQLite solely to test application logic**, not PostgreSQL. A live PostgreSQL service, OIDC provider, SMTP server, browser E2E tests, 20-user load tests, backup-restoration drill, external security review and real government-hosting configuration have **not** been executed in this environment. A green unit test does not establish production readiness.

## Repository guide

- `app/core.py`: identity boundary and relational entities.
- `app/main.py`: scoped REST endpoints and policy enforcement.
- `app/notifications.py`: configurable SMTP outbox processor.
- `app/static/index.html`: bilingual workflow UI, built against the actual API.
- `tests/`: executable event service regression tests.
- `docs/requirements/`: ToR traceability matrix and gaps/discrepancies.
- `docs/architecture/`: configuration-first evaluation and integration plan.
- `docs/operations/`: backups, bootstrap, security and next steps.
- `docs/IMPLEMENTATION_STATUS.md`: explicit status and evidence.

**No production environment or client-owned data has been accessed or modified.** Do not label this repository as UNICEF-certified or a finished procurement deliverable.
