# Stage 4: screens and case history

Upcoming now shows seven hospital-calendar dates beginning today. Later dates move
forward in seven-day windows. Each case/day is one row; multiple tasks expand to
show every title and assignee, including distinct tasks with identical titles.
Today, overdue and awaiting-report queues retain their existing status rules.

New Case is one expanded intake with identity/contact, department/diagnosis and
required workflow fields visible. Referral and notes are optional details. One
Save action submits the existing validated form. Existing-patient lookup and HTMX
draft preservation remain active; leaving a changed form prompts before discarding
it. Draft patient data is not stored in browser storage.

Case detail distinguishes patient identity from the selected case's department,
diagnosis, follow-up status and next action. The Clinical Timeline is expanded in
main content. Its All, Calls, Tasks, Notes and Clinical filters use canonical
records: CallLog supplies calls, mirrored CALL activity is excluded, task-note
activity belongs to Notes, and SYSTEM activity supplies clinical changes such as
case edits, outcomes, EDD corrections and vitals. Legacy case-detail payloads remain
compatible.

History pages contain at most 30 events, ordered by timestamp, source rank and
record ID descending. Exact timestamp precision is retained in the cursor;
display uses the hospital timezone. Each source query reads at most 31 records.
Opaque cursors bind the actor, authorization state, dataset epoch, selected case
and filter. Initial source-ID ceilings prevent newly inserted history from
appearing halfway through older pages. Refresh returns the latest history.

## Native read APIs

- `GET /api/upcoming/`: optional `start_date`, repeated `category` and
  `subcategory`, `assigned_to`, `scope_context`, and opaque `cursor`. Response
  includes hospital date/timezone, inclusive window and up to 50 task rows sorted
  by due date, case ID and task ID. Native groups by case/day and deduplicates by
  task ID across pages. Assignment filtering follows existing case-search
  semantics: it selects eligible cases, then shows their visible scheduled tasks.
- `POST /api/upcoming/search/`: the same filters in JSON arrays, plus a 3–80
  character `query`. Patient queries never belong in URLs. Existing search
  normalization, prefix identity/name and exact phone semantics are retained;
  audit metadata omits query content. Search uses the existing account throttle.
- `GET /api/cases/{id}/timeline/`: `filter` and opaque `cursor`; response contains
  canonical event IDs, labels, offset-aware timestamps, actor, task title,
  headline, reason and details, with `next_cursor` and hospital timezone.
- `GET /api/cases/{id}/related/`: up to 50 same-patient cases ordered by ID with
  department, diagnosis, status and `next_cursor`. Scope is applied to both the
  selected case and siblings. A legacy patientless case returns only itself.

Every page reapplies current access rules. Invalid, mismatched or expired cursors
require refresh. These APIs add no clinical mutation or permission grant. MTNO
continues to come exclusively from the Stage 3 server identity implementation.

## Synthetic verification

On an isolated scratch database with mock seeding explicitly enabled:

```sh
python manage.py seed_mock_data --count 8 --reset --screen-scenarios
python manage.py collectstatic --noinput
python scripts/stage4_screen_smoke.py --case-id <first-seeded-case-id>
python manage.py test patients.test_stage4
```

The browser script uses `E2E_USERNAME`/`E2E_PASSWORD` for a synthetic staff account,
one Chromium context and 320/390/430/1440 viewports. Its screenshots and receipt
are written to `output/stage-4/browser/`. It exercises group expansion, later
dates, timeline filters/paging, keyboard focus, unsaved/invalid intake and a real
synthetic save. The optional seed flag adds duplicate-title day groups, day-seven
and later tasks, general call reason and more than one timeline page. These local
checks do not establish production or physical-device acceptance.
