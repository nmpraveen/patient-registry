# Changelog

## 2026.03.22.20.49
- Refined the case-detail hero so the status pill now hugs the patient name, the redundant `View Patient` text link is removed, and the corner patient action remains the single patient-navigation entry point.
- Reworked the case-detail hero action cluster into a compact centered 2x2 button block, removed the extra sibling-case strip, and normalized all four hero actions to the same unhighlighted visual treatment.

## 2026.03.22.19.36
- Introduced patient master records keyed by UHID so one patient can hold multiple cases, with patient-aware search, patient pages, merge controls, migration support, and patient-aware import/export plus seed data.
- Reworked the New Case flow into a patient-first intake with live existing-patient search, cleaner selected-patient summaries, patient-linked case detail context, and updated theme-aligned patient UI.
- Fixed existing-patient case creation so hidden identity fields no longer block save, the Save Case path submits reliably again, and regression coverage now includes existing-patient creates with omitted hidden identity fields.

## 2026.03.22.16.17
- Moved the Surgery and Medicine subcategory selector on the New Case page into Step 1 directly under the category choices, so staff can fill it immediately after selecting the case type.
- Kept the HTMX preview refresh aligned with the new layout by rendering the relocated subcategory field through its own out-of-band partial, and removed the duplicate Step 3 subcategory control from the workflow panel.
- Added focused regression coverage for the New Case preview fragment so Surgery still renders one subcategory field in the Step 1 fragment ahead of the workflow panel.

## 2026.03.22.15.55
- Added structured case prefix support with `Mr.`, `Ms.`, and `Mrs.` across the New Case, Quick Entry, and Edit flows.
- Stored prefixes as their own case field, included them in displayed full names, and kept compact initials and short-name displays focused on the patient’s actual name.
- Extended seed/mock data, patient-data bundle import/export, and regression coverage so prefixes persist correctly while legacy blank-prefix cases are required to choose a prefix when edited.

## 2026.03.22.14.12
- Adjusted the stacked case-detail layout so mobile and other collapsed-width views now prioritize the working flow as hero, Action Center, tasks, timeline, vitals, and then clinical details, while preserving the desktop 40/30/30 module row.

## 2026.03.22.14.01
- Reworked the case-detail page into the new hero-plus-module layout, with Action Center, Vitals, and Clinical Details grouped in a responsive top row while preserving the existing task workspace, timeline, routes, permissions, and inline editors.
- Removed category tinting and leftover gradient treatment from lower case-detail surfaces so the hero remains category-aware while the surrounding modules use a cleaner neutral shell style aligned with the Vitals card.
- Redesigned the Action Center into a left-rail Task/Call/Note workspace with inline panes, simplified forms, and typography/spacing aligned more closely with the Vitals module while keeping the existing AJAX workflows and interactions intact.
- Finalized the Action Center polish with refined pane spacing, balanced controls, and updated call-form copy.

## 2026.03.22.02.53
- Fixed the case-detail hero metadata separators so patient profile pages render clean middle dots again instead of mojibake characters between UHID, sex, age, place, and phone.
- Replaced the affected case-detail CSS bullet literals with stable Unicode escapes to prevent the same symbol corruption from reappearing during future stylesheet edits.

## 2026.03.22.02.24
- Inverted the shared `Open case` external-link SVG to a white circle with dark linework, and added a subtle dark rim so the icon stays legible on the light action button background.

## 2026.03.22.02.23
- Replaced the shared dashboard `Open case` arrow with the provided external-link SVG so Today, Upcoming, Recently Added, and Overdue actions all use the same icon asset with tighter sizing.
- Updated the dashboard regression to verify the shared `Open case` style references the shipped SVG asset instead of the old text-arrow rule.

## 2026.03.22.02.13
- Removed the extra helper sentences from the navbar category-filter dropdown and aligned the Theme Settings preview with the slimmer filter panel copy.
- Restored the Today dashboard card call-history emoji markers so confirmed, unreachable, invalid, lost, callback, and untouched cases render with the familiar symbol shorthand again.
- Fixed the shared dashboard `Open case` action glyph by replacing the broken arrow character with a stable CSS escape so the link renders cleanly everywhere the shared style is used.

## 2026.03.22.01.55
- Shifted the top navbar onto a mockup-style palette by updating the built-in nav defaults to a warm white surface with navy brand text and muted gray controls, while preserving existing user-customized themes through a guarded migration.
- Re-mapped the navbar actions so `Quick Entry` now uses the green dashboard-today palette, `New Case` uses the dark case-header accent, and the funnel active state uses the danger palette for clearer filter emphasis.
- Updated the Theme Settings preview and regression coverage so the redesigned navbar preview, dashboard-only nav stats row, and new top-bar hooks stay aligned with the live app.

