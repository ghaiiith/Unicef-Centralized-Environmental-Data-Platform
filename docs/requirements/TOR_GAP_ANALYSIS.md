# UNICEF ToR — Requirements and gap analysis

**Authority:** signed 12-page Annex J, not the PowerPoint. Page numbers below refer to the printed ToR page numbers. All proposed clarifications require Ministry/UNICEF approval before becoming contractual commitments.

## Contract and acceptance ambiguities

1. **Payment schedules conflict.** Page 5 presents two deliverables: platform go-live/handover **Week 12 = 95%**, support period **Month 15 = 5%**. Page 8 presents a different three-step payment schedule: **UAT for MVP functional demo version Week 5 = 50%**, platform go-live/handover **Week 10 = 45%**, support period **Month 15 = 5%**. Do not represent either as the settled payment basis without written clarification.
2. **Duration discrepancy.** Page 1 defines **3 months implementation + 12 months technical support**, page 5 speaks of Week 12 go-live; page 8 instead provides a Week 10 payment milestone. Establish whether Week 10 is an intermediate go-live/acceptance or an erroneous milestone.
3. **Retention.** Page 8 states a **5% bank warranty equivalent** for 12 months after user acceptance and conditions for release, while also retaining the last **5% support payment until Month 15**. Confirm whether both mechanisms coexist, how they interact, and the precise release conditions.
4. **Form definitions.** Page 2 says configure *up to ten* forms, but Annex 1 on pp.10–12 contains **six sample sector forms**. Confirm four additional forms, exact authorized labels, indicator formulas, and controlled unit vocabulary at inception. No new forms are approved by implication.
5. **Target hosting and domain.** Page 5 assigns government infrastructure/network/domains/SSL to the Ministry; deployment specifics and security boundary must be supplied. Platform cannot be production certified until supplied.
6. **Historical migration.** Page 5 assigns historical Excel cleanup to the Ministry; agree exact sheets, approved date ranges, mapping, and reconciliation criteria. The current increment imports no historical files.
7. **Organization boundaries.** Page 3 requires department-level restrictions with MOEn consolidated visibility. The exact MOEn global-viewer identity claim and authorization policy must be formally confirmed. The current service deliberately enforces explicit organization membership for every user including administrators.
8. **Audit/deletion.** Page 3 requires audit of creation, modification/deletion, authentication, and workflows retained ≥12 months. The present event service records create/transition/upload/category changes; unified auth logging, centralized log retention and immutable storage are not yet implemented.
9. **Security/SSO.** Page 3 requires platform-managed password policy, lockout and admin MFA; government-directory SSO is a future architectural capability, not required live integration. An OIDC provider is proposed here but is not provisioned or acceptance-tested.
10. **Analytical reporting.** Page 3 needs four agreed templates in PDF + Excel and scheduled email distribution. Apache Superset's report export combinations require a real installation proof; do not claim completed.

## MVP boundary — what exists

- A real FastAPI/SQLAlchemy event service, explicit PostgreSQL-targeted schema, validation, organization-scoped access and event lifecycle.
- Access tokens require an external, correctly configured RS256 OIDC identity provider. **No identity provider is deployed in this commit.**
- A bilingual browser screen runs real REST operations, not static mock charts.
- GeoJSON events API exists, but **no interactive point map** has been built yet.
- Filesystem evidence storage and notification outbox exist; **no antivirus scanner and no scheduled sender** are provisioned.
- PostgreSQL Docker definition exists but could **not be started locally** because Docker is unavailable in the current execution environment.

## Critical remaining contract work

The core platform's dynamic form builder, six annex forms, version integrity, bulk Excel/CSV import, analytics dashboards, no-code dashboard editing, four signed-off reports, scheduled PDF/Excel delivery, OIDC deployment/account administration, audit retention, backup/restore drill, 20-concurrent-user load evidence, security scans, training assets, government hosting and 12-month support setup remain **open**. See `TRACEABILITY_MATRIX.md` and `docs/IMPLEMENTATION_STATUS.md`.
