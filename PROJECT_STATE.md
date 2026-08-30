# PROJECT_STATE.md

## Current Status

MEDTRACK is a runnable Django + Postgres case-follow-up MVP with a native Android companion app in the same repo.

The web app supports login-based role-aware workflows, case dashboards, case activity logs, configurable roles/categories/theme settings, patient-data import/export, server-side backup bundles, and seeded demo records.

The Android v1 implementation is locally implemented and has local verification evidence from the Test NNH workflow. The release goal is not complete until the external Firebase and physical-device gates pass.

Production is deployed on the hardened VPS at commit `a5dff668b23c52e5a71431807a291573f9e0404c`: pinned Python/PostgreSQL/Caddy versions, loopback-only Django exposure, persistent host backup storage, health-gated startup, and exact-commit deployment. Website and API object authorization now enforce created, assigned, or current call-queue scope for restricted staff; Doctor/Admin retain full active-case scope. Non-superusers can no longer modify superusers or grant settings-admin access, and the plaintext temporary-password-note model/table/UI have been removed. Encrypted Google Drive backups and health timers are active, and a pull-only Synology ciphertext mirror provides an independent off-VPS copy.

## Last Verified Date

2026-08-30

The unreleased `codex/remediate-frontend-a11y` branch adds website-only frontend, privacy, and accessibility hardening on base commit `920357a58a69bd2e18ed03023a4273cd1493a066`. Focused Django/template regressions and the Playwright Chromium matrix pass at 320, 390, 430, and 1440 pixels with no console or request failures, horizontal document overflow, external asset requests, or browser-back PHI exposure. This branch is not deployed; the production commit recorded below is unchanged.

PR #95 was reviewed at exact head `4b591627d9fac0ff4ecff1230fc74162280c4e84` and merged/deployed as `a5dff668b23c52e5a71431807a291573f9e0404c`. Verification covered all 375 Django tests (2 skipped), migration drift and clean scratch migration, production migration state, healthy Compose services, origin-bypassed and public HTTPS, real administrator login, removal of the plaintext-note table/UI, and a rollback-only live forged-ID/revocation smoke with no persisted synthetic records. Immediately before deployment, encrypted pre-deployment backup `medtrack-prod-pre-deployment-20260823T174416Z.tar.age` passed Drive verification, NAS export, and off-site health checks.

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
- Production website deployment: deployed and healthy on the hardened VPS with the website/API P0 authorization and admin-IAM containment live.
- Android v1: locally implemented and locally smoke-tested.
- Release readiness: blocked on external Firebase delivery evidence, a physical Android phone smoke, and a two-user field-test record.

## Done

- Django server-rendered MEDTRACK app for case-based ANC, Surgery, and Medicine follow-up tracking.
- Role-aware login and role/action settings.
- Server-side object scope on website and API list/detail/mutation routes, including forged-ID and reassignment revocation coverage.
- Superuser/settings-role takeover containment and removal of plaintext temporary-password-note storage.
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
- Production Caddy/Docker deployment with exact-commit refusal, service healthchecks, secure loopback binding, and persistent `/app/backups` storage.
- Encrypted off-VPS recovery tooling with immutable upload names, post-upload verification, exact-pattern retention, four scheduled tiers, a pre-deployment tier, and freshness/retention health checks.
- Live encrypted canary `medtrack-prod-canary-20260811T165254Z.tar.age`, independently downloaded, checksum-verified, decrypted off VPS, restored into PostgreSQL 16.14, and validated by the exact deployed Django commit.
- Pull-only Synology mirror at `Home/Backups/MEDTRACK` with a read-only SFTP export, networked incoming-only fetcher, network-disabled archive promoter, hard space/transfer ceilings, and no automatic deletion.
- NAS-sourced restore proof for the same canary: external and internal checksums, PostgreSQL restore, exact-commit Django checks, ORM queries, and login HTTP 200 all passed; decrypted scratch material was removed.
- Unreleased website frontend hardening: locally pinned authenticated-page assets, nonce/hash CSP and browser headers, authenticated no-store caching, unique form IDs, labeled controls, combobox semantics, explicit merge review, theme contrast enforcement, responsive overflow fixes, and browser regressions.

