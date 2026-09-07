# ROADMAP.md

## Issue #113 staged program

- The related full web-edit lock-order correction supersedes 2168b74: verify the bounded Patient-before-Case change and fresh exact-head CI. Concurrent requests, stale identity/draft retention and audit regressions pass; no additional broad review or native build is required for this server-only correction.

- Latest Stage 1 corrections: signed rendered web-edit baseline and normalized ANC link visibility. Complete focused correction verification and fresh exact-head CI; keep later provisional stages separate until actual Stage 1 merged main is available.

- Final four ANC feedback corrections cover cache cancellation safety, loss/close consistency, seed round-trip validity and audited Case-only lock order. Finish targeted checks, then use fresh exact-head CI; no additional broad review is required.

- The six existing automated Stage 1 comments require a focused feedback recheck and fresh exact-head CI after the sync, workflow and pagination fixes. Earlier d2ab783 GO is superseded until those gates pass.

- Stage 1 review fixes: all four consolidated findings are implemented with 91 targeted regression checks passing. Await fresh exact-head CI and a focused fix/regression recheck before coordinator merge.

- Stage 1 source implementation: scoped dormant patient grouping, persistent ANC overdue/EDD-missing attention, explicit audited outcome and USG EDD correction, web/native/API and bundle compatibility. Await the Stage 1 PR's exact-head CI and coordinator review/merge. No production activation is implied.
- Stages 2–5 remain separate gated PRs: task editing/general calls; permanent MTNO; main screens/timeline; administrative modules. Start each implementation from its predecessor's merged main.
- Stage 1 behavior, reconciliation and rollback guidance: [docs/issue-113-stage-1.md](docs/issue-113-stage-1.md).

## September dependency maintenance

- Complete exact-head backend, container, and Android CI for PRs #107, #109, and #114 before merging.
- Preserve strict dependency verification and lock regeneration checks during upgrades.
- Android device acceptance, external signing, and production deployment remain separate release gates.

## Phase Status

| Phase | Status | Notes |
|---|---|---|
| Web MVP | Done | Django + Postgres app supports the core case-follow-up workflows, scoped server-side object authorization, hardened admin IAM, settings, demo data, and backup/import/export flows. |
| Local demo workflow | Done | Test NNH server runs at `http://localhost:8000` with `admin` / `pass` through the `local-dev` wrappers. |
| Mobile API | Done locally | DRF endpoints support Android auth, worklists, case detail, writes, notifications, and device registration. |
| Android v1 app | Done locally | Kotlin/Compose app, offline writes, notifications surface, local smoke scripts, and screenshot/style handoff evidence exist. |
| Android release readiness | In progress | API 36 flavors, packaging, account isolation, server contracts, and data-only opaque push handling are merged in source; external Firebase/device evidence, release signing, field tests, and final audit remain. |
| Production hardening | Website operational; overall NO-GO | Last verified live website commit remains `a5dff668`; GitHub `main` is `892a0c2`. Operations/recovery gates are source-reviewed on this branch but require PR merge and separately approved live installation/acceptance. |

## Near-Term Roadmap

0. Activate the build and CI containment baseline.
   - Merge the exact-head workflow and the application lanes required to make strict OpenAPI, Android unit/lint/release, and frontend no-overflow green.
   - Do not mark failing checks optional or weaken their commands to merge.
   - After all ten check names have run on `main`, use the read-only preflight and exact-SHA apply command in `.github/BRANCH_PROTECTION.md`.
   - Keep weekly Dependabot and supply-chain freshness runs enabled; review all lock/digest changes through PRs.

1. Operate and exercise the recovered production system.
   - Rotate the temporary VPS root credential and preserve the normal non-root admin path.
   - Add a host-level VPS snapshot so application backups are not the only recovery layer.
   - Review Drive/NAS timer health and bounded storage use, and investigate failures without automatically deleting NAS archives.
   - Repeat an off-production scratch restore at least monthly and after any backup-system change.
   - Install the supervised patient-backup timer and independent scratch-restore hook only after the operations/recovery PR is reviewed and live change approval is granted.
   - Keep the private `age` identity in at least two recoverable off-VPS locations and never place it on the VPS or NAS.
   - Treat `a5dff668b23c52e5a71431807a291573f9e0404c` as the last verified live website commit until rechecked; require a fresh encrypted receipt, reviewed migration-plan hash, tested rollback artifacts, all-service/TLS/authenticated-login acceptance, and exact deployment receipt before the next code deployment.

2. Continue the website-first Stage 7 cleanup.
   - Build role profiles and frontend behavior on the live created/assigned/call-queue/all object-scope boundary.
   - Review the completed frontend hardening branch for self-hosted assets, CSP/no-store headers, accessible forms/search/merge workflows, theme contrast checks, and responsive browser coverage before deployment.
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
   - Verify the server sends only data-only opaque event/type wake-up data; Android suppresses raw-FCM display, ignores untrusted title/body/patient/case/phone fields, and refetches after authentication.

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

- Provision Play App Signing/external upload-key secrets and run the documented signed `bundleProdForPlay` gate; never commit signing material.
- Operate recurring independent scratch-restore verification through the fail-closed hook after approved installation; keep the private age identity off the VPS and NAS.
- Design the permanent mobile worklist scope policy so elevated users can choose the operational queue intentionally instead of relying on the temporary `assigned_to=all` default.
- Keep the app scoped as case-based follow-up tracking, not a full EHR.
- Add new seed support whenever future workflows create or update patient data.