## 2026.03.21.21.53
- Normalized the remaining shared, dashboard, case-create, and case-detail UI colors so those pages now derive their visible surfaces, borders, pills, and status treatments from theme variables instead of hardcoded literals or Bootstrap fallback colors.
- Replaced dashboard call-status emoji and flag badges with theme-driven status pills/chips, keeping those colors under the existing alert, case-status, and shell theme controls.
- Wired hidden framework fallbacks into the theme system by theming `btn-outline-warning` and `alert-secondary`, then expanded dashboard and theme regression checks to catch these routes and status styles.

## 2026.03.21.21.30
- Extended Theme Settings coverage so gender-tag colors are now editable alongside the existing search/dashboard/status/category palette controls, and fixed the theme preview script to include the missing `Recently Added` pair plus the new search-tag pairs.
- Rewired the live UI away from several hardcoded colors by moving base gender chips, vitals pages, dashboard call/open-case pills, case-create GPLA controls, and the currently rendered case-detail hero/vitals/composer surfaces onto theme, status, and category variables or colors derived from them.
- Added direct `Open Theme Settings` shortcuts across the remaining admin settings subpages and expanded regression coverage for the new Theme Settings fields and subpage links.

## 2026.03.21.21.13
- Replaced the built-in default theme palette so the shell, nav, case header, buttons, alerts, status pills, search accents, and vitals charts now follow the new warm neutral plus green, blue, red, purple, orange, teal, and indigo color family from the provided reference.
- Updated the default ANC, Surgery, and Medicine category colors so fresh environments and Theme Settings `Restore Defaults` use the new orange, teal, and indigo palette by default.
- Added a guarded category-color migration so existing canonical category rows pick up the new defaults only when they still match the previous built-in palette.

## 2026.03.21.20.49
- Fixed the Awaiting Reports expanded-detail label contrast so the header and field labels now render with a dark readable color against the lighter tinted row surface.

## 2026.03.21.20.45
- Restyled the shared dashboard `Open case` action into a clearer bordered button with white fill and trailing external-link icon, and applied the same action treatment to Upcoming rows.
- Removed the extra helper copy from Recently Added expanded rows so they now open directly into a `Notes` header row with right-aligned subcategory and `Open case` actions.
- Reworked Overdue and Awaiting Reports expanded rows to use the same clean header structure, with a left title, right-aligned actions, and a more consistent detail body layout.

## 2026.03.21.20.30
- Kept expanded dashboard detail actions pinned to the top-right, including the shared subcategory plus `Open case` pill treatment and the inline Today diagnosis row action layout.
- Removed the mobile stack-forcing behavior from the Today detail header line so the diagnosis row can wrap naturally while keeping the pills aligned to the right edge.
- Anchored Upcoming row actions to the top-right of each row and preserved the compact summary separators for Recently Added, Overdue, and the new expandable Awaiting Reports rows.

## 2026.03.21.20.09
- Restyled dashboard patient rows across Today, Upcoming, Recently Added, Overdue, and Awaiting Reports to use a flatter category wash, a flush 5px left stripe, and a crisp category-colored border that reads as one continuous unit.
- Converted compact row names and Upcoming row names into category-colored pills so the patient label becomes the primary visual anchor, matching the new structural row treatment from the design reference.
- Kept the existing module behaviors intact while tightening the overall row presentation into a cleaner clinical card pattern with lighter shadows and more consistent category emphasis.

## 2026.03.21.19.33
- Increased the dashboard category tint again so the row shading reads more clearly across the dashboard while the left-edge accent stays subdued.
- Added an explicit `Hide` action to the inline call reveal and kept outside-click plus `Escape` dismissal, so Today and Overdue call trays now have an obvious close path.
- Kept the expanded subcategory pill pinned at the top-right, preserved Today's single-line `Diagnosis : ...` and `Tasks : ...` rows, and limited Upcoming row badges to real subcategory text only.
- Updated the focused dashboard regression checks for the subcategory-only Upcoming badges and the new inline call tray close affordance.

## 2026.03.21.19.26
- Increased the dashboard row category tint substantially so Today, Recently Added, Overdue, Upcoming, and Awaiting rows now read more clearly by category without relying on the narrow edge accent.
- Added outside-click and Escape-to-close behavior for the inline call reveal, while keeping the existing in-row phone number plus call action pattern for Today and Overdue.
- Moved expanded subcategory pills into a clearer top-right badge treatment, tightened Today details into true single-line `Diagnosis : ...` and `Tasks : ...` rows, and limited Upcoming row badges to actual subcategory text only.