## Not Done

- Native create-case currently remains a mock/draft-style flow and is not persisted through the backend API.
- First-run secure setup and unlock routing exist in source but were not reachable in the current fresh-login screenshot flow.
- Real Firebase push delivery is not proven for MEDTRACK until Firebase Android config, Django service-account config, and a real FCM token are supplied.
- Low-end or representative physical Android phone smoke is not complete.
- Two-user field-test record is not complete.
- Final Android v1 audit remains incomplete until `.\android\scripts\medtrack-v1-audit.ps1` reports `goalComplete=true`.
- Android account-scoped local storage/outbox isolation and PHI-free FCM payloads remain separate production blockers; they were intentionally outside PR #95.

## Known Risks

- This is not an EHR; avoid expanding scope into broad EHR workflows without explicit design.
- Patient data and backups can contain PHI. Do not commit real patient data, backup bundles, screenshots, logs, FCM tokens, service-account JSON, or `.env`.
- Importing patient-data bundles is destructive for existing patient data after a safety backup.
- The Test NNH server is local/demo infrastructure and must not be treated as production.
- Caddy certificate issuance still depends on correct public DNS/Cloudflare routing to the VPS on ports 80 and 443.
- Google Drive's developer API terms restrict general backup use without express written consent. The owner explicitly accepted that residual policy risk for this personal-use deployment and enabled the timers; this is not a legal or compliance conclusion.
- The NAS mirror is append-only by application logic rather than immutable/WORM storage. A compromised VPS could feed correctly named malicious ciphertext or exhaust the bounded 20 GiB areas, but cannot use this path to decrypt backups, write the archive directly, or access other NAS folders.
- The Synology Docker host enforces AppArmor, memory limits, dropped capabilities, `no-new-privileges`, mount isolation, and a networkless promoter, but its kernel did not expose the normal seccomp profile or honor requested PID/CPU limits.
- The current Test NNH listener can appear LAN-exposed through Docker port publishing; use `adb reverse` for physical-device local testing when possible.
- `MarkUS_Latest_API37` can appear attached while stuck behind a locked/black SystemUI state. For quick manual starts, switch to `MarkUS_Local` instead of debugging the APK.
- Firebase readiness depends on external console configuration and local secrets that are intentionally excluded from Git.
- The website-side authorization containment is live, but overall MEDTRACK production readiness remains NO-GO for Android until account isolation, generic push payloads, and the remaining release/recovery gates are completed.
- The unreleased CSP still permits inline style attributes because the existing theme system applies per-category CSS variables that way. Executable scripts require a nonce, and the one runtime-generated Crayons style block is limited to a pinned SHA-256 hash; upgrading Crayons requires revalidating that hash and the browser suite.

## Important Generated Outputs

- `backups/` - patient-data bundles and backup artifacts; treat as sensitive and gitignored.
- `staticfiles/` - collected Django static files.
- `output/` - Android/API smoke, audit, and field-test evidence when scripts are run.
- `output/android-claude-handoff-final-20260531-105420/` - current screenshot handoff for style and workflow review.
- Synology `Home/Backups/MEDTRACK/archive/` - encrypted NAS recovery archive; no private `age` key and no automatic deletion.
- `C:\Users\prave\Documents\NNH umich\MEDTRACK Recovery\2026-08-11-nas-restore\` - local encrypted NAS restore evidence and verification report; no retained plaintext.
- `%USERPROFILE%\.codex\build\medtrack-android\app\outputs\apk\debug\app-debug.apk` - default debug APK output.
- `test_nnh_state` - Docker volume for the Test NNH demo SQLite database.

## Next 3 Actions

1. Review and merge the website frontend/privacy/accessibility hardening PR, then deploy only through the normal backup, exact-commit, and live-acceptance gates.
2. Rotate temporary production credentials and resolve the HostDZire browser-console recovery issue; keep Drive/NAS health and monthly scratch restores monitored.
3. Before enabling Android/FCM in production, implement account-scoped encrypted local state and PHI-free push payloads, then complete physical-device and two-user field tests.
