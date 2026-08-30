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
{"event_id": "opaque UUID", "type": "notification type"}
```

The event ID is opaque. A client must authenticate and fetch the notification API
before showing clinical details. Notification list, mark-read, and send paths check
the current user, case, task assignment, and task state. Revoked records may disappear
and clients must reconcile local rows accordingly. `FCM_ENABLED` remains false by
default.

## Idempotent writes

The supported write endpoints accept an optional `client_write_id`. A receipt is kept
for seven days and is bound atomically to the authenticated user, operation, route
target, canonical request payload, current authorization fingerprint, and dataset
epoch. Exact retained retries reconstruct a response from the currently authorized
object. Reuse with any changed binding returns HTTP `409` with
`code=idempotency_mismatch`; a concurrently pending write returns HTTP `409` with
`code=idempotency_in_progress`.

Receipts contain hashes, status, expiry, opaque result identity, and a generic message,
not a stored clinical response. Assignment, role, deletion, and dataset replacement
events purge affected receipts. Dataset replacement also advances the epoch and
deactivates mobile tokens, so clients must discard pre-replacement queued writes.

## Patient search

`GET /api/patients/?q=...` requires at least three characters, is throttled to 30
requests per minute per authenticated user, uses name/UHID prefix matching, and accepts
phone matching only for an exact 10-digit value. Results contain only `id`, `uhid`, and
`name`, with a default page size of 10 and maximum of 20.

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
