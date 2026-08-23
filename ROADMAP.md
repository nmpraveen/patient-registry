# ROADMAP.md

## Phase Status

| Phase | Status | Notes |
|---|---|---|
| Web MVP | Done | Django + Postgres app supports the core case-follow-up workflows, scoped server-side object authorization, hardened admin IAM, settings, demo data, and backup/import/export flows. |
| Local demo workflow | Done | Test NNH server runs at `http://localhost:8000` with `admin` / `pass` through the `local-dev` wrappers. |
| Mobile API | Done locally | DRF endpoints support Android auth, worklists, case detail, writes, notifications, and device registration. |
| Android v1 app | Done locally | Kotlin/Compose app, offline writes, notifications surface, local smoke scripts, and screenshot/style handoff evidence exist. |
| Android release readiness | In progress | Screenshot handoff is captured; Firebase delivery, create-case persistence, lock-flow routing, field-test evidence, release signing, and final v1 audit remain. |
| Production hardening | Website operational; overall NO-GO | Website/API P0 authorization and admin-IAM containment are live at `a5dff668`; HTTPS, encrypted Drive timers, isolated Synology mirror, and restore evidence are verified. Android account isolation/FCM PHI, credential rotation, and provider-console recovery remain follow-ups. |

## Near-Term Roadmap

1. Operate and exercise the recovered production system.
   - Rotate the temporary VPS root credential and preserve the normal non-root admin path.
   - Add a host-level VPS snapshot so application backups are not the only recovery layer.
   - Review Drive/NAS timer health and bounded storage use, and investigate failures without automatically deleting NAS archives.
   - Repeat an off-production scratch restore at least monthly and after any backup-system change.
   - Keep the private `age` identity in at least two recoverable off-VPS locations and never place it on the VPS or NAS.
   - Treat `a5dff668b23c52e5a71431807a291573f9e0404c` as the current live website commit and require a fresh pre-deployment backup before the next code deployment.

2. Continue the website-first Stage 7 cleanup.
   - Build role profiles and frontend behavior on the live created/assigned/call-queue/all object-scope boundary.
   - Keep forged-ID, archived-object, and reassignment-revocation tests as release gates.
   - Do not reintroduce plaintext credential notes into the application database or UI; credentials remain in the local Git-ignored ledger until rotation.

3. Review the Android screenshot handoff.
   - Current handoff: `output/android-claude-handoff-final-20260531-105420/CLAUDE_HANDOFF.md`.
   - Captured pages: login, home, filters, red-flag reasons, cases, case detail, vitals entry, notifications, alert detail, calls, dialer handoff, call outcome, profile, quick add, create case, and final home state.
   - Current style finding: no runtime-reachable MEDTRACK page in the handoff is clearly off-theme; the dialer handoff is an external Android OS surface.

4. Complete Firebase setup for MEDTRACK only after Android security blockers are fixed.
   - Add local-only `android/app/google-services.json`.
   - Configure host-only Firebase Admin SDK credentials.
   - Set `FCM_ENABLED=True`, `FCM_CREDENTIALS_FILE`, and project id if needed.
   - Run `.\android\scripts\mobile-push-preflight.ps1 -RequireReady`.

5. Decide Android create-case and lock-flow scope.
   - Current create-case wizard is a native mock/draft-style flow, not a persisted backend write.
   - First-run lock setup and unlock screens exist in source but were not runtime-reachable in the latest fresh-login handoff.
   - If either remains in v1 scope, wire the route and add matching seed/API support before final release audit.

6. Keep the temporary elevated mobile worklist behavior explicit.
   - Current behavior: Admin, Doctor, and Superuser/root mobile sessions default to `assigned_to=all` so they can see all visible cases.
   - Non-elevated case-data roles still default to assigned-to-me.
   - Later fix: replace the temporary elevated default with a deliberate worklist model, such as a role-configurable default scope, a persistent user filter preference, or separate "All visible" / "Assigned to me" queues that are clear in the UI.
   - Do not remove the explicit `assigned_to=all` behavior until that worklist model is designed and tested.

7. Prove real push delivery.
   - Run `.\android\scripts\mobile-real-push-smoke.ps1 -NoBuild`.
   - Confirm the app registers a real token and the device notification surface has evidence.

8. Record field readiness without PHI.
   - Run `.\android\scripts\field-test-record.ps1` after real push smoke passes and the app is installed on the intended test devices.
   - Include roles, device model, Android version, pass/fail flags, and issue summary only.

9. Close Android v1.
   - Run `.\android\scripts\medtrack-v1-audit.ps1`.
   - Treat the v1 release goal as complete only when the audit reports `goalComplete=true`.

## Later Work

- Decide whether the Android app needs a signed release build and distribution checklist.
- Add recurring independent scratch-restore verification after the first manual restore proof.
- Design the permanent mobile worklist scope policy so elevated users can choose the operational queue intentionally instead of relying on the temporary `assigned_to=all` default.
- Keep the app scoped as case-based follow-up tracking, not a full EHR.
- Add new seed support whenever future workflows create or update patient data.
