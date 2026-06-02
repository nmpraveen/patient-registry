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

Local Codex setup on this machine:
- The checked-out `main` branch should stay aligned with GitHub. A few extra local-only helper files are intentionally present in this working copy and should remain local-only unless the user explicitly asks to push them.
- When the user says `push to GitHub`, do not push directly to `main` by default. Create a feature branch with the `codex/` prefix, push that branch, and open a pull request unless the user explicitly says to push directly to `main`.
- Direct-to-`main` pushes are allowed only when the user explicitly asks for that workflow in the current task.
- Local-only files intentionally restored here: `package.json`, `package-lock.json`, `patients/management/commands/ensure_local_demo_superuser.py`, `local-dev/TEST_NNH_SERVER.md`, `local-dev/test-nnh-up.ps1`, and `local-dev/test-nnh-web-start.sh`.
- Purpose of those local-only files: improve Playwright reliability for Codex in this repo and keep the local Test NNH server able to recreate the demo superuser with username `admin` and password `pass`.
- Local generated directories such as `.venv/`, `node_modules/`, and `staticfiles/` are also intentional and should not be treated as repo changes.
- Do not ask to recreate or remove this local-only setup unless the user explicitly wants that. If needed, the preserved local-only snapshot branch is `local/dev-tools`.

Local Test NNH server:
- Prefer the local-only Test NNH server at `http://localhost:8000` for demos and quick verification.
- Read `local-dev/TEST_NNH_SERVER.md` before changing local server behavior.
- From the repo root, use `.\local-dev\test-nnh-up.ps1` to start or reuse it, `.\local-dev\test-nnh-status.ps1` to inspect it, and `.\local-dev\test-nnh-stop.ps1` to stop it.
- Use `.\local-dev\test-nnh-health.ps1` for read-only local health checks: port `8000`, Compose state, `/api/schema/`, and Local Server Dashboard discovery.
- Log in with username `admin` and password `pass`.
- Before starting a local server, check whether the intended port is free with `Get-NetTCPConnection -State Listen -LocalPort <port> -ErrorAction SilentlyContinue`.
- After starting or reusing the server, verify that the Local Server Dashboard sees it at `http://127.0.0.1:3899/api/snapshot` when practical.
- Do not spin up a separate demo server or reinstall dependencies unless `requirements.txt` or `Dockerfile` changed and the image needs rebuilding.
- Do not leave hidden server processes running at the end of a task unless the user asked to keep them running or the server is the requested deliverable.

Android emulator workflow:
- For quick manual Android starts, prefer the healthy `MarkUS_Local` AVD before trying `MarkUS_Latest_API37`.
- Keep the Android debug API base URL at `http://10.0.2.2:8000/` for emulator runs against Test NNH.
- If `MarkUS_Latest_API37` is attached in `adb devices` but screenshots are black, `dumpsys activity users` shows `RUNNING_LOCKED`, or SystemUI/NotificationShade remains focused, stop troubleshooting the APK and switch to `MarkUS_Local`.
- If `adb shell am start ...MainActivity` says the activity does not exist, confirm with `adb shell dumpsys package com.naveenhospital.medtrack`; when the package declares `.MainActivity`, treat the launch failure as an emulator lock/profile state issue, not a build issue.
- After login, the first-run secure unlock screen is expected. Set the smoke-test pattern using top-left, top-middle, top-right, then middle-right dots; deny the Android notification permission prompt unless notification behavior is the task.

Implementation:
- Prefer existing patterns over new abstractions.
- Keep diffs small and scoped to the requested feature.
- Do not silently change core workflows (case creation, task generation, role checks) without stating the behavior change.
- Any newly introduced color or theme token must also be added to the Theme settings page (`/patients/settings/theme/`) so it can be modified later. Create a new category only for genuinely new UI elements; otherwise add it to the existing relevant category.
- Any new function or workflow that creates or updates patient data must also include corresponding `seed_mock_data` support so seeded environments populate the new data and do not leave blank values.
- If your change modifies user-visible behavior or shipped code, update the `VERSION` file only when that change set is being pushed to GitHub. Set it to the current UTC timestamp in `year.month.day.hours.min` format (example: `2026.03.03.17.38`).
- For each such push, prepend a matching section to the top of `CHANGELOG.md` using that version header and concise bullet-pointed summary notes for the changes included in that GitHub update.

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

## Documentation Upkeep

At the end of any substantial implementation, explicitly ask Codex to update `PROJECT_STATE.md`, `RUNBOOK.md`, and `ROADMAP.md` so status, commands, generated outputs, risks, and next actions stay current.
