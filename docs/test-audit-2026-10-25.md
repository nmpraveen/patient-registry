# MEDTRACK test audit — October 25, 2026

Local audit completed on `codex/test-audit-2026-10-25`, based on `e07e69dc0efa64c9611a518478e8afc71a2df896`. The owner subsequently authorized feature-branch delivery through a draft PR. This report records the local audit evidence; current hosted checks and the independently reviewed PR head are recorded in the PR and local project context. No release, deployment or production-data access. Changes preserve all existing behavioral tests and all required CI/release gates. No legacy application, Android or recovery source was deleted. Receipt links below refer to ignored local evidence and are not published in the PR.

## Starting state and boundaries

The sole checkout started on `main`, equal to `origin/main`, with only the owner's existing `AGENTS.md` modification. Its SHA-256 is `22e5ca81d67f6f7ec2ee77521225f3156c14f2ccf9aac8e927f16de97ab200eb`; it remains unchanged. [Initial state and hook inventory](../output/test-audit-20261025/initial-git-state.json) and the adjacent saved patch record that boundary. Two subagents performed read-only investigation/review; this chat was the only writer.

Validation used the existing synthetic `medtrack-mac-dev` PostgreSQL container on loopback port 55433, native project Python, and disposable databases named `test_medtrack_audit_20261025` and `test_medtrack_audit_focused_20261025`. Django removed both; the container was returned to its initial stopped state. Restricted mounts, persistent synthetic data and production credentials were untouched. No schedules were created or enabled.

## Actual triggers and commands

| Trigger / entrypoint | Before | After |
| --- | --- | --- |
| Local commit / push hooks | `core.hooksPath` unset; only sample hooks; no tests execute | Unchanged |
| Feature-branch push without a PR | No matching CI push trigger | Unchanged |
| PR opened/synchronized/reopened against `main`; push to `main`; manual CI dispatch | Eight exact-head jobs below, without path filtering | Same jobs, triggers and check names; no skipped-job gates added |
| Push to `main`: trusted attestation | Independent canonical build/context/layer checks, vulnerability scans, SBOM and service-image verification; downstream provenance/SBOM signing | Unchanged; no signing performed in this audit |
| Monday 12:17 UTC and manual freshness dispatch | `pip_audit`, remote image-pin check, reproducible Python locks | Existing security schedule unchanged |
| Weekly Dependabot | pip, Docker, Gradle Android, GitHub Actions update configurations | Retain pip/Docker/Actions; remove deprecated Android version-update configuration |
| Normal documented agent work | Generic full-suite example; Mac test guide led with the full suite | Affected modules/classes first; full suite for cross-cutting changes/full acceptance; documentation edits need link/diff checks |
| `npm run test:e2e` | 68 selected test/viewport pairs, 44 runtime skips | Select the same 24 effective pairs before fixtures; no runtime skip instances |
| Manual Android helpers | `android-ci.ps1`, `mobile-test-suite.ps1`, release/field-test helpers; mobile suite explicitly invokes Django plus Gradle | Retained historical/manual entrypoints; not web acceptance gates |

The tracked workflows and the live Actions workflow inventory agree. The inspected main SHA has only GitHub Actions checks, with no legacy commit statuses. No Xcode Cloud, Xcode project, other CI configuration or package lifecycle test hook was found in the maintained web tree. This does not prove absence of unadvertised external services.

| Exact-head CI job | Commands / coverage | Change |
| --- | --- | --- |
| Django tests | Locked dependencies, `pip check`, `python manage.py test` | All existing tests retained; two clock regressions added |
| Migration integrity | `makemigrations --check --dry-run`; migrate empty PostgreSQL, Django check, ensure no unapplied migrations | Unchanged |
| Strict OpenAPI | `spectacular --validate --fail-on-warn --file openapi-ci.yml` | Remove unused PostgreSQL service |
| Supply-chain scans | Vulnerability audit, regenerate locks, immutable image pins, three scanner unittest modules, full-tree Trivy scan, non-web production service scans/SBOM | Unchanged |
| Compose and shell | Both Compose renders, shell syntax/ShellCheck, eight explicit operations unittest modules, all 11 `scripts/tests/test-*.sh` suites, runtime allowlist and image-pin checks | Strengthen one negative proxy assertion; retain commands/dependencies |
| Windows verifier regressions | Native scratch-state/catalog unittest modules and two PowerShell failure/installer suites | Unchanged |
| Container integrity | Canonical exact-source OCI build, context canaries, layer/image scanning, SBOM/provenance and artifact receipt | Unchanged |
| Frontend no-overflow | Five Node logic tests; Python overflow smoke (six routes × four widths); nine desktop review browser tests | Install shared system dependencies once; retain both runner-specific browser installs and both browser commands |

