# Issue #113 Stage 1: follow-up visibility and ANC resolution

## Classification and units

Access scope is applied before classification, counts, search or assignment filters. Restricted roles keep their existing assigned/created/call-queue scope. An assignment preference cannot discard an otherwise accessible case with no open tasks.

`patients.follow_up` owns SQL predicates for web/API lists and counters. Open means SCHEDULED or AWAITING_REPORTS; completed/cancelled rows never make a case open. Active, unarchived cases without open tasks are dormant unless unresolved ANC has an effective EDD before the hospital date (Asia/Kolkata). That EDD remains overdue independently of tasks. EDD today is not overdue. USG EDD overrides the original EDD. Missing EDD has a separate review-needed indicator and is never assigned an invented overdue date.

Dashboard follow-up counters and API bucket counters count **cases**. The web follow-up list groups affected cases by Patient and paginates **patient groups**, keeping all affected cases together even when another case has open tasks. Legacy patientless cases each form a separate group. The existing dashboard task panels still count tasks and are labelled accordingly. API/native rows remain case-based, preserving existing pagination and old-client contracts.

Patient-group keys are paginated in SQL before loading the affected cases for that page. API list/search and follow-up queues include unarchived closed cases with retained open tasks, keeping case status and outcome intact. Closed taskless cases remain outside worklists; EDD-only overdue, dormant and missing-EDD classification still require an active case. Retained task overdue remains visible after closure until the task is explicitly completed or cancelled.

## Explicit actions

Full web case edits submit a signed baseline from the rendered page, bound to the case, editor and update timestamp. A later outcome, EDD correction or other case change makes the original page stale; the locked POST rejects it and requires reload. Missing/invalid baselines also reject without saving. API patch requests retain their separate existing baseline contract. ANC action visibility uses the normalized domain workflow, including mixed-case department names.

Case editors open **ANC outcome / EDD correction** from the case page or native detail. Delivery, loss to follow-up, referral and other resolution record an outcome date and reason. The outcome date is the delivery/referral date when that outcome is selected. Referral also requires a destination. Users explicitly choose continuing follow-up (active) or closing the case (completed, or loss to follow-up). Referral continuation is a recorded resolution of the pregnancy EDD attention; retained overdue tasks still require attention.

The form displays open tasks and a retain/cancel-selected policy. Retain is the default, including for closed cases; closing does not silently complete or cancel work. Only selected currently open tasks may be cancelled, and cancellation requires task-edit permission in addition to case-edit. Completed history is preserved. Existing Grey List transition restrictions remain enforced. Concurrent case updates are rejected using `base_updated_at`. Scoped writers lock a plain case row selected through an access-eligibility subquery; read-only ANC GET requests do not lock cases. Recent Cases notes/diagnosis writes refresh and update only those fields; full case-form saves lock and recheck their loaded version before saving, so intervening ANC actions cannot be overwritten.

Automatic RCH reminder generation stops for closed/archived cases and any recorded ANC outcome, including continuing referrals. Existing retained tasks stay unchanged. An explicitly cancelled reminder is not recreated by an unrelated web/API edit or a generic case reactivation. Resumption requires an explicit authorised task creation/reopen action under the existing task permissions.

EDD correction sets USG EDD and records before/after values, effective EDD before correction, actor, timestamp and reason in activity history. Every existing task date/status is retained, including generated, manually edited and completed tasks. There is no schedule regeneration or task-moving option. Initial intake EDD capture is unchanged. Existing case-edit endpoints reject changes to stored EDD fields with a message directing the user to this audited workflow; unchanged older client payloads remain valid.

Reclassifying a non-ANC case without a stored effective EDD permits initial ANC date capture. Existing ANC cases and any stored effective EDD remain protected by the correction guard. Grey transition permission checks retain the existing non-completed task predicate, including cancelled historical tasks, while attention and selectable cancellations use only scheduled/awaiting tasks.

`POST /api/cases/{id}/anc/` is additive and described in OpenAPI. Required controls: `client_write_id`, `base_updated_at`, `action`, `reason`, `task_policy`; outcome-specific fields are validated server-side. Native submissions use the existing authenticated account session and guarded encrypted cache commit. They are **online only** and do not enter the offline outbox. Retrying an unchanged submission reuses its write ID. Server replay rechecks current permissions/scope and stores only safe receipt metadata, using the existing idempotency framework. Old servers omit new DTO fields safely; the native action remains disabled without a server version timestamp.

## Migration, bundles and reconciliation

Loss-to-follow-up outcomes require closing the case across web/API/model/import validation; native does not offer continuing that outcome. ANC writes use the existing audited bulk-update boundary for only their clinical fields, avoiding Patient identity locks while preserving mandatory audit rollback.

Native ANC success waits for authoritative detail refresh. Selected cancellations become non-actionable as soon as the server acknowledges them, including when detail refresh subsequently fails; the old case baseline remains available for an idempotent retry until refreshed.

Django migration 0040 adds optional outcome/date/reason/destination and a follow-up choice without changing existing case statuses or task rows. Patient bundle v2 exports the new fields; current imports preserve them, and older bundles default to no recorded outcome. Shared form/model/import validation requires a nonfuture outcome date, nonblank reason, referral destination where applicable and an explicit boolean follow-up choice whenever an outcome is supplied. Malformed new outcome records reject the import transactionally without replacing existing patients. Full database backups naturally include the new fields. Do not use an older application to import a new bundle when preserving outcomes is required.

Room 12→13 adds defaulted case attention/outcome display and server version fields plus dormant case counts. Account ownership, generation checks, encryption and pending writes are unchanged. A sync refresh supplies the new display fields after upgrade.

Foreground and background sync both preserve follow-up/outcome display, server update timestamps and dormant counts, including detail refreshes and pending-write responses committed to Room.

Historical closed cases are never mass-reopened. Run the **read-only** inventory in an authorised environment:

```sh
python manage.py report_anc_reconciliation > anc-reconciliation.csv
```

The CSV lists closed ANC case/patient IDs, status, archive flag and effective EDD where no outcome is recorded. An authorised staff member reviews each record against source evidence; record an explicit outcome per case only when verified. Do not infer historical delivery from a due date or task status.

Deployment remains a separate operational gate. Migration is additive; before rolling back schema, export/backup outcomes because reversing 0040 removes those columns. Prefer rolling back application code while retaining the additive columns and the validated database backup. No production operations are part of this PR.

## Synthetic validation

Follow-up seed examples retain model-valid LMP/EDD pairs; the intentionally missing-EDD example uses supported quick-entry metadata. Synthetic quick-entry patients retain their profile surname so the complete seeded dataset round-trips through the standard bundle importer.

`patients.test_follow_up` covers date boundaries, missing EDD, mixed tasks, patient grouping, corrected EDD, cancellation/history, referral continuation/closure, forbidden IDs, scoped counts, stale updates, role distinctions, idempotent replay, web form submission, API search parity and bundle round trip. Existing full Django/API tests remain required.

```sh
python manage.py test patients.test_follow_up
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml
python manage.py seed_mock_data --count 12 --reset --follow-up-scenarios
# Set the synthetic demo_admin password explicitly; seed accounts have unusable passwords.
E2E_PASSWORD=<synthetic-password> PYTHONPATH=. python scripts/follow_up_smoke.py
```

Smoke artifacts: `output/playwright/issue113-stage1/`. The browser smoke checks five routes at 320/390/430/1440 widths and submits a correction plus continuing referral. Native tests validate additive DTO compatibility and every supported Room version through 13; Android unit/lint/release CI gates remain required. Local build/synthetic evidence does not establish Firebase or physical-device readiness.
