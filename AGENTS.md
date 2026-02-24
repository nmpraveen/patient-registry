# AGENTS.md

## WHY (what this repo is)
MEDTRACK is a Django + Postgres MVP for case-based follow-up tracking (ANC, Surgery, Non-surgical).
It is not an EHR.

## WHAT (stack + map)
- Django app with server-rendered templates
- Postgres via Docker Compose
- Primary domain code: `patients/` (models, forms, views, tests)
- UI templates: `templates/` (especially `templates/patients/`)

## HOW (how to work in this repo)
Before coding:
- Read `README.md` for the current run/test/backup workflow.
- Identify the exact files you will touch, then propose a short plan plus acceptance checks.
- Ask targeted questions if requirements affect permissions, PHI exposure, migrations, or data retention.

Implementation:
- Prefer existing patterns over new abstractions.
- Keep diffs small and scoped to the requested feature.
- Do not silently change core workflows (case creation, task generation, role checks) without stating the behavior change.

Verification (do not skip):
- If you changed models: run `python manage.py makemigrations` and `python manage.py migrate`, and commit migrations.
- Run tests: `docker compose exec web python manage.py test` (or app-specific tests if provided).
- If the change is user-facing, do a quick manual smoke check of the relevant pages.

Output expectations:
- Summarize changes, list commands run, and call out follow-ups or risks.

## Guardrails (always on)
- Never add real patient data to fixtures, screenshots, logs, or examples.
- Never commit secrets or `.env`.
- Enforce permissions server-side. UI hiding is not security.
- Do not add report ingestion or file uploads without an explicit design for storage, access control, retention, and audit logging.

## Pointers (read only if relevant)
- `README.md`: setup, demo data, backup/restore
- `patients/models.py`: Case, Task, RoleSetting, scheduling rules
- `patients/views.py` and `templates/patients/`: UI flows and permission enforcement
- `scripts/backup.sh` and `scripts/restore.sh`: upgrade safety workflow
