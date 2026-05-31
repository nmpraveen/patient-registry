# ROADMAP.md

## Phase Status

| Phase | Status | Notes |
|---|---|---|
| Web MVP | Done | Django + Postgres app supports the core case-follow-up workflows, role-aware access, settings, demo data, and backup/import/export flows. |
| Local demo workflow | Done | Test NNH server runs at `http://localhost:8000` with `admin` / `pass` through the `local-dev` wrappers. |
| Mobile API | Done locally | DRF endpoints support Android auth, worklists, case detail, writes, notifications, and device registration. |
| Android v1 app | Done locally | Kotlin/Compose app, offline writes, notifications surface, and local smoke scripts exist. |
| Android release readiness | In progress | Firebase is wired; release signing and final client handoff remain. Physical-device smoke is not a current blocking gate. |
| Production hardening | Ongoing | Continue backup discipline, PHI hygiene, permission checks, and controlled deployment verification. |

## Near-Term Roadmap

1. Complete Firebase setup for MEDTRACK.
   - Add local-only `android/app/google-services.json`.
   - Configure host-only Firebase Admin SDK credentials.
   - Set `FCM_ENABLED=True`, `FCM_CREDENTIALS_FILE`, and project id if needed.
   - Run `.\android\scripts\mobile-push-preflight.ps1 -RequireReady`.

2. Keep the temporary elevated mobile worklist behavior explicit.
   - Current behavior: Admin, Doctor, and Superuser/root mobile sessions default to `assigned_to=all` so they can see all visible cases.
   - Non-elevated case-data roles still default to assigned-to-me.
   - Later fix: replace the temporary elevated default with a deliberate worklist model, such as a role-configurable default scope, a persistent user filter preference, or separate "All visible" / "Assigned to me" queues that are clear in the UI.
   - Do not remove the explicit `assigned_to=all` behavior until that worklist model is designed and tested.

3. Prove real push delivery.
   - Run `.\android\scripts\mobile-real-push-smoke.ps1 -NoBuild`.
   - Confirm the app registers a real token and the device notification surface has evidence.

4. Record field readiness without PHI.
   - Run `.\android\scripts\field-test-record.ps1` after real push smoke passes and the app is installed on the intended test devices.
   - Include roles, device model, Android version, pass/fail flags, and issue summary only.

5. Close Android v1.
   - Run `.\android\scripts\medtrack-v1-audit.ps1`.
   - Treat the v1 release goal as complete only when the audit reports `goalComplete=true`.

## Later Work

- Decide whether the Android app needs a signed release build and distribution checklist.
- Document production Firebase/Caddy/Docker deployment steps only after the external gates are proven.
- Design the permanent mobile worklist scope policy so elevated users can choose the operational queue intentionally instead of relying on the temporary `assigned_to=all` default.
- Keep the app scoped as case-based follow-up tracking, not a full EHR.
- Add new seed support whenever future workflows create or update patient data.
