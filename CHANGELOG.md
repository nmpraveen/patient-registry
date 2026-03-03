# Changelog

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
