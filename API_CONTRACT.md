# MEDTRACK mobile API compatibility contract

The generated OpenAPI document at `/api/schema/` is the machine-readable source of
truth for the mobile API. This file records security-sensitive semantics that clients
must preserve across generated DTO or sync changes.

## Case edits

`PATCH /api/cases/{id}/` is a true partial update:

- An omitted field retains its current server value.
- An explicitly blank or null value clears a field when that field permits clearing.
- A supplied list replaces the current list; omitting the list preserves it.
- The response contains `case`, the display summary, and `editable_case`, a complete
  post-write snapshot of every editable field.

Both `GET /api/cases/{id}/edit-form/` (`case`) and a successful PATCH
(`editable_case`) return the same editable field set: patient selection and identity,
category/subcategory/status, diagnosis/referral/notes, risk fields, ANC fields,
surgical pathway, `surgery_done`, surgery/review dates, and obstetric counts. Clients
must not synthesize defaults for omitted fields; in particular, absence must never be
converted to `surgery_done=false`.

## Notifications and FCM

Stored and pushed notifications use generic copy. FCM data contains only:

```json
{"event_id": "opaque UUID"}
```

The event ID is opaque. No patient, case, task, phone, risk, or notification-detail
field is sent in either the FCM notification or data payload. A client must authenticate,
pass the current account/scope/auth-version checks, and fetch the notification API before
showing authorized detail. Notification list, mark-read, and send paths check the current
user, case, task assignment, and task state. `FCM_ENABLED` remains false by default.

`GET /api/notifications/` is a stable authorized-snapshot traversal:

- Query parameters are `cursor`, `page_size` (default 50, maximum 100), `type`, and
  `unread_only`. Legacy `page` requests return HTTP 400.
- The response is `dataset_epoch`, opaque `next_cursor`, and `results`; it has no
  count or page URLs.
- Cursors are bound to account, dataset epoch, role/auth version, filters, ordering,
  and the first-page snapshot boundary. Filter or role/auth-version changes invalidate
  the cursor with HTTP 400. Rows inserted after page one appear only on a new traversal.
- Current-object authorization is rechecked and stale rows are purged on every page.
  Assignment or terminal-state revocation removes the row while allowing the remaining
  authorized snapshot traversal to continue. At
  `next_cursor=null`, the returned/seen event IDs are the complete authorized snapshot
  for that account and epoch. Clients delete unseen local notifications. A changed
  dataset epoch invalidates the prior notification snapshot, cache, and outbox.
- Notifications expire after 30 days. Creation and snapshot traversal opportunistically
  delete expired rows in bounded batches. Completing or cancelling a task immediately
  removes its task notifications; reopening an assigned task emits a fresh assignment
  event.
- Password, account, role-policy, role-membership, and device-security changes advance
  the auth version and deactivate registered mobile push tokens.

## Idempotent writes

The supported write endpoints accept an optional `client_write_id`. A receipt is kept
for seven days and is bound atomically to the authenticated user, operation, route
target, canonical request payload, current authorization fingerprint, and dataset
epoch. Exact retained retries reconstruct a response from the currently authorized
object. Reuse with any changed binding returns HTTP `409` with
`code=idempotency_mismatch`; a concurrently pending write returns HTTP `409` with
`code=idempotency_in_progress`.

Receipts contain hashes, status, expiry, opaque result identity, and a generic message,
not a stored clinical response. Expired receipts are opportunistically deleted in
bounded batches during ordinary idempotent write traffic. Assignment, role, deletion,
and dataset replacement events purge affected receipts. Dataset replacement also
advances the epoch and deactivates mobile tokens, so clients must discard
pre-replacement queued writes.

## Patient search

Patient search is POST-only. `GET /api/patients/` returns HTTP 405 and never accepts a
search value in the URL.

`POST /api/patients/` accepts JSON containing required `query` (3 to 80 characters),
optional `page_size` (default 10, maximum 20), and optional opaque `cursor`. It is
throttled to 30 requests per minute per authenticated user. Matching uses UHID/name
prefixes or an exact normalized 10-digit phone under the current object/intake scope.
Results are ordered by UHID then ID and contain only `id`, `uhid`, and `name`.

The response contains only `next_cursor` and `results`. The cursor is bound to the
normalized query, ordering, account, and authorization scope; reuse for another query
or scope returns HTTP 400. Clients must send every subsequent cursor in the JSON body,
never in a URL.

Every accepted or rejected POST search writes a PHI-safe audit event with actor,
request/session/device context, normalized search class and length, result count,
current role scope, and outcome. The raw search value and patient identifiers are never
stored in audit metadata.

## Client event time

Call `attempted_at` and vital `recorded_at` values may be at most five minutes in the
future and 30 days in the past. Call responses expose the client-supplied time as
`client_event_at`; `created_at` is the immutable server receipt time. Vital responses
similarly expose `recorded_at` and `server_received_at` separately.

## Contract validation

Generate and strictly validate the schema with:

```powershell
python manage.py spectacular --file schema.yml --validate --fail-on-warn
```

Schema warnings or duplicate operation IDs are release-blocking contract failures.
