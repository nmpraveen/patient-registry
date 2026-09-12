# MEDTRACK (patient-registry)

A Django + PostgreSQL MVP for **case-based follow-up tracking**.

> **Android is deprecated**
>
> Android is deprecated and is not an actively maintained release target. Issue #120 targets web and responsive mobile web. Native feature parity, emulator testing, and Android release acceptance are outside its scope. Shared server security and data-integrity guarantees remain supported.
>
> The `android/` directory and its history are retained. Server-side API authentication, authorization, idempotency and integrity tests remain supported and tested; deprecating the client does not deprecate the server's security boundary. See [.github/BRANCH_PROTECTION.md](.github/BRANCH_PROTECTION.md).

Permanent patient MTNO is assigned on save; hospital UHID is optional. Existing identifiers, merge aliases and recovery checkpoints remain traceable. See [Stage 3 identity and recovery](docs/issue-113-stage-3.md).

## What this build supports

- Visible full task editing with stale-edit conflict handling, and reasoned General patient calls on web/native. See [Stage 2 behavior and compatibility](docs/issue-113-stage-2.md).

- Scoped **Dormant patients**, **Overdue cases**, and **EDD review needed** views; unresolved past-EDD ANC stays overdue even with no open tasks.
- Explicit **ANC outcome / EDD correction** on web and native case detail. Corrections retain task dates; outcomes cancel only explicitly selected open tasks. See [Stage 1 workflow](docs/issue-113-stage-1.md).

- Login-based access and role-aware actions (Admin, Doctor, Nurse, Reception, Caller)
- Entry flow aligned to clinical pathways:
  - **ANC**: capture LMP/EDD, derive trimester, auto-create ANC checklist tasks
  - **Surgery**: choose **Planned surgery** vs **Surveillance**
  - **Medicine**: set review date/frequency and track follow-up tasks
- Case dashboard with Today / Upcoming / Overdue / Awaiting / Red / Grey views
- Case activity log with timestamp + user identity
- Admin settings page for role permissions, role assignment, and custom category configuration
- Admin database management page for patient-data export, import, and server-side backups
- Patient identity with **First Name + Last Name** (instead of single name-only listing)

## Quick start

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Local development uses:
- `docker-compose.yml` as the shared base config
- `docker-compose.dev.yml` as the tracked local-dev overlay that enables the source bind mount

If you keep a private local override file, add `-f docker-compose.override.yml` to explicit multi-file commands. The checked-in local-dev PowerShell wrappers do this automatically when that file exists.

For a private VPS, keep server-only Docker settings in an untracked `docker-compose.override.yml`. Docker Compose auto-loads that file for `up`, `exec`, `ps`, and `logs`, so host-specific settings stay off GitHub while commands like `update_medtrack` remain unchanged.

## Production deployment

Production uses the shared Compose file plus the tracked Caddy overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
./scripts/deploy-production.sh plan "$(git rev-parse HEAD)" \
  --backup-receipt /srv/medtrack/offsite-backups/state/latest-pre-deployment.receipt \
  --evidence-dir /srv/medtrack/deploy-evidence/<deployment-id>
```

Review the generated migration plan and its SHA-256 before running the separate `apply` phase documented in `RUNBOOK.md`. The deployment script refuses a different commit or modified tracked files, requires a fresh encrypted pre-deployment receipt, runs migrations only through a controlled one-shot service, creates and scratch-restores rollback artifacts, checks all services and both TLS paths, and requires an external authenticated-login smoke hook. Web container startup never runs migrations.

Create an untracked `.env` with fresh values. At minimum, production must set:

```dotenv
MEDTRACK_DOMAIN=book.naveenhospital.net
SECRET_KEY=<fresh-long-random-secret>
DEBUG=False
ALLOWED_HOSTS=book.naveenhospital.net,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://book.naveenhospital.net
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=False
SESSION_COOKIE_SECURE=True
SESSION_TIMEOUT_SECONDS=43200
SESSION_SAVE_EVERY_REQUEST=True
CSRF_COOKIE_SECURE=True
USE_X_FORWARDED_PROTO=True
WEBAUTHN_RP_ID=book.naveenhospital.net
WEBAUTHN_ALLOWED_ORIGINS=https://book.naveenhospital.net
FCM_ENABLED=False
POSTGRES_DB=patient_registry
POSTGRES_USER=patient_registry
POSTGRES_PASSWORD=<fresh-long-random-password>
POSTGRES_HOST=db
POSTGRES_PORT=5432
BACKUP_HOST_DIR=/srv/medtrack/backups
```

The web container runs as non-root UID/GID `10001:10001`. Create the selected
`BACKUP_HOST_DIR` with ownership/access for that identity before deployment;
the production deploy script verifies writability before starting the service.

The two session settings above implement a sliding 12-hour inactivity timeout: each authenticated request refreshes the session expiry. Staff should still log out manually on shared workstations.

Django is published only on `127.0.0.1:8000`; Caddy is the public entry point on ports 80 and 443 and obtains HTTPS automatically. PostgreSQL is not published to the host. Do not seed demo patients in production.

Create admin user:

```bash
docker compose exec web python manage.py createsuperuser
```

Open:
- `http://localhost:8000/login/`
- `http://localhost:8000/patients/`
- `http://localhost:8000/patients/settings/` (admin role/settings page)

