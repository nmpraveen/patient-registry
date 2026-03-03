# Changelog

## 2026.03.03.18.09
- Added a changelog page at `/patients/settings/changelog/` that lists each version and its change notes.
- Added a "View Changelog" link on the Admin Settings page for quick access.
- Kept login page version footer support and version/context wiring from the previous release.

## 2026.03.03.17.38
- Added a global `VERSION` file and exposed `app_version` through a Django context processor.
- Displayed the current version on the login page footer.
- Updated AI agent workflow notes to require bumping `VERSION` for user-visible or shipped code changes.
