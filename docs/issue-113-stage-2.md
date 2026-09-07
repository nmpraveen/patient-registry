# Task editing and general patient calls

Stage 2 of issue #113 reuses the existing Django task form and native task sheet. Edit is visible in prominent task rows, including future ANC tasks whose completion remains locked. Editable fields are title, due calendar date, assignee user, status/type, frequency label and notes. Frequency is descriptive text, not a new recurring scheduler. Blank optional text clears it; unassignment clears the user FK. Task date controls use calendar dates without browser timezone conversion.

## Concurrent changes and clinical history

Full web task edits carry a signed baseline bound to the task and editor from the original GET. Missing/tampered/wrong-task/wrong-editor baselines fail closed. A save compares only the user's changed fields with the locked current task. Overlapping changes return 409 and preserve the draft; independent field edits retain each other's changes. Quick completion/reopen/reschedule compare original status/date; quick note compares original notes. Refresh is required after conflict; do not silently replace the original baseline and retry an old draft.

Web and mobile task writes recheck current authorization and scope, then serialize case/task updates. Existing future ANC completion, completed-to-Scheduled reopening permission, cancelled-task completion restrictions and RCH reminder effects remain enforced. Task changes and their clinical activity commit together. Full edits record changed before/after values, actor and timestamp; security audit records retain their existing limited metadata.

Mobile full edits and notes use the existing online PATCH with changed-only fields, original server `base_updated_at`, touched `base_values` and `client_write_id`. Current native quick notes use that PATCH as well. The old task-note endpoint remains supported with locked current-state mutation. Legacy clients cannot supply an unobserved baseline retrospectively; their original endpoint compatibility is retained, not misrepresented as full stale-editor detection.

New mobile completion requests may include `base_values` containing exactly observed `status` and `due_date`. A changed precondition returns 409; unrelated note edits do not. Old completion envelopes omit this optional object and retain the compatible locked action path. Completion replay precedes precondition checks, so retries do not add another activity.

## General patient calls

The web task selector's empty option is **General patient call**. A new taskless call requires **Reason for call** plus the existing outcome; notes remain optional. Calls attach to the selected case and therefore its patient. A task from another case is rejected. Saving a call creates no task and completes no work.

`reason` is a trimmed string with maximum 500 characters. New web and native taskless authoring requires a nonblank reason. In the mobile endpoint, an omitted reason is deliberately accepted for legacy clients and already queued taskless calls; explicit null is invalid, and explicit blank/whitespace is invalid for taskless calls. Task-associated calls may omit reason or send an empty string. No historical reason is invented.

Android's optional reason defaults to null and is omitted when reserializing legacy queued JSON. Old pending call/completion requests keep their original keys, write ID and attempted timestamp. New fields must never be injected during replay: a server-success/lost-response request must retain its receipt payload hash. Existing receipt authorization, device revocation, dataset epoch, owner-account and retry controls still apply. One call and one audit activity are stored; timeline presentation shows the call once.

Case detail and call-write responses share call serialization. `reason`, `task_title` and `staff_user` are additive strings; unknown historical values remain empty. `created_at` is immutable server receipt time; `client_event_at` is the optional captured attempt time. Native case call history and patient recent calls are bounded to the newest 20 ordered by receipt time then id descending. This is not the complete history; the Stage 4 combined timeline work remains separate.

## Migration, bundles and deployment boundary

Migration `0041_calllog_reason` adds an optional field with an empty legacy default; it does not backfill clinical reasons. Patient bundle version 2 adds reason to call records and imports older records without that key as empty. Existing version 1 compatibility, task references, actors, timestamps and dataset invalidation remain intact. Synthetic seed calls include reasons and both task-associated and taskless examples. Full database backups include the new field.

Source completion does not activate production. A release must first have the coordinated backend/schema and native compatibility checks. Keep an encrypted recovery backup before activation. Rollback should retain the additive schema and recorded reasons; reversing the migration deletes reason data. Earlier backend code can ignore the column but cannot record new reasons, so suspend new general-call authoring during such a rollback and restore compatible code before resuming. Do not infer live, Firebase, signing or physical-device acceptance from local tests.

## Verification

Focused contracts live in `patients/test_task_calls.py`; existing web task fixtures obtain their actual GET baseline. Coverage includes all edit fields, independent and overlapping edits, a PostgreSQL two-editor race, invalid baselines, atomic audit rollback, permission changes, legacy/current reason rules, cross-case IDs, receipt replay, bounded history and bundle reconstruction with/without reason. Existing API, scope, ANC/reopen, seed, bundle and security regressions remain required.

Run backend tests with `DEBUG=false` and `ALLOW_MOCK_DATA_SEEDING=false`; seed-specific tests use local overrides. Use isolated synthetic databases and the validated runtime. The Stage 2 report records exact test heads, browser/emulator evidence, migration checks and PR/review state; no production action is part of these tests.
