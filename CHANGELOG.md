# Changelog

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
