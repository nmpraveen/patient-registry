# Changelog

## 2026.03.03.22.21
- Added a new admin Settings page at `/patients/settings/seed-mock-data/` to run mock-data seeding directly from the web UI.
- Added UI controls for seeding options (`profile`, `count`, vitals toggle, ANC RCH scenario toggle, and reset-all toggle) plus Seed/Re-seed/Delete actions.
- Wired the page to run the `seed_mock_data` management command and added seeded-data delete support for records with `metadata.source = seed_mock_data`.
- Added view tests for seed settings page access, command invocation options, and seeded-data-only deletion behavior.

## 2026.03.03.22.12
- Refactored `seed_mock_data` to create deterministic named scenarios (ANC high-risk, ANC RCH-missing, surgery planned, and non-surgical overdue) with `metadata.seed_scenario` traceability.
- Added seed command CLI options `--profile`, `--include-vitals`, and `--include-rch-scenarios` for scenario-focused data generation.
- Added post-task-build task status/due-date mutation, scenario-aware call-log generation, and optional vital-entry seeding to better populate dashboard and workflow states.
- Expanded seed command tests to validate scenario metadata, ANC RCH behavior, task/status coverage, vitals, and smoke profile sizing.

## 2026.03.03.22.05
- Updated `seed_mock_data` reset behavior so `--reset` removes only seeded mock cases (and their call/activity logs) using `metadata.source == "seed_mock_data"`.
- Added an explicit `--reset-all` flag for full case/call/activity data wipes.
- Documented the new reset semantics in the README demo-data section.
- Added management-command test coverage to confirm non-seeded cases survive `--reset`.

## 2026.03.03.18.09
- Added a changelog page at `/patients/settings/changelog/` that lists each version and its change notes.
- Added a "View Changelog" link on the Admin Settings page for quick access.
- Kept login page version footer support and version/context wiring from the previous release.

## 2026.03.03.17.38
- Added a global `VERSION` file and exposed `app_version` through a Django context processor.
- Displayed the current version on the login page footer.
- Updated AI agent workflow notes to require bumping `VERSION` for user-visible or shipped code changes.