Live branch-protection read-back still requires seven Actions-app-bound checks: Django, migration, OpenAPI, supply-chain, Compose/shell, container and frontend. The Windows job is additional. The Mac release verifier also requires **every job in the exact main CI run to succeed**, so blanket job skipping would break release authorization. [Read-back](../output/test-audit-20261025/branch-protection.json), [workflow invariants](../output/test-audit-20261025/workflow-invariants.json).

## Changes and proof

1. **Focused Django selection:** `patients/test_anc_review_fixes.py` and `patients/test_anc_comment_fixes.py` now import the fixture module instead of exposing its `FollowUpTests` class to discovery. Their six reused fixture attributes remain the identical objects. Focused collection drops **22 → 7** and **21 → 6**. Django already deduplicated these classes in the full suite: there was no full-CI duplication to remove. All **714 original IDs remain**, with two new tests yielding **716 unique IDs**. [Before](../output/test-audit-20261025/django-selection-before.json), [after](../output/test-audit-20261025/django-selection-after.json).

2. **Browser selection:** `playwright.config.js` excludes desktop review tests from narrow projects and uses explicit tags in `frontend-a11y.spec.js` for desktop/edge-width coverage. Redundant runtime skips are removed from both specs. Before/after collection proves the effective set is identical: 320: **3**, 390: **2**, 430: **2**, desktop: **17**. The 44 removed instances were previously skipped, including **17 that performed login first**. All responsive, accessibility, PHI race/cache, identity-merge, CSP/theme and WebAuthn assertions remain. This improves the broader local matrix; CI already selected the desktop review file. [Selection proof](../output/test-audit-20261025/playwright-selection-proof.json).

3. **CI setup:** strict schema generation succeeded with PostgreSQL deliberately unavailable (`127.0.0.1:1`), and its output is byte-identical before/after. Removing its service loses no database test. Node's second `--with-deps` is removed; its `install chromium` remains in case the two pinned Playwright versions diverge. Both current runners are 1.63.0 / Chromium revision 1243 and launch successfully. No dependency locks or actual browser checks were removed.

4. **Deprecated automation:** remove only Gradle's weekly version-update entry in `.github/dependabot.yml`. Current AGENTS/README and branch-protection documentation explicitly deprecate Android, and its CI job was already retired. Android source, locks, tests, manual scripts and full-tree security scanning remain. Future avoided PR/CI counts depend on available updates; no fixed weekly saving is claimed.

5. **Genuine seed bug:** `_build_recorded_at` in `patients/management/commands/seed_mock_data.py` previously clamped a future timestamp to `now - 5 minutes`, moving today's vital into yesterday during the first five minutes after India midnight. Clamp to `now` instead, preserving date alignment and the no-future rule. Two database-free tests in `patients/test_seed_mock_data.py` cover midnight/year rollover, later same-day times and past clinic dates. The old code failed at 00:00/00:03; the fix passes. The existing database alignment assertion also passes at a forced 00:03 without weakening it.

6. **False-positive test prevention:** `scripts/tests/test-edge-auth-throttle.sh` now requires the actual inconsistent-proxy diagnostic and prints unexpected startup errors. Previously any failure, including missing Django, satisfied that negative test. Real rejection passes; simulated missing dependency and incorrect success both fail. No production proxy behavior changed.

README/RUNBOOK now point normal work to focused verification and this report. Existing local-only `MAC_DEVELOPMENT.md` and `PROJECT_CONTEXT.md` were updated without forcing them into Git. The Mac guide's stale “recovery checks enabled” statement was corrected to the owner's documented disabled state. `AGENTS.md` remains unchanged. Authorized PR delivery updates `VERSION` and prepends matching `CHANGELOG.md` notes for `2026.10.25.04.44`, as required for the seed-command code change.

## Measured baseline and savings limits

The GitHub connector confirmed the latest PR jobs; raw Actions timestamps and live protection were read with `gh api` because the connector summaries omit those fields.

