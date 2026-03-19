# Changelog

## 2026.03.19.03.14
- Split Docker Compose into a shared base plus a tracked `docker-compose.dev.yml` overlay so local bind-mount behavior stays in git while VPS-only Docker settings can live in a private `docker-compose.override.yml`.
- Updated local Test NNH wrappers and docs so they use the dev overlay and automatically include a private local override file when present, preserving the existing local demo workflow.
- Expanded backup and restore scripts to capture and restore compose overlay files when they exist, and added ignore rules for private override and ad-hoc VPS backup artifacts.

## 2026.03.19.01.29
- Hardened `/patients/settings/` so missing settings-related tables or columns on a deployed server no longer crash the page with a 500 during schema drift.
- Added an admin-facing warning on the Settings hub that points operators to `python manage.py migrate`, shows unavailable sections clearly, and disables links to settings modules that depend on the missing schema.
- Fixed the Settings hub theme summary so legacy or partial saved theme-token JSON is merged with defaults before counting customizations, preventing `KeyError` crashes from older theme rows.
- Added regression coverage for both the degraded settings-hub path when device-access settings schema is absent and the legacy theme-token payload that reproduced the VPS failure.

## 2026.03.18.23.57
- Rebuilt `/patients/cases/new/` into a responsive case-intake workflow with a split layout, sticky save actions, live starter-task preview, inline identity warnings, and HTMX-driven workflow/duplicate-check updates while keeping the existing Django route and server-side validation rules.
- Simplified the day-to-day intake flow by defaulting the page to a low-copy mode with a `Show Help` toggle, removing the visible new-case status control, switching category selection to themed radio cards, and tightening the default ANC path with hidden gender selection plus normalized ANC field labels and alignment.
- Added the new ANC `Obstetric history (GPAL)` section with compact plus/minus controls, a `Primi` preset, live `Gx Px Ax Lx` summary, preserved null-versus-zero save semantics, and compatibility fixes so explicit zero GPLA values continue to render correctly in edit/detail views.

## 2026.03.18.17.05
- Simplified the top navigation search field by removing the long explanatory placeholder text and replacing it with a compact magnifying-glass treatment while keeping the same search behavior and accessibility label.

## 2026.03.18.16.54
- Added a new `Quick Entry` patient-create flow with a dedicated six-field form, auto-generated `QE-YYYYMMDD-###` placeholder UHIDs, and saved metadata marking records that still need full details.
- Created a matching quick-entry follow-up task (`Details need to be filled`) while preserving the existing category starter-task generation so staff can capture notes immediately and complete records later.
- Updated the top navigation and theme system so `New Case` uses a configurable success button, `Quick Entry` uses the warning palette, and quick-entry cases render intentional phone fallbacks in list/detail views.
- Extended seeded demo data and regression coverage for the quick-entry workflow, theme controls, seeded pending-details scenario, and top-bar permission behavior.

## 2026.03.18.03.18
- Normalized stored patient `first_name`, `last_name`, and `place` values to simple proper case on every `Case` save, with whitespace collapsed and `patient_name` re-derived from the normalized name values.
- Tightened partial `save(update_fields=...)` handling so patient identity fields stay in sync even when only one of the name fields is explicitly saved.
- Added batched data migrations to rewrite existing patient names and places into the same normalized storage format without touching `updated_at`, and expanded regression coverage for direct ORM saves, case create/edit flows, and database bundle imports.

## 2026.03.18.02.10
- Reworked the dashboard `Today`, `Recently Added`, `Overdue`, and `Awaiting Reports` modules into a shared compact-row layout with category tinting, inline expand behavior where needed, and mobile-friendly condensed rows.
- Replaced the `Recently Added` modal workflow with inline notes and task review, preserved `Open full case`, and expanded the dashboard/recent payloads to include compact sex-age, short-name, due-date, and category theme metadata.
- Simplified the module headers so they show only the title, moved long-list `Expand` controls to the top-right of each module, and fixed the `Awaiting Reports` expand-button contrast so the label stays readable before hover.
- Added dashboard regression coverage for the compact-row markup, inline recent detail container, expanded recent-case API payload, awaiting-row rendering, and the streamlined Recent header behavior.

