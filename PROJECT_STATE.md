# PROJECT_STATE.md

## Current Status

MEDTRACK is a runnable Django + Postgres case-follow-up MVP with a native Android companion app in the same repo.

The web app supports login-based role-aware workflows, case dashboards, case activity logs, configurable roles/categories/theme settings, patient-data import/export, server-side backup bundles, and seeded demo records.

The Android v1 implementation is locally implemented and has local verification evidence from the Test NNH workflow. The release goal is not complete until the external Firebase and physical-device gates pass.

## Last Verified Date

2026-05-31

Verified with the local Test NNH server on `http://localhost:8000`, `.\local-dev\test-nnh-health.ps1`, full Django tests, Android `:app:assembleDebug`, Android `testDebugUnitTest`, APK install on `emulator-5554` / `MarkUS_Local`, and the screenshot handoff package at `output/android-claude-handoff-final-20260531-105420/`.

## How To Run Locally

Preferred Codex/demo workflow:

```powershell
.\local-dev\test-nnh-up.ps1
.\local-dev\test-nnh-status.ps1
```

Open:

- `http://localhost:8000/login/`
- Username: `admin`
- Password: `pass`

Stop only when the task does not need the server kept running:

```powershell
.\local-dev\test-nnh-stop.ps1
```

The Test NNH workflow uses Docker Compose and a local-only Docker volume named `test_nnh_state` for the demo SQLite database. It runs migrations, recreates the local admin user, resets demo content, and reseeds mock data on start.

General Docker workflow from `README.md`:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
docker compose exec web python manage.py test
```

If `docker-compose.override.yml` exists locally, the local-dev PowerShell wrappers include it automatically.

## Current Phase

- Web MVP: operational and runnable locally.
- Android v1: locally implemented and locally smoke-tested.
- Release readiness: blocked on external Firebase delivery evidence, a physical Android phone smoke, and a two-user field-test record.

## Done

- Django server-rendered MEDTRACK app for case-based ANC, Surgery, and Medicine follow-up tracking.
- Role-aware login and role/action settings.
- Today, Upcoming, Overdue, Awaiting, Red, and Grey dashboard views.
- Activity logging with user/timestamp context.
- Patient-data ZIP export/import and server-side patient-data backups.
- Seeded demo data and demo users.
- Local Test NNH server workflow for repeatable Codex demos on `http://localhost:8000`.
- Android Kotlin/Compose app structure with `app`, `core`, and `feature` modules.
- Mobile DRF API surface for auth, case lists/details, writes, notifications, and device registration.
- Android offline write support for task completion, call outcome, and vitals writes.
- Android screenshot handoff for login, home, filters, red-flag reasons, cases, case detail, vitals entry, notifications, alert detail, calls, dialer handoff, call outcome, profile, quick add, create case, and final home state.
- Android alert detail, call outcome, and Custom Rehab visual surfaces are locally implemented for review.
- `MarkUS_Local` is the preferred AVD for quick manual Android start/login checks against Test NNH.
- Firebase/FCM integration boundary is implemented so missing Firebase config does not break normal local use.

## Not Done

- Native create-case currently remains a mock/draft-style flow and is not persisted through the backend API.
- First-run secure setup and unlock routing exist in source but were not reachable in the current fresh-login screenshot flow.
- Real Firebase push delivery is not proven for MEDTRACK until Firebase Android config, Django service-account config, and a real FCM token are supplied.
- Low-end or representative physical Android phone smoke is not complete.
- Two-user field-test record is not complete.
- Final Android v1 audit remains incomplete until `.\android\scripts\medtrack-v1-audit.ps1` reports `goalComplete=true`.

## Known Risks

- This is not an EHR; avoid expanding scope into broad EHR workflows without explicit design.
- Patient data and backups can contain PHI. Do not commit real patient data, backup bundles, screenshots, logs, FCM tokens, service-account JSON, or `.env`.
- Importing patient-data bundles is destructive for existing patient data after a safety backup.
- The Test NNH server is local/demo infrastructure and must not be treated as production.
- The current Test NNH listener can appear LAN-exposed through Docker port publishing; use `adb reverse` for physical-device local testing when possible.
- `MarkUS_Latest_API37` can appear attached while stuck behind a locked/black SystemUI state. For quick manual starts, switch to `MarkUS_Local` instead of debugging the APK.
- Firebase readiness depends on external console configuration and local secrets that are intentionally excluded from Git.

## Important Generated Outputs

- `backups/` - patient-data bundles and backup artifacts; treat as sensitive and gitignored.
- `staticfiles/` - collected Django static files.
- `output/` - Android/API smoke, audit, and field-test evidence when scripts are run.
- `output/android-claude-handoff-final-20260531-105420/` - current screenshot handoff for style and workflow review.
- `%USERPROFILE%\.codex\build\medtrack-android\app\outputs\apk\debug\app-debug.apk` - default debug APK output.
- `test_nnh_state` - Docker volume for the Test NNH demo SQLite database.

## Next 3 Actions

1. Review the current screenshot handoff in `output/android-claude-handoff-final-20260531-105420/CLAUDE_HANDOFF.md`.
2. Decide whether native create-case should persist to the backend now, and wire the first-run lock setup/unlock route if it remains part of the v1 scope.
3. Configure Firebase inputs, prove real push delivery, record the two-user field test, and rerun `.\android\scripts\medtrack-v1-audit.ps1`.