## Device approval pilot

The login flow now supports an admin-approved device pilot for selected users:

- Admin page: `http://localhost:8000/patients/settings/device-access/`
- Pilot helper: clones `Staff` into `Staff Pilot`
- V1 targeting: selected users only, managed from Device Access settings

## Database management

Admins can manage patient-data bundles from:

- `http://localhost:8000/patients/settings/database/`

This page supports:

- Exporting a patient-data ZIP bundle
- Importing a patient-data ZIP bundle
- Writing a patient-data ZIP bundle to the server backup folder
- Configuring automatic backup schedules with status for the last and next backup of each schedule

Bundle format:

- `patient_data.json`: patient-related records only
- `manifest.json`: schema version, record counts, export metadata, and SHA-256 checksum

Important notes:

- These tools cover **patient data only**: cases, tasks, vitals, call logs, and activity logs.
- Users, roles, theme settings, device-approval settings, sessions, and other non-patient tables are not included in the bundle.
- Patient identity is keyed by **UHID**, not by patient name, so same-name patients remain separate.
- Import is destructive for patient data: it replaces all current patient-related records after creating a fresh safety backup.
- Automatic schedules support:
  - daily backups at a chosen time, retaining the most recent 30 daily bundles
  - monthly backups every 1st of the month at `12:00 AM`, retaining all monthly bundles
  - yearly backups every `Jan 1` at `12:00 AM`, retaining all yearly bundles
- The page shows the last backup and next backup timing for each schedule, plus the overall last backup status.
- Automatic scheduling is executed only by the supervised `medtrack-patient-backup-scheduler.timer`; Gunicorn workers and web requests do not own a scheduler.

For WebAuthn / passkeys outside localhost, configure these env vars and serve the app over HTTPS:

```bash
WEBAUTHN_RP_ID=your-hostname.example.org
WEBAUTHN_RP_NAME=MEDTRACK
WEBAUTHN_ALLOWED_ORIGINS=https://your-hostname.example.org
```

## Demo data (30 mock cases)

To quickly see the app with sample records:

```bash
docker compose exec web python manage.py seed_mock_data --count 30 --reset
```

- `--count` controls how many mock cases to create (default: `30`).
- `--reset` clears only previously seeded mock cases (and linked call/activity logs) before seeding.
- `--reset-all` clears all case/task/activity data before seeding and now requires confirmation.
- `--yes-reset-all` skips the interactive `--reset-all` confirmation prompt (required in non-interactive runs, e.g. UI/automation).
- The seed includes today, upcoming, overdue, awaiting-report, red-flag, quick-entry, call-log, notification, ANC, Surgery, and Medicine coverage for web UI demos.
- Demo staff users are created with password `pass`: `demo_admin`, `demo_doctor`, `demo_nurse`, `demo_caller`, and `demo_reception`. On the local Test NNH server, existing `admin` is used for the Admin queue instead.

## Updating to latest version safely (with backup)

Good news: the Postgres DB already persists in Docker volume `postgres_data`, so container rebuild/restart will not erase your patient data by default.

There are now four backup paths:

- `./scripts/backup.sh`: VPS-local Postgres + config backup for upgrade safety
- `python manage.py backup_patient_data`: patient-data bundle backup for regular operational snapshots
- `./scripts/backup-offsite.sh --tier <tier>`: full, encrypted Postgres + recovery-config archive uploaded off the VPS
- restricted Synology pull mirror: the NAS fetches only completed ciphertext triplets into an isolated archive; the VPS cannot push to or browse the NAS

### 1) Create backup before pull/update

```bash
./scripts/backup.sh
```

This backs up:
- PostgreSQL dump (`database.sql`)
- `.env`
- `docker-compose.yml`
- `docker-compose.dev.yml` if present
- `docker-compose.override.yml` if present
- current app commit hash

This is useful for a fast rollback, but it is not disaster recovery by itself because it remains on the VPS.

### 2) Pull latest and rebuild

```bash
git pull
docker compose up -d --build
```

If the VPS uses a private `docker-compose.override.yml`, `git pull` leaves that file untouched because it is untracked and server-local.

### 3) Apply migrations through a controlled one-shot job

```bash
docker compose --profile deploy run --rm migrate
```

For production, use the plan/apply deployment gate in `RUNBOOK.md`; do not run the one-shot migration manually.

### 4) Verify a full recovery backup