## 2026.03.17.22.40
- Renamed the `Non-Surgical` category to `Medicine` across the live dashboard, case list, global search, theme preview, and validation copy.
- Updated category matching, theming, and case-form behavior so `Medicine` is the canonical category name while legacy `Non Surgical` spellings still map to the same internal filter and style bucket.
- Added a data migration to merge existing legacy department rows into `Medicine`, repoint existing cases, and updated seeded/demo data plus regression coverage for the renamed category.

## 2026.03.17.21.57
- Changed the dashboard `Upcoming Schedule` week controls to refresh in place instead of triggering a full-page reload, while keeping the URL and browser history in sync.
- Updated the dashboard script to fetch the next week view asynchronously, replace the Upcoming summary and schedule DOM together, and preserve the existing day-tab interaction after each swap.
- Added regression assertions for the rendered week-navigation hooks used by the in-page updater.

## 2026.03.17.21.49
- Reworked the dashboard `Upcoming Schedule` from a rolling `Today + 7 days` window into Monday-Sunday week navigation with `This week`, `Next week`, and conditional `Previous week` controls.
- Changed the dashboard schedule query and tab state so each view renders exactly one selected week, defaults to today within the current week, and starts on Monday for future weeks.
- Added regression coverage for week-offset validation, next-week filtering, previous-week navigation visibility, and preserved grouped/category-themed schedule rows.

## 2026.03.17.11.11
- Changed the India-style Crayons datepicker rollout to commit single-date selections immediately on day click instead of waiting for the picker footer's `Update` button, preventing blank submissions that triggered `Pick a valid date`.
- Normalized picker write-back to submit `YYYY-MM-DD` into Django even though the Crayons component reports full ISO datetimes, and synchronized picker disabled/readonly/min/max state with the hidden source input after enhancement.
- Added explicit unique ids for inline quick-reschedule date inputs and extended regression coverage for the rendered datepicker attributes and dashboard reschedule template.

## 2026.03.17.03.28
- Added production static-file serving for Django via WhiteNoise and a collected `staticfiles/` output so datepicker assets and other app static files are available behind Gunicorn.
- Updated the Docker web startup command to run `collectstatic --noinput` before Gunicorn so new static assets are present after each deploy.

## 2026.03.17.03.12
- Renamed the shared top-bar brand label from `MEDTRACK` to `NNH` across the authenticated navbar and the Theme settings live preview.

## 2026.03.17.02.48
- Upgraded case and task date fields to a Crayons-style datepicker experience with `dd/MM/yyyy` display for India while preserving ISO date submission for Django.
- Added shared datepicker assets and wired quick-add and quick-reschedule task forms into the same reusable date input treatment.
- Expanded date parsing and regression coverage so case forms and inline task rescheduling accept both ISO dates and `dd/MM/yyyy` input.

## 2026.03.17.02.16
- Enlarged the Settings hub version panel in `Utilities & About` so long version stamps fit comfortably and read as a dedicated info tile instead of a cramped metric chip.

## 2026.03.17.02.09
- Rebuilt the main Settings page into a category-based admin hub with filterable overview cards for user management, categories/workflow defaults, device access, data recovery, appearance, and utilities/about.
- Expanded `User Management` into the single admin surface for users and roles, including a dedicated roles tab, searchable user list, and an admin-only temporary plaintext password note with clear action and update metadata.
- Added a dedicated `Categories & Workflow` settings page for category names, predefined actions, metadata templates, and retained follow-up defaults, plus new migration and regression coverage for the redesigned settings flows.

## 2026.03.16.23.22
- Added an admin-only `User Management` settings page for creating users, editing names and usernames, resetting passwords, toggling active status, and assigning each account's primary role/group.
- Linked the new page from Admin Settings while keeping the existing role-permission configuration flow intact.
- Added regression coverage for user-management access control, user creation, user updates, and protection against removing the last active settings admin.

