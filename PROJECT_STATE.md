# PROJECT_STATE.md

## Issue #113 Stage 2 implementation

Stage 2 combines web/API and native task editing, original-baseline conflict handling, descriptive task history and general-call reasons on Stage 1 merge `4531f09c728f1c11141f7f636a4f14fc43eb740a` (PR #115). Legacy queued call/completion JSON remains compatible; reasons round-trip through bundles and bounded call history. Native integration preserves the final Stage 1 ANC refresh/cancellation guards, and server Case/Patient baselines and lock order remain unchanged.

Local validation passed: 543 backend tests (two expected absent local-helper skips), 127 native core tests, final targeted tests and dev assembly, responsive web/keyboard checks and synthetic native online/offline call checks. Post-rebase validation passed 47 server integration tests, 30 native repository tests, app compilation, schema validation and migration drift checks. See docs/issue-113-stage-2.md and the coordination stage-2-report.md for exact commits, outputs and limits. The combined PR review and exact-head CI remain required before merge; no production activation is implied.

## Issue #113 Stage 1 source implementation

Stage 1 is merged as PR #115. The following correction entries are its completed review history; their earlier pending-gate wording is superseded by the merge recorded above.

The remaining Recent Cases lock-order issue is reproduced and corrected with precise mandatory-audited diagnosis/notes/timestamp updates, preserving fresh activity before-values and checking Patient linkage without taking a Patient lock. Eight targeted regressions pass; fresh exact-head CI and the correction-only recheck supersede the prior head.

The native ANC callback now propagates coroutine cancellation from both action and list refresh instead of writing warnings or invoking report callbacks. Five standalone scenarios extracted from the actual callback and incremental app Kotlin compilation pass; this minimal correction requires fresh exact-head CI.

The latest native ANC success correction refreshes the active list membership and counters after authoritative detail, preserving every active filter and clearing remembered filters on account reset. Focused repository tests and incremental app Kotlin compilation pass; fresh exact-head CI and bounded correction verification supersede the prior e49ab891 gate.

The related full web-edit deadlock correction locks Patient before Case, refreshes scoped state/linkage before form binding, and includes Patient identity/version in the rendered baseline. Actual concurrent CaseUpdate/PatientUpdate requests complete with a clean stale-draft rejection and preserved identity/audit. Focused tests pass; fresh exact-head CI and correction verification replace the prior 2168b74 gate.

The latest two review corrections protect the actual rendered web-edit baseline through POST and use normalized ANC action visibility. Real GET-to-separate-clinical-write-to-original-POST regressions pass, alongside missing/tampered baseline, normal edit, API compatibility and mixed-case permission checks. Fresh exact-head CI and coordinator targeted verification remain required.

Four subsequent automated ANC comments are addressed in the final feedback revision: acknowledged native cancellation safety, loss-to-follow-up/close consistency, valid seed bundle round-trips and precise audited ANC updates without Patient lock inversion. Targeted validation and fresh exact-head CI replace earlier revision gates.

The six existing automated review comments are addressed in the pending revision: background Room mapping, Grey permission parity, initial ANC reclassification dates, SQL patient-group pagination and retained-task worklist visibility. This supersedes the earlier d2ab783 review/CI gate; a focused feedback recheck and fresh exact-head CI are required.

The four Stage 1 review findings are addressed: PostgreSQL-safe scoped row locks, concurrent web edit preservation, explicit reminder cancellation retention, and shared ANC outcome validation for imports. Review-fix verification passed 91 targeted tests; fresh exact-head CI and the coordinator's focused recheck remain the merge gates.

Stage 1 adds scoped dormant/overdue/EDD-missing follow-up views, persistent task-independent ANC EDD attention, explicit audited outcome/EDD actions, and additive native/API/bundle contracts. Django migration 0040 and Room 12→13 preserve existing statuses/history. EDD correction retains every task date. Historical closed ANC reconciliation is read-only. See [Stage 1 contract and validation](docs/issue-113-stage-1.md).

Local evidence: 509 Django tests passed (two existing skips) before dependency integration; the Stage 1 browser smoke passed five routes at four widths and real synthetic correction/referral submissions; native unit/debug builds passed. Dependencies are integrated from main `04e2f13bc32b9c2249aee7ab1e36081d806a273e`. The PR's exact-head CI is the final source gate. This feature has not been deployed; native Firebase/physical-device acceptance remains separate.

## Dependency maintenance (2026-09-07)

PR #109 migrates Android to AGP 9 built-in Kotlin and the Kotlin Compose compiler plugin, compiles against API 37 while preserving target API 36 and minimum API 24, and refreshes strict dependency locks and checksum metadata. The shared container repair pins Alpine libuuid 2.41.6-r1. These are source changes only; no production deployment or signing was performed. Exact-head CI remains the merge gate.

## Current Status

MEDTRACK is a runnable Django + Postgres case-follow-up MVP with a native Android companion app in the same repo.

The web app supports login-based role-aware workflows, case dashboards, case activity logs, configurable roles/categories/theme settings, patient-data import/export, server-side backup bundles, and seeded demo records.

The Android v1 implementation and its reviewed server contracts are merged in source, including API 36 environment flavors, fail-closed case edits, account-scoped encrypted state, cursor snapshot sync, durable recovery records, and data-only opaque FCM consumption. The release goal is not complete until external Firebase, physical-device, signing, and field gates pass.

GitHub build/release containment is implemented in the current remediation change: the Docker context and image are runtime-allowlisted, Python and production image inputs are immutable, Android artifacts use Gradle checksum verification, and exact-head CI covers backend, schema, supply-chain, container, frontend, and Android gates. Branch protection is intentionally not mutated by this change; the coordinator must apply the tracked configuration after the workflow merges and has emitted all required check names.

Production is deployed on the hardened VPS at commit `a5dff668b23c52e5a71431807a291573f9e0404c`: pinned Python/PostgreSQL/Caddy versions, loopback-only Django exposure, persistent host backup storage, health-gated startup, and exact-commit deployment. Website and API object authorization now enforce created, assigned, or current call-queue scope for restricted staff; Doctor/Admin retain full active-case scope. Non-superusers can no longer modify superusers or grant settings-admin access, and the plaintext temporary-password-note model/table/UI have been removed. Encrypted Google Drive backups and health timers are active, and a pull-only Synology ciphertext mirror provides an independent off-VPS copy.

GitHub `main` is source-reviewed at `892a0c2a6095b346fcbb5a90804a481ec849ee76`, but this task did not query or modify the live VPS, Drive, NAS, or backup state. The rebased operations/recovery remediation branch adds fail-closed verified restore and rollback, two-phase deployment gates, supervised patient-data scheduling, stronger off-site triplet/hash health, destructive reverse-migration refusal, and bounded imports. Those controls remain pending PR merge and an explicitly approved live installation; they are not deployed.

## Last Verified Date

2026-08-30

The unreleased `codex/remediate-frontend-a11y` branch adds website-only frontend, privacy, and accessibility hardening on base commit `920357a58a69bd2e18ed03023a4273cd1493a066`. Focused Django/template regressions and the Playwright Chromium matrix pass at 320, 390, 430, and 1440 pixels with no console or request failures, horizontal document overflow, external asset requests, or browser-back PHI exposure. Its 577-file vendor manifest is byte-stable in fresh Windows and Linux checkouts, and rendered theme interaction text is validated at 4.5:1 separately from the 3:1 focus-indicator boundary. This branch is not deployed; the production commit recorded below is unchanged.

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
- Release readiness: local packaging/remediation implemented; blocked on exact API PR #99 integration, account-scoped encrypted Room/outbox handling, external Firebase delivery evidence, a physical Android phone smoke, and a two-user field-test record.

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
- Android sync recovery records preserve structured local/server payloads and provide durable retry/discard actions instead of silently poisoning the WorkManager queue.
- Android notification sync exhausts opaque cursors and reconciles stale/revoked rows only after a terminal complete snapshot; raw FCM display is suppressed and only triggers authenticated API refresh.
- Android API 36 dev/stage/prod flavors, external-only signing configuration, dependency locks, third-party notices, and unsigned release APK/AAB audit tooling are implemented.
- Android screenshot handoff for login, home, filters, red-flag reasons, cases, case detail, vitals entry, notifications, alert detail, calls, dialer handoff, call outcome, profile, quick add, create case, and final home state.
- Android alert detail, call outcome, and Custom Rehab visual surfaces are locally implemented for review.
- `MarkUS_Local` is the preferred AVD for quick manual Android start/login checks against Test NNH.
- Firebase/FCM integration boundary is implemented so missing Firebase config does not break normal local use.
- Production Caddy/Docker deployment with exact-commit refusal, service healthchecks, secure loopback binding, and persistent `/app/backups` storage.
- Encrypted off-VPS recovery tooling with immutable upload names, post-upload verification, exact-pattern retention, four scheduled tiers, a pre-deployment tier, and freshness/retention health checks.
- Source-level operations remediation for encrypted scratch-first restore, tested rollback artifacts, reviewable one-shot migrations, supervised backup scheduling, complete-triplet/hash health, fail-closed reverse migration, and bounded ZIP imports. Live enablement remains coordinator-controlled.
- Live encrypted canary `medtrack-prod-canary-20260811T165254Z.tar.age`, independently downloaded, checksum-verified, decrypted off VPS, restored into PostgreSQL 16.14, and validated by the exact deployed Django commit.
- Pull-only Synology mirror at `Home/Backups/MEDTRACK` with a read-only SFTP export, networked incoming-only fetcher, network-disabled archive promoter, hard space/transfer ceilings, and no automatic deletion.
- NAS-sourced restore proof for the same canary: external and internal checksums, PostgreSQL restore, exact-commit Django checks, ORM queries, and login HTTP 200 all passed; decrypted scratch material was removed.
- Unreleased website frontend hardening: hash-verified locally pinned assets, nonce/hash CSP without blob scripts, browser headers, universal dynamic-response no-store caching, unique form IDs, labeled controls, race-safe combobox semantics, complete affected-set merge review, text/interaction/focus contrast enforcement, responsive overflow fixes, and browser regressions.

## Not Done

- Native create-case currently remains a mock/draft-style flow and is not persisted through the backend API.
- First-run secure setup and unlock routing exist in source but were not reachable in the current fresh-login screenshot flow.
- Real Firebase push delivery is not proven for MEDTRACK until Firebase Android config, Django service-account config, and a real FCM token are supplied.
- Low-end or representative physical Android phone smoke is not complete.
- Two-user field-test record is not complete.
- Final Android v1 audit remains incomplete until `.\android\scripts\medtrack-v1-audit.ps1` reports `goalComplete=true`.
- The new operations/recovery gates have only local/synthetic and isolated validation until the coordinator approves installation and live acceptance. Do not run restore activation, deployment apply, or unit installation against production from this task.

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
- The website-side authorization containment and Android account/session boundaries are implemented, but overall MEDTRACK production readiness remains NO-GO until the final mobile API-contract integration and release/recovery gates are proven together.
- The unreleased CSP still permits inline style attributes because the existing theme system applies per-category CSS variables that way. Executable scripts are self-hosted and nonce-bound, and the one runtime-generated Crayons style block is limited to a pinned SHA-256 hash; upgrading Crayons requires reviewing the vendor integrity manifest, revalidating that hash, and rerunning the browser suite.

## Important Generated Outputs

- `backups/` - patient-data bundles and backup artifacts; treat as sensitive and gitignored.
- `staticfiles/` - collected Django static files.
- `output/` - Android/API smoke, audit, and field-test evidence when scripts are run.
- GitHub Actions artifact `medtrack-sbom-provenance-<sha>` - CycloneDX SBOM, unsigned local in-toto statement, and OCI image archive containing BuildKit SBOM/provenance attestations; retained for 30 days.
- `output/android-claude-handoff-final-20260531-105420/` - current screenshot handoff for style and workflow review.
- Synology `Home/Backups/MEDTRACK/archive/` - encrypted NAS recovery archive; no private `age` key and no automatic deletion.
- `C:\Users\prave\Documents\NNH umich\MEDTRACK Recovery\2026-08-11-nas-restore\` - local encrypted NAS restore evidence and verification report; no retained plaintext.
- `android/.build/` - per-worktree Gradle build outputs.
- `android/release-artifacts/<version>/<git-sha>/` - audited unsigned APK/AAB, SHA-256 manifest, CycloneDX SBOM, provenance, and credential-entry audit.
- `test_nnh_state` - Docker volume for the Test NNH demo SQLite database.

## Next 3 Actions

1. Review and merge the operations/recovery PR at its exact head; do not deploy it based only on local or synthetic tests.
2. With explicit live approval, install the supervised units and independent scratch-restore hook, generate a fresh pre-deployment receipt, review the migration-plan hash, and exercise the documented plan/apply/login/rollback gates without exposing credentials or PHI.
3. Before enabling Android/FCM in production, prove external data-only Firebase delivery, signed release identity, physical-device behavior, and the two-user field test.
