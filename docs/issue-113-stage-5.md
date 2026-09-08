# Stage 5 staff operations

PhoneBook, reminders and announcements use separate Django applications. They never create patient records or clinical tasks. Existing active staff with explicit RoleSetting membership, and active superusers, can read the directory and announcements addressed to them. A bare Django is_staff flag grants no access. Existing manage_settings capability controls contact maintenance and announcement publication.

## PhoneBook
/staff/directory/ provides search, per-user favourites, contact details, multiple labelled numbers/extensions and call links. Managers add/edit/deactivate contacts. Inactive contacts disappear from reader lists/details/favourite writes; managers can include and reactivate them. Existing favourites are retained through deactivation and return if reactivated.

The corresponding /api/staff/directory/ list/detail routes use existing revocable JWT authentication. Lists use fixed pages of 50, q (up to 100 characters), favourites=true and manager-only include_inactive=true. The paginated envelope includes server_now. PUT {id}/favourite/ accepts an explicit is_favourite boolean, making repeated sets idempotent. It never accepts another user's identity. Manager PATCH requires the current version; concurrent stale edits return 409. Contact DTO fields are id, name, role_specialty, organization, phones (label/number/extension), notes, is_active, is_favourite, version, updated_at. Phones are validated and capped at ten.

## Announcements
/staff/announcements/ provides an applicable current list and detail. Managers create/edit via new/ and {id}/edit/ and use ?manage=true to inspect all schedules/history. Text is plain escaped text, up to 2000 characters. Priority is normal, important or urgent. Audience is explicitly all_staff or selected_roles, with at least one selected RoleSetting. Managers and superusers do not implicitly match a selected-role announcement in normal consumption. They can inspect it explicitly in management mode.

Start is inclusive, mandatory expiry is exclusive: starts_at <= server time < ends_at, with is_active true. Web datetime inputs use hospital timezone Asia/Kolkata. Deactivation retains records. Publisher identifies the original publishing user; later edits are attributable in the audit log. Deleting that user retains an editable announcement with a null publisher, displayed as Former staff member.

The static banner shows the highest priority current applicable announcement, links to detail/list, refreshes every 60 seconds and on resume, and disappears on failed refresh. It has no ticker/motion. Open list/detail rows and banners drop at expiry using server-relative elapsed time.

/api/staff/announcements/ list/detail uses the same visibility predicates. Normal consumption orders urgent, important, then normal before pagination, with newest start and ID breaking ties. Management lists retain newest-first order. ?manage=true requires manage_settings. DTO: id, text, priority, audience, audience_role_ids, starts_at, ends_at, publisher ({id,name} or null), is_active, version, updated_at, server_now. Lists have fixed page-number pagination of 50 and server_now. Manager PATCH requires version; stale versions return 409.

## Reminders
/staff/reminders/ provides definition create/edit/detail, due notices, pending occurrences and retained completion history. Existing settings managers can manage all; other authorised staff can act only as current owner or assignee. Reassignment immediately removes the former assignee's access unless they are independently the owner or a manager. Active authorised assignee choices come from /api/staff/reminders/assignees/.

The /api/staff/reminders/ definition list/create and {id}/ detail/PATCH expose title, owner_id, assignee_id/name/active, due_date, advance_notice_days (0–365), recurrence, is_active, version, timestamps, can_edit and can_assign. PATCH requires version. Original due_date and recurrence are immutable after creation; deactivate/create a replacement to change the schedule. Recurrence is ONCE, MONTHLY, EVERY_TWO_MONTHS or YEARLY. Fixed calendar anchors clamp to the last valid day without drifting: Jan31 -> Feb28/29 -> Mar31; Feb29 yearly returns to Feb29 in leap years. Hospital date always uses Asia/Kolkata.

GET /api/staff/reminders/occurrences/?status=pending|completed|all|notices&reminder_id={optional-id} returns scoped occurrence identity, reminder_id, title, assignee, due_date/notice_date, completion actor/time, active state, can_complete and definition_version. POST occurrences/{id}/complete/ requires {version:definition_version} for first completion; stale assignment/content yields409. A completed replay returns original completion after rechecking current scope. Completion never changes the recurrence anchor. Lists use fixed50 pagination, server_now and server_today.

The first occurrence is created atomically with its definition. Later occurrences are generated only by the bounded schedule_staff_reminders command. It uses definition row locks, resumable indices and unique occurrence constraints. Inactive assignees pause future generation until reassignment. Completion history remains intact.

Source-only deploy/systemd/medtrack-staff-reminders.service and .timer provide a supervised minute-by-minute command with limit500 and per-reminder24. They are not installed or enabled by application startup or this source change. At an authorised deployment, install these units alongside existing MEDTRACK units, enable the timer, and verify successful journal output; monitor remaining_definitions and failures. Missed invocations catch up in bounded repeat runs. No external notification delivery is configured.

## Safety and data boundaries
All management writes use transactions and row locks, check fresh role capabilities after locking the actor, and recheck request authentication version before writing. The existing AuditEvent DATA category records actor/object/action/changed field names/version. No clinical timeline events are fabricated. Audit failure rolls back the write. Favourites have a database unique constraint on user/contact.

Browser no-store/CSP and existing session/device security remain in force. Native consumption is online and keeps only session-owned in-memory state, clears it on account change/revocation or failed refresh, refreshes on entry/resume/mutation, and enforces announcement expiry against server_now and monotonic elapsed time. No new notification provider, push delivery, Room migration or outbox format is implied by these apps.

Full PostgreSQL backups include all new operational tables, their foreign keys, favourites and audit records. Patient-data ZIP bundles intentionally exclude these apps and cannot restore them. Restore operational records with the full database recovery process.

## Synthetic seed
The existing seed_mock_data command now adds a synthetic switchboard contact, favourite, current staff announcement and every-two-months reminder. A standalone command seeds all three administrative apps:

```text
python manage.py seed_staff_operations --owner <existing-settings-manager>
```

Both require ALLOW_MOCK_DATA_SEEDING=true in an explicitly authorised test environment. Production remains false. The seed is repeatable and uses fictional 202-555-01xx numbers. It does not delete existing operational data.

## Integration status
All three backend apps and native consumers are integrated on the declared Stage4 source boundary. Actual Stage4 squash rebase, one combined Stage5 PR, exact-head review/CI, and production activation remain separate gates. Runtime packaging includes all three apps through the explicit Docker/build-context/image-scan allowlists.
