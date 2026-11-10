# Technology evaluation — configuration first

**Decision status: preliminary; no running DHIS2, ODK Central, Superset, or Keycloak proof-of-concept in the current execution environment.** The signed ToR p.4 explicitly requires established open-source components integrated/configured rather than wholesale custom platform engineering. Versions and licenses must be checked again during inception.

| Capability | DHIS2 | ODK Central | Apache Superset | Status / evidence |
|---|---|---|---|---|
| Visual form setup, metadata | Native maintenance app + custom form editor | Requires external XLSForm authoring; Central itself not graphical form designer | Not a collection platform | DHIS2 documentation supports form sections/custom editor; empirical evaluation pending |
| Conditional fields and repeatable groups | Program rules and repeatable program stages, semantics must be evaluated | XLSForm conditions and repeats supported | Not applicable | Verify ToR's exact repeat semantics on a running instance |
| Published version preservation | Metadata history needs PoC for immutable semantics | Published XLSForm versions archived | Not applicable | ODK docs support archived published versions; inspect historic edits |
| Draft/submitted + evidence | DHIS2 Capture configurable (test needed) | Central drafts and web submissions (test needed) | Not applicable | No formal acceptance proof |
| Hierarchy and org-scoped access | Native organization units and roles | Project/form-level roles, cross-sector modelling needed | RLS requires explicit design | Test inherited rights before choosing a stack |
| Charts, no-code dashboard management | Native analytics dashboards | External analytics | Native dashboards and chart editor | Superset promising, PoC required |
| PDF, Excel, scheduled email | Additional integration likely | CSV/OData feeds | Alerts and reports require Celery, headless browser and mail settings | PDF and XLSX combinations to be tested |
| Read-only token datasets | DHIS2 API, scoped service accounts | REST/OData APIs | Separate secured reporting layer | Test token scope and deny-by-default behavior |
| Arabic and correct RTL | Localization supported; visual proof required | Multilingual forms; UI RTL proof required | Locale support but full RTL proof required | No screenshots/RTL acceptance tests yet |
| Event submit → verify → close with comment | May require configured workflow/extensions | Review features but exact ToR state machine needs validation | Not workflow engine | **Custom environmental event service increment implemented and tested in SQLite** |
| PostgreSQL | Required/native | Native storage | Native metadata DB option | Docker definition prepared for the event service, not operated |

## Preferred target architecture (subject to PoC)

1. **DHIS2** as candidate for data collection and indicators, with operator-configured sample forms, organizational units, validation, and built-in native APIs. If exact version preservation or repeatable groups fail fit-gap, compare ODK Central plus a verified graphical open-source builder rather than inventing a full custom form system.
2. **Apache Superset** for no-code analytics, reporting and scheduled report workflows, with tightly scoped read-only datasets and tested report/browser requirements.
3. **Existing open-source IdP / Keycloak candidate** for PKCE frontend login and server-verified RS256 JWTs. Administrator MFA, account lifecycle, lockout and OIDC client/audience/claim mapping must be established in the IdP. Current custom service refuses unconfigured identity.
4. **Custom event service** (this increment) only for the precise verification lifecycle/gap, organization-scoped event registry, evidence handling and notification outbox; PostgreSQL as storage. Future work must implement secure ingestion into analytics without replicating DHIS2 records.
5. **Government-operated reverse proxy/TLS, encrypted backups and runtime monitoring** to be designed with government hosting security policy.

## Evidence references (not a substitute for installed PoC)

- DHIS2 program configuration: https://docs.dhis2.org/en/use/user-guides/dhis-core-version-243/configuring-the-system/programs.html
- DHIS2 official Docker deployment (not yet installed): https://github.com/dhis2/docker-deployment
- ODK Central forms: https://docs.getodk.org/central-forms/
- ODK Web Forms limitations: https://docs.getodk.org/web-forms-intro/
- Superset embedded integration: https://superset.apache.org/user-docs/using-superset/embedding/
- Superset scheduled alerts/reports: https://github.com/apache/superset/blob/master/docs/admin_docs/configuration/alerts-reports.mdx

**Why no bespoke form builder here?** The ToR expressly prohibits wholly bespoke platform solutions; the current application intentionally implements only the event-workflow gap and leaves general data collection to a proven open-source product pending a live requirements proof.
