# MEDTRACK (patient-registry)

A Django + PostgreSQL MVP for **case-based follow-up tracking**.

## What this build supports

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
- Built-in automatic scheduling runs while the web app is running; host-level scheduled commands are still a stronger option for unattended infrastructure.

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

## Updating to latest version safely (with backup)

Good news: the Postgres DB already persists in Docker volume `postgres_data`, so container rebuild/restart will not erase your patient data by default.

There are now two backup paths:

- `./scripts/backup.sh`: full Postgres + config backup for disaster recovery and upgrade safety
- `python manage.py backup_patient_data`: patient-data bundle backup for regular operational snapshots

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

This remains the recommended full-environment disaster-recovery backup.

### 2) Pull latest and rebuild

```bash
git pull
docker compose up -d --build
```

If the VPS uses a private `docker-compose.override.yml`, `git pull` leaves that file untouched because it is untracked and server-local.

### 3) Apply migrations

```bash
docker compose exec web python manage.py migrate
```

### 4) If something goes wrong, restore backup

```bash
./scripts/restore.sh backups/<timestamp>
```

Then restart app:

```bash
docker compose up -d
```

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
- The built-in app scheduler creates separate daily, monthly, and yearly archive bundles; the management command creates manual bundles and prunes only other manual bundles.
- Use the patient-data bundle flow for routine restores of patient records, and keep `scripts/backup.sh` / `scripts/restore.sh` for full-environment recovery.

## Useful commands

```bash
docker compose exec web python manage.py test
docker compose exec web python manage.py createsuperuser
docker compose exec -T web python manage.py backup_patient_data --keep 30
docker compose down
```
