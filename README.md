# MEDTRACK (patient-registry)

A Django + PostgreSQL MVP for **case-based follow-up tracking**. It is designed for clinical workflows where each case has time-bound tasks and teams need visibility into due/overdue work.

## Features

- Authenticated access (`/login/`, `/logout/`)
- Department-configured cases (`UHID`, patient details, metadata JSON)
- Task tracking per case (due date, status, assignee, type)
- Dashboard views for today, upcoming, overdue, awaiting reports, red/grey list counts
- Search and filters by UHID/phone/name, status, category, assignee, date range
- Case activity log with timestamped notes and user attribution
- Dockerized app + PostgreSQL

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Then migrate and create admin:

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Open `http://localhost:8000`.

## Key routes

- Dashboard: `/patients/`
- Case list: `/patients/cases/`
- New case: `/patients/cases/new/`
- Case detail: `/patients/cases/<id>/`

## Config

- `SESSION_TIMEOUT_SECONDS` (default `1800`)
- Standard Django/Postgres env vars from `.env.example`

## Tests

```bash
python manage.py test
```
