# Backup and restore — operational plan, not executed/accepted

**Status:** guidance only, not a backup implementation or validated restore drill. A production-ready retention key-management plan requires Ministry sign-off. In particular the ToR requires encrypted **daily** automated backups and a **demonstrated** restoration. No such job or test ran in this environment.

## Coverage

An actual recoverable environment must include: PostgreSQL event data; `uploads` volume; OIDC realm/users/roles/configuration **only if self-hosted and contractually owned**; DHIS2 database/config/filestore; Superset database/dashboard metadata and associated encrypted settings; SMTP/job scheduler configuration minus external credentials; TLS/reverse-proxy config; and documentation of decryption credentials held in a secure external key vault.

## Non-destructive rehearsal in isolated staging

1. Freeze a known synthetic test dataset and count events, transitions, evidence files and outbox rows.
2. Run an encrypted `pg_dump` as a least-privileged backup user (using a key from external secret management). Capture the separate evidence/upload volume in the same recovery point. Store archives encrypted with a key **not in the archive or repository**.
3. Copy both encrypted archives to an access-controlled off-host destination. Verify SHA-256 checksums and successful decryption in **new disposable infrastructure**, not the active environment.
4. Provision a brand-new PostgreSQL database and empty evidence volume; restore PostgreSQL dump into **that new database only** using `pg_restore`; restore evidence storage. Never restore over an active operational database.
5. Check database referential integrity, row counts, signed-in role-scoped access, attachment retrieval, audit history, events and reconciliation against snapshots. Then destroy the test environment and record the evidence.
6. Schedule and monitor daily jobs, error alerts, rotation and 12-month audit retention after approval. No RTO/RPO was confirmed in the signed ToR.

Do not confuse persistent Docker volumes with backups. Full deployment restore needs more than PostgreSQL alone.