## 2026.03.16.15.24
- Fixed the automatic backup schedule form so browser time inputs that submit `HH:MM:SS` values are accepted instead of failing with the generic `Backup schedule has errors.` message.
- Rendered the daily backup time input explicitly at minute precision and added regression coverage for the browser-submitted seconds format.

## 2026.03.16.14.27
- Reworked the Database Management scheduler into three automatic backup tracks: daily backups at an admin-chosen time, monthly backups on the 1st at `12:00 AM`, and yearly backups on `Jan 1` at `12:00 AM`.
- Changed retention behavior so daily backups keep the newest 30 daily bundles while monthly and yearly archive bundles are retained indefinitely, with backup filenames and pruning now separated by backup type.
- Updated the scheduler UI, migration state, and automated coverage to show per-schedule last/next backup status and to verify that daily pruning never deletes monthly or yearly archives.

## 2026.03.16.13.52
- Added backup-scheduler controls to the Database Management page so admins can enable automatic patient-data backups as `1 per day`, `2 per day` at `00:00` and `12:00`, or custom `HH:MM` timings.
- Added persistent scheduler status on the page, including last backup time/result, last trigger type, last backup file, and the next scheduled backup time.
- Added a built-in background scheduler with DB-backed schedule state, due-run locking, status updates for manual/scheduled/import-safety backups, migration coverage, and automated tests for schedule save/validation and automatic backup execution.

## 2026.03.16.13.28
- Added an admin-only `Database Management` settings page for exporting patient-data ZIP bundles, importing validated patient-data bundles, and creating server-side patient-data backups.
- Introduced the patient-data bundle format (`patient_data.json` + `manifest.json`) with SHA-256 integrity checks, UHID-based case identity, duplicate-UHID validation, null-safe missing-user imports, and safety backups before destructive imports.
- Added the `backup_patient_data` management command for scheduled patient-data backups with retention pruning, updated the README with backup guidance, and expanded automated coverage for bundle export/import, rollback safety, and backup pruning.

## 2026.03.15.21.14
- Extended case search so `CallLog.notes` are searchable alongside direct case fields, case notes, and timeline note entries in both the navbar autocomplete and the full case search results page.
- Updated the search UI copy to explicitly call out case-note and call-note matching.
- Added regression coverage for call-note-only matches in both the full results page and the navbar search ranking.

## 2026.03.15.19.35
- Expanded global case search to include place, case notes, and timeline note entries, while keeping quick top-result navigation and adding a `View all results` handoff into the full cases page.
- Upgraded the existing case list into a search-results experience for keyword queries with multi-select category pills, result counts, diagnosis visibility, and matching note snippets from either case notes or note logs.
- Added coverage for the expanded search scope, note-result ordering, repeated category-group filters, and the authenticated layout's full-results search handoff.

## 2026.03.15.18.46
- Fixed the live WebAuthn registration and authentication verification flow to use the current `webauthn` library API instead of the removed `parse_raw(...)` helper, which was causing device registration to fail after the passkey prompt.
- Improved device verification page error messages so cancelled or blocked iPhone passkey prompts show clearer guidance instead of a generic request failure.

## 2026.03.15.18.15
- Added a pilot device-approval login flow with WebAuthn-backed device registration, trusted-browser cookies, and admin approval gating for selected users without changing the default login path for everyone else.
- Added a new Device Access admin settings page to save pilot target users, review pending and approved devices, approve or revoke browsers, and clone `Staff` permissions into a `Staff Pilot` role for safer rollout testing.
- Added device-approval models, migration coverage, login/device view tests, and setup documentation for the required WebAuthn relying-party configuration.