```bash
./scripts/restore.sh verify \
  --archive /absolute/path/medtrack-prod-<tier>-<timestamp>.tar.age \
  --checksum /absolute/path/medtrack-prod-<tier>-<timestamp>.tar.age.sha256 \
  --identity /offline/path/age-identity.txt \
  --expected-commit <full-git-sha> \
  --receipt-dir /absolute/path/restore-receipt
```

This is scratch-only by default. It verifies ciphertext and both manifests, validates the PostgreSQL catalog and recorded version/commit, restores into an isolated database, runs Django/migration/ORM/login checks, and removes decrypted scratch material. Production activation has a separate environment gate and confirmation token, creates and scratch-restores a fresh rollback snapshot, retains the rollback database, and supports the documented `rollback` mode.

## Data persistence notes

- Your DB is stored in Docker named volume `postgres_data` and survives container recreation.
- Do **not** run `docker compose down -v` unless you intentionally want to delete DB volume.
- Keep `.env` backed up; it contains runtime config and DB credentials.

## Periodic patient-data backups

For routine unattended backups, use a host-level scheduler to run the management command inside the web container and keep the latest 30 manual bundles.

Example command:

```bash
docker compose exec -T web python manage.py backup_patient_data --output-dir /app/backups --keep 30
```

Example cron entry on the Docker host:

```cron
0 2 * * * cd /path/to/patient-registry && docker compose exec -T web python manage.py backup_patient_data --output-dir /app/backups --keep 30
```

Notes:

- `/app/backups` maps to the repo `backups/` folder in this Docker setup.
- `backups/` is gitignored and should be treated as PHI-containing server storage.
- The supervised host timer runs `python manage.py run_due_patient_backups` once per minute to create due daily, monthly, and yearly bundles; the management command above creates manual bundles and prunes only other manual bundles.
- Use the patient-data bundle flow for routine restores of patient records. `scripts/backup.sh` remains a VPS-local upgrade snapshot only; full-environment recovery uses encrypted off-site triplets with the fail-closed `scripts/restore.sh` workflow above.

## Encrypted off-VPS recovery backups

Production disaster-recovery backups use `scripts/backup-offsite.sh`. Each run:

- creates and validates a PostgreSQL custom-format dump
- captures the production `.env`, Compose/Caddy recovery files, Git commit, and runtime versions
- stores a verified latest evidence segment/checkpoint in rapid, daily, and canary backups; weekly, monthly, and pre-deployment backups retain the complete evidence chain
- builds an internal SHA-256 manifest
- compresses the recovery payload before encryption so JSON/log evidence is not stored at raw size
- encrypts the entire archive with an `age` public key before any upload
- uploads a unique ciphertext, checksum, and completion marker through rclone
- verifies the uploaded objects before recording success
- prunes only files matching the exact MEDTRACK tier pattern; Google Drive removals go to Trash

The VPS stores only the public encryption recipient. The private `age` identity must remain off the VPS, with at least two recoverable copies. The Google OAuth token is restricted to the root-only rclone configuration and must never be committed.

Production retention separates the small VPS working set from the longer Drive history:

| Tier | Frequency | VPS-local | Google Drive | Evidence payload |
|---|---:|---:|---:|---|
| Rapid | Every 6 hours | 4 | 28 (7 days) | Latest verified checkpoint |
| Daily | Every day | 2 | 30 | Latest verified checkpoint |
| Weekly | Every Sunday | 2 | 12 | Complete retained chain |
| Monthly | First day of each month | 1 | 12 | Complete retained chain |
| Pre-deployment | Before a production deployment | 2 | 14 | Complete retained chain |
| Canary | After deployment/maintenance | 1 | 1 | Latest verified checkpoint |

The four scheduled tiers provide 82 completed recovery points after the retention windows fill. Pre-deployment backups are additional and capped at 14. See `RUNBOOK.md` for credential placement, canary, timer, health, and restore-check commands.

The live deployment also mirrors the bounded VPS-local completed set to Synology `Home/Backups/MEDTRACK`. A restricted SFTP-only VPS account exposes ciphertext read-only; a networked NAS fetcher can write only to an incoming quarantine, and a separate network-disabled promoter validates complete triplets before copying them into the protected archive. Expired, checksum-valid triplets are removed only from VPS export staging; the NAS archive never receives the private `age` identity and retains its independently promoted copies.

## Useful commands

```bash
docker compose exec web python manage.py test
docker compose exec web python manage.py createsuperuser
docker compose exec -T web python manage.py backup_patient_data --keep 30
docker compose down
```

The pinned Playwright Chromium regression matrix covers 320, 390, 430, and 1440 pixel viewports. With a local server running, configure `PLAYWRIGHT_BASE_URL`, `PLAYWRIGHT_USERNAME`, and `PLAYWRIGHT_PASSWORD`, then run `npm ci` and `npm run test:e2e`. See `local-dev/TEST_NNH_SERVER.md` for the Test NNH example; evidence is written under `output/playwright/`.

Authenticated-page third-party asset versions and licenses are recorded in `THIRD_PARTY_WEB_ASSETS.md`.