The latest main [CI run 40005841211](https://github.com/nmpraveen/patient-registry/actions/runs/40005841211) took approximately 7m48s elapsed. Individual job durations were Django **466s**, migrations **31s**, OpenAPI **29s**, supply-chain **244s**, Compose/shell **170s**, Windows **42s**, container **65s**, frontend **124s** (1,171 summed runner seconds, not elapsed time). [Job/step timestamps](../output/test-audit-20261025/ci-main-jobs.json).

OpenAPI's now-removed container initialization took **11s**, with **1s** cleanup. That measures removed setup work, not a guaranteed end-to-end saving: Django remains the critical path. Frontend's second npm/browser installation step took **3s total**, so its dependency-only saving cannot be isolated from that timing. The 44 skipped combinations / 17 logins and 15 extra tests per focused module are proven counts, not measured runtime savings.

PR146's [CI run 40003357100](https://github.com/nmpraveen/patient-registry/actions/runs/40003357100) failed its seed alignment assertion on attempt 1; the subsequent Django-only retry cost **359 job seconds**. Other jobs retained their original timestamps. The midnight regression reproduces that failure mechanism; the exact test's clock instant was not logged, so attribution is supported rather than conclusively timed. Future retry savings are unknown. [Failure log](../output/test-audit-20261025/ci-django-failure-sanitized.log), [attempt 1](../output/test-audit-20261025/ci-pr-attempt1-jobs.json), [attempt 2](../output/test-audit-20261025/ci-pr-attempt2-jobs.json).

## Validation

All Python commands used `source .local/mac/env.sh`; database tests used DEBUG=false, mock seeding disabled globally and the disposable DB names above. Seed tests explicitly enable synthetic seeding within their existing test override.

| Command / check | Result |
| --- | --- |
| `python -m pip check` | Pass; Python 3.12.15 / Node 22.23.4 |
| `python manage.py test --noinput` before implementation | **714 tests, 245.382s**, pass with **2 expected skips** for the absent optional local demo command; 250.754s wall |
| `python manage.py test patients.test_seed_mock_data --noinput` against old/new seed code | Old: two failing midnight subcases; new: **2 tests pass** |
| Focused Django labels: `patients.test_anc_review_fixes patients.test_anc_comment_fixes patients.test_follow_up patients.tests.SeedMockDataCommandTests patients.test_seed_mock_data` | **39 tests, 20.642s**, no skips/failures; 22.760s wall. Existing seed alignment test wrapped with fixed India 00:03 clock |
| `node --test tests/js/web-regressions.test.cjs` | **5 pass**, 104.504ms |
| `npx playwright test --list --reporter=json` before/after | Exact effective selection parity: **24 pairs**, all 17 unique browser tests preserved |
| `npx playwright install chromium`; Python and Node Chromium launch/title smoke | Both pass against synthetic in-memory HTML |
| `POSTGRES_PORT=1 python manage.py spectacular --validate --fail-on-warn ...` | Pass, no database; unchanged schema; measured final run 0.871s |
| Extracted changed proxy-negative shell block with real Python / simulated missing Django / incorrect success | Expected exit codes **0 / 1 / 1** |
| YAML parse + workflow invariants; `node --check` on changed JS; `bash -n` on changed shell | Pass; same triggers, eight jobs, seven live required names, exact-head verification, no added skips |
| `git -c core.whitespace=cr-at-eol diff --check` | Pass; preserve existing mixed/CRLF file conventions |

[Baseline receipt/log](../output/test-audit-20261025/django-baseline.json), [focused receipt](../output/test-audit-20261025/django-focused.json), [focused log](../output/test-audit-20261025/django-focused.log), [proxy controls](../output/test-audit-20261025/proxy-negative-gate.json), [schema proof](../output/test-audit-20261025/openapi-no-database.json), [database cleanup](../output/test-audit-20261025/database-cleanup.json). Full-suite execution was not repeated after each small edit; final discovery proves retention and focused tests cover the changed behavior.

## Protected coverage, withheld removals and limits

- Retain all identity/alias/issuance-floor, stale-edit/lock-order, authorization/authentication, audit, migration, import/export, idempotency/replay and recovery tests. Retained APIs remain registered and supported by `API_CONTRACT.md` despite native-client deprecation.
- Default Django discovery does **not** include `scripts/tests/`; explicit CI operations/scanner commands are separate coverage. Windows versus Linux lock/catalog tests cover different native implementations and are not duplicates.
- Keep legacy recovery fixtures/catalogs, irreversible migrations and optional local helper tests: historical data/recovery and external/manual callers prevent proving obsolescence. No behavioral test body deletion was justified.
- Keep manual browser smoke helpers and `frontend-a11y.spec.js`: CI's Python overflow smoke and desktop review subset do not replace their complete behavior coverage.
- Keep the independent trusted main build/signing workflow and main CI. Removing repeated builds requires an artifact-transfer/trust redesign; PR evidence cannot automatically replace exact-main release proof. Keep Compose Python dependencies: the edge test needs a real Django startup check.
- Two read-only independent reviews found no blocking issue and verified test/viewport retention and required-check compatibility.
- This is local validation. No revised GitHub Actions run, Ubuntu dependency-install timing, full application browser session, complete Caddy integration rerun, Windows execution, new container scan or release signing was performed. Browser listing/launch evidence is not authenticated application acceptance. Unchanged CI/security lanes remain required on a future authorized PR.

Audit-owned changes are delivered only on the feature branch; `main`/`origin/main` remain at the starting SHA. Existing `AGENTS.md` bytes and unrelated files are preserved. Local context/Mac guide changes remain intentionally ignored, and detailed synthetic receipts remain under `output/test-audit-20261025/`.
