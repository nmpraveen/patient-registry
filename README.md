# MEDTRACK (patient-registry)

A Django + PostgreSQL MVP for **case-based follow-up tracking**.

## What this build supports

- Login-based access and role-aware actions (Admin, Doctor, Nurse, Reception, Caller)
- Entry flow aligned to clinical pathways:
  - **ANC**: capture LMP/EDD, derive trimester, auto-create ANC checklist tasks
  - **Surgery**: choose **Planned surgery** vs **Surveillance**
  - **Non-Surgical**: set review date/frequency and track follow-up tasks
- Case dashboard with Today / Upcoming / Overdue / Awaiting / Red / Grey views
- Case activity log with timestamp + user identity
- Admin settings page for role permissions, role assignment, and custom category configuration
- Patient identity with **First Name + Last Name** (instead of single name-only listing)

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

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

### 1) Create backup before pull/update

```bash
./scripts/backup.sh
```

This backs up:
- PostgreSQL dump (`database.sql`)
- `.env`
- `docker-compose.yml`
- current app commit hash

### 2) Pull latest and rebuild

```bash
git pull
docker compose up -d --build
```

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

## Useful commands

```bash
docker compose exec web python manage.py test
docker compose exec web python manage.py createsuperuser
docker compose down
```