## 2026.03.21.19.09
- Refined dashboard row styling with softer full-row category tinting, subcategory pills in expanded details, and stronger visual consistency across Today, Recently Added, Overdue, Upcoming, and Awaiting Reports.
- Updated Today and Overdue rows to use inline call reveal actions plus bottom-right `Open full case` links in expanded details, while moving the Today date into the module title.
- Reformatted Recently Added compact summaries to `Name | F30 | Mon DD`, moved the recent-case full-case action into the detail footer, and changed Upcoming rows to use explicit `Open full case` actions instead of full-row navigation.
- Expanded dashboard regression coverage for the new summary formatting, today detail/footer behavior, upcoming explicit actions, and the extra dashboard payload fields used by the updated UI.

## 2026.03.21.16.41
- Changed Quick Entry subcategory rendering to stay hidden until the selected category actually exposes subcategory options, so non-configured categories no longer show a disabled control.
- Made the Quick Entry subcategory option payload/help text option-driven rather than Surgery/Medicine-only, so future categories can surface the same field automatically as soon as subcategory choices are configured.
- Added regression coverage for the hidden-by-default quick-entry state and the visible-on-category-rerender path while preserving optional save behavior for known quick-entry subcategories.

## 2026.03.21.16.36
- Added the optional Surgery/Medicine subcategory field to the Quick Entry form, including client-side category-sensitive dropdown population so staff can capture a known specialty without switching to the full form.
- Kept Quick Entry subcategory optional on save while preserving the existing blank-subcategory path for minimal entries, and added regression coverage for both blank and explicitly selected quick-entry subcategories.

## 2026.03.21.14.51
- Added persisted Surgery and Medicine case subcategories, including category-specific validation, workflow form controls, preview/edit-summary support, migration backfill for existing records, and UI rendering on case detail, case list, and universal search.
- Kept Quick Entry lightweight by allowing blank subcategories there, while preserving `Phone pending` fallback rendering and ensuring quick-entry Surgery/Medicine records still import/export safely.
- Updated patient-data bundle import/export, mock seeding, admin list display, and regression coverage so subcategories round-trip correctly, legacy bundles default missing full-entry subcategories to the requested general values, and seeded demo data includes populated Surgery/Medicine subtypes.

## 2026.03.20.23.10
- Fixed the compact vitals tile alignment on the case-detail page so the emoji, label, and value content now anchor left inside each stat tile instead of inheriting centered badge-style positioning from the shared vitals tier utility.

## 2026.03.20.23.02
- Fixed the compact vitals tile emoji regression on the case-detail page by passing the icon field through the vitals summary payload and replacing the corrupted source literals with safe Unicode escape values, so the rendered tiles now show the intended `💓`, `🫁`, `⚖️`, and `🩸` icons reliably.

## 2026.03.20.22.59
- Added the missing mockup emojis to the case-detail vitals stat tiles so Pulse, SpO2, Weight, and Hemoglobin now render with `💓`, `🫁`, `⚖️`, and `🩸` instead of text-only shorthand.
- Compressed the vitals card sizing by reducing tile padding, value sizes, hero sizing, and tab/header spacing so the sidebar module sits closer to the rest of the case-detail typography instead of reading oversized.

## 2026.03.20.22.52
- Reworked the case-detail vitals module into the requested tabbed `Patient Vitals` card with `Snapshot`, `Trends`, and `History` views, a header `+ Add` action, a BP hero card, compact 2x2 metric tiles, and an inline history preview that links to the full vitals route.
- Updated vitals comparison and history payloads so the case page now renders latest-vs-previous trend rows and a compact recent-history table without bringing back the older stacked sidebar layout.
- Switched vitals status handling on the case page to the requested exact three-tier clinical thresholds and colors for blood pressure, pulse rate, SpO2, and hemoglobin, while keeping weight neutral and preserving the existing paired BP storage fields plus inline add/edit flow.

## 2026.03.20.18.15
- Rebuilt the case-detail vitals sidebar into a modern two-surface module with a combined `Blood Pressure` snapshot, compact recent-readings history, and always-visible vitals actions.
- Added an inline sidebar vitals editor for add/edit flows, replaced the BP preset dropdown with paired systolic/diastolic inputs, and updated vitals create/edit views to support the shared AJAX response contract while preserving full-page fallbacks.
- Refreshed the dedicated vitals history route to use one combined blood-pressure chart plus a cleaner audit table, and updated theme settings/preview/token compatibility so legacy BP chart colors map into the new `blood_pressure` chart token.

## 2026.03.20.04.36
- Kept mobile Actionable Task buttons on a single row, tightened their card layout, and switched overdue accents and pills to a clearer red treatment that matches the requested mockup more closely.
- Moved the shared task reschedule/note editor into per-task inline anchor slots so it now opens directly under the clicked actionable row or mobile card instead of below the full task list.
- Removed the case-detail `Upcoming queue` sidebar module and deleted the old task helper copy that was no longer wanted in the task workspace/editor flow.