## 2026.03.13.00.19
- Restyled the dashboard's `Today's Tasks`, `Recently Added`, `Overdue Tasks`, and `Awaiting Reports` sections into the same framed, tinted module system introduced for `Upcoming Schedule`, while preserving the current layout, ordering, and interactions.
- Rebuilt today and overdue patient group cards plus awaiting-report rows with shared dashboard module accents derived from existing theme tokens, including the awaiting-report task status palette and category pills for report follow-up rows.
- Added stable dashboard section markers for the refreshed modules and extended dashboard view tests to cover the new module wrappers without changing backend contracts or permissions.

## 2026.03.12.22.42
- Replaced the old dashboard `Upcoming` card list with a compact appointment-style schedule module featuring a horizontal date rail, selected-day patient list, and built-in empty states for open days.
- Added distinct category dots and category pills derived from the configured department theme colors, including stronger dot accents so schedule categories remain readable when theme colors change.
- Extended dashboard view coverage for the inclusive schedule range, grouped patient rows, and category-theme color propagation in the new schedule section.

## 2026.03.12.18.17
- Removed the leftover vertical accent stripe from the dashboard navbar stat buttons so the new rounded button treatment reads cleanly without an extra divider line.

## 2026.03.12.18.00
- Refined the dashboard navbar stats into subtle button-like panels with soft tinted backgrounds, rounded borders, and hover polish while preserving the same layout and counts.
- Reused the existing Today, Upcoming, Overdue, and category theme colors so each stat is easier to distinguish without introducing a new visual pattern.

## 2026.03.12.17.48
- Fixed the dashboard navbar regression so the compact stats bar renders as a true second row beneath the main navigation instead of collapsing beside the brand/search/actions row.
- Rebalanced the shared navbar shell sizing so desktop keeps the intended inline search, category pills, and actions while mobile still shows the brand, menu toggle, and scrollable stats strip cleanly.

## 2026.03.11.21.16
- Tightened collapsed `Recently Added` rows into a single desktop metadata line with full-name truncation, a narrower-desktop first-name fallback, and a mobile wrap fallback.
- Added `first_name` to recent-case dashboard payloads so the collapsed recent list can switch names cleanly without changing routes, permissions, or modal behavior.
- Reused the recent-card hover lift on `Today's`, `Upcoming`, `Overdue`, and `Awaiting Reports` items while keeping the rest of the dashboard layout unchanged.

## 2026.03.11.20.56
- Refined `Recently Added` to match the dashboard's existing heading-and-card pattern instead of restyling the surrounding dashboard modules.
- Changed `Recently Added` to default to a collapsed compact list of 10 recent cases with an inline `Expand` / `Collapse` toggle, while preserving the existing recent-case modal workflow.
- Updated dashboard view tests to cover the collapsed default render, the expand control, and the empty-state behavior for the refined recent panel.

## 2026.03.11.15.02
- Added a Doctor/Admin and Reception-only `Recently Added` dashboard panel above overdue work, ordered by newest case creation time and capped to the latest 10 cases.
- Added `/patients/recent/` and `/patients/recent/<pk>/` JSON endpoints plus a lightweight modal workflow for reviewing recent cases, updating diagnosis/case notes, and keeping activity logs in sync.
- Extended inline task quick actions to return JSON for AJAX callers while preserving the existing redirect flow, and expanded view tests for the new dashboard, API, permission, and modal/task-action behavior.

## 2026.03.06.03.59
- Fully flattened the case-detail vitals column into the shared header shell so the identity rail, clinical panel, and vitals panel now use one consistent three-section layout.
- Reworked long patient-name handling with wider rail bounds, sane word wrapping, and length-based name-size classes to avoid aggressive mid-word breaks on desktop and mobile.
- Updated case-detail render tests for the new long-name sizing helper and the removal of the nested vitals wrapper.

## 2026.03.06.03.51
- Removed the extra boxed treatment from the case-detail vitals column so the identity rail, clinical section, and vitals section now read as one consistent three-part header.
- Rebalanced vitals panel padding and stacked-layout separators so the right column aligns visually with the center section on both desktop and smaller breakpoints.

## 2026.03.06.03.43
- Expanded the case detail identity header into a three-column desktop layout with a wider adaptive name rail for long patient names and a dedicated right-side vitals summary card.
- Moved the latest-vitals timestamp and actions into the new vitals card, removed the old bottom vitals strip, and reused existing vitals status theme tokens for the metric meters and empty state.
- Extended case-detail render coverage for long-name wrapping, vitals card rendering, partial vitals `N/A` rows, and the no-vitals empty-state workflow.