## 2026.03.20.04.17
- Rebuilt the case-detail `Actionable Tasks` and `All Tasks` module into the new cleaner desktop table plus mobile card system, with overdue/focus/total counters, urgency strips, dot-status pills, and a collapsed full-history section.
- Replaced per-row task reschedule and note collapses with one shared in-page task editor panel that powers both desktop and mobile task actions while keeping the existing AJAX endpoints and task-selection logic unchanged.
- Added regression coverage for the new task-module DOM contract, including the shared editor, collapsed history toggle, mobile task lists, locked future ANC actions, and the updated case-detail datepicker markup.

## 2026.03.20.03.31
- Tightened the case-detail Action Center follow-up styling so the idle task, call, and note cards separate more clearly from the workspace background while preserving the new compact mockup layout.
- Limited the case-detail `Log Call` task selector to upcoming open tasks only, excluding overdue, completed, and cancelled tasks from the in-page call workflow.
- Adjusted the mobile Action Center open-state scroll behavior so opening a form keeps the three action cards visible instead of jumping the viewport down to the form body.

## 2026.03.20.00.08
- Rebuilt `/patients/cases/<id>/` into a modular case workspace with dedicated case-detail assets, a compact patient hero, category-aware surface tinting, stronger task focus, richer clinical sidebar cards, and purpose-built desktop/mobile layouts.
- Added inline case-page action flows for quick task creation, note capture, call logging, task completion, rescheduling, and timeline/log jumps while preserving the existing Django routes, permission checks, and non-JavaScript fallbacks.
- Expanded case-detail summary data and regression coverage so the redesigned page keeps long-name handling, vitals empty states, progress counts, risk/category metadata, timeline behavior, and AJAX response paths under test.
- Updated the local Test NNH startup workflow so same-LAN devices can open the demo server by LAN IP, and passed `CSRF_TRUSTED_ORIGINS` through Docker Compose so the mobile-login path works with that local workflow.

## 2026.03.19.17.05
- Expanded admin `Case Management` so each case now offers both `Archive` and `Delete Permanently` actions instead of delete-only handling.
- Added a real archive state on cases, hid archived cases from the dashboard, recent cases, search/autocomplete, and the main case list, while keeping archived records available on the admin case-management page.
- Updated patient-data bundle export/import and regression coverage so archived cases keep their archive metadata during backup and restore.

## 2026.03.19.16.50
- Added an admin-only `Case Management` settings module and dedicated `/patients/settings/case-management/` page for reviewing stored cases and removing a case from the app.
- Built a two-step permanent-delete flow with an explicit confirmation panel before removal, plus linked-record impact counts so admins can see what will be deleted.
- Added regression coverage for case-management access control, search filtering, confirmation enforcement, and successful cascade deletion of linked case data.

## 2026.03.19.16.20
- Shifted the new `Recently Added` default again to a clearer primary-blue subtle palette so it stays visibly blue while remaining distinct from the cyan `Upcoming` module.

## 2026.03.19.16.19
- Tuned the new `Recently Added` dashboard default from a very light blue to a clearer medium-light blue so it separates more obviously from the cyan `Upcoming` module on the live dashboard.

## 2026.03.19.16.18
- Added a dedicated dashboard theme color pair for `Recently Added` so it no longer shares the same blue-cyan treatment as `Upcoming`.
- Wired the new `Recently Added` dashboard color into Theme settings and the live appearance preview so admins can adjust it later without editing code.

## 2026.03.19.16.09
- Increased the dashboard module shell tint so `Today`, `Recently Added`, `Overdue`, `Awaiting Reports`, and `Upcoming` separate more clearly at a glance instead of reading as nearly identical white cards.
- Strengthened dashboard module and upcoming-schedule border treatments, and slightly intensified the Upcoming day-chip fill so the page hierarchy is easier to scan without changing the existing theme tokens.

## 2026.03.19.13.13
- Rebuilt `/patients/cases/<id>/edit/` to match the new case-intake visual system with the same split shell, category tiles, create-style field cards, ANC GPAL stepper controls, sticky summary rail, and mobile save bar while keeping edit-specific behavior intact.
- Added edit-only HTMX preview and duplicate-identity helper endpoints so draft workflow changes and self-excluding UHID/phone warnings refresh live without implying that starter tasks will be recreated.
- Upgraded the edit summary rail into a true pending-changes panel so unsaved GPAL, risk-factor, workflow, and note edits are called out in red with before/after diffs and added/removed list details.
- Expanded the edit preview refresh wiring and regression coverage so more draft field changes immediately appear in the summary rail, and restored a hidden global-search help string needed by the authenticated layout test suite.

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