## 2026.03.06.03.20
- Rebuilt the case detail identity header into a split hero layout with a dark identity rail, visible clinical details panel, circular task-completion indicator, and mobile stacked adaptation.
- Added inline SVG icons, initials avatar rendering, task-count summary context, and a redesigned latest-vitals strip while preserving existing routes, permissions, and case actions.
- Expanded case detail tests to cover the new identity header content, sparse clinical state, vitals empty state, and header summary context values.

## 2026.03.05.23.46
- Added a dedicated `Case Header Background` theme control so the patient case identity header can be styled independently from the top navigation bar.
- Updated the case detail page and Theme settings preview to use the new case-header token while preserving existing nav text and control colors.
- Expanded theme tests to cover the new token mapping, persistence, and case-detail rendering behavior.

## 2026.03.05.23.03
- Rebases the global theme system onto the latest `main`, preserving the newer dashboard, case list, and action-first case detail layouts while keeping theme tokens and the admin Theme settings page.
- Added the global `ThemeSettingsView` back on the rebased branch and restored themed category colors in universal search, case detail, case list, dashboard summary cards, and the shared base shell.
- Standardized hard-coded status and task colors in the rebased case detail view to theme tokens, kept Django `error` messages mapped to themed danger alerts, and preserved the latest search/nav behavior from upstream.
- Kept the new `/patients/settings/theme/` workflow, per-category colors, migrations, tests, changelog links, and user-facing Theme page on top of the updated repo.

## 2026.03.05.21.22
- Delivered Issue #47 as a single integrated update: action-first case detail workflow with prominent actionable tasks, inline quick task actions, unified clinical timeline filters, and task-linked call logging requirements.
- Added backend contract support for timeline/event reliability: `CaseActivityLog.event_type` (`SYSTEM`, `TASK`, `NOTE`, `CALL`) with migration backfill, explicit activity typing on writes, and task quick-action endpoints:
  - `/patients/tasks/<pk>/quick-complete/`
  - `/patients/tasks/<pk>/quick-reschedule/`
  - `/patients/tasks/<pk>/quick-note/`
- Updated case detail behavior and rendering:
  - Query params `timeline=all|calls|tasks|notes` and `show_logs=1` for timeline filter/expansion.
  - Master task list with status filtering (`open`, `completed`, `cancelled`) and mobile-first card rendering below `768px` while preserving desktop tables.
  - Mobile action center collapsible panels and improved visibility of inline task actions without horizontal table dependency.
- Rolled out global semantic theming and base surface updates across shared UI:
  - Deep navy navigation, cool blue-gray surfaces/borders, and standardized text scale.
  - Consistent semantic pills/tags for gender, high-risk, categories (ANC/Surgery/Non-surgical), cancelled state, progress, and completed-row styling.
- Improved case creation and validation UX with inline required-field feedback (`is-invalid` + error text) and first-error scroll/focus behavior.
- Enforced timezone policy and display consistency by setting `TIME_ZONE = "Asia/Kolkata"` with `USE_TZ=True` (UTC storage preserved).
- Expanded test coverage for migration/backfill, action-first case detail sections, quick-action permissions/rules, timeline filters, call-task requirement, semantic render classes, mobile/task-list markup, and validation feedback behavior.

## 2026.03.03.23.01
- Added safety confirmation for destructive mock seeding: `seed_mock_data --reset-all` now prompts interactively and requires `--yes-reset-all` in non-interactive runs.
- Updated the Seed Mock Data settings page to enforce reset-all confirmation before command execution and pass `--yes-reset-all` only after explicit user confirmation.
- Reworked vitals seeding to generate deterministic, richer timelines (smoke=4 points, full=6 points) aligned to past relevant task dates with realistic OPD-time recordings.
- Expanded seed/settings tests to cover reset-all guardrails, reset-all UI command wiring, vitals density by profile, vitals date alignment, and deterministic vitals replay across reset runs.

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
