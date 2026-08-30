# Android API Contract Coordination

The Android joins in this lane are pinned to the merged server contract in
`origin/main` (API PR #99 plus Android security PR #102). The final branch is
rebased on the exact main head recorded in the PR and its DTO tests reject
field-name or transport drift.

## Authentication and device policy integration gate

The merged account-security implementation owns this boundary. Android parses
the required `/api/me.data_scope`, accepts targeted first login only as a strict
HTTP 202 `PENDING` response, and keeps the one-time mobile device secret in its
dedicated Keystore-backed credential store. An approved login is committed only
when access and rotated refresh JWTs bind the same account and exact
`mobile_device_id`. The FCM registration token remains a separate credential.

## Case partial edits

Android retains the complete edit-form baseline and uses a three-state update
DTO: omitted, value, or explicit JSON null. It sends only fields changed by the
user and sends `base_updated_at` plus `base_values` for every touched field.
The response contract requires an authoritative complete `editable_case`.

1. The case edit-form payload includes an explicit, non-null
   `case.surgery_done` Boolean for Surgery cases.
2. PATCH has true partial-update semantics for every field: an absent key
   preserves the stored value. Explicit clearing must be distinguishable from
   omission for nullable fields.
3. PATCH returns `editable_case`, whose complete editable field set includes
   `surgery_done`, so the client can refresh from authoritative state.
4. Server and Android tests prove an unrelated partial edit cannot change
   `surgery_done`, patient date of birth, alternate phone, or any other omitted
   field.

`ApiContractDtoTest` rejects an incomplete editable snapshot, pins omission
versus explicit-null serialization, and verifies the optimistic baseline fields
for case, task, and vital PATCH payloads.

## Notification snapshot reconciliation

`GET /api/notifications/` accepts opaque `cursor` and optional `page_size`
(default 50, maximum 100), plus the existing `type` and `unread_only` filters.
Legacy `page` is invalid. The response is
`dataset_epoch`, `next_cursor`, and authorized generic notification results,
ordered by `created_at DESC, id DESC`. The cursor is filter-bound and preserves
the first-page snapshot boundary. It is also bound to page size/order,
actor/account/scope/auth version, filter identity, and epoch. Authorization is
re-evaluated on every page.

Android requests 100 rows, follows `next_cursor` until null, rejects repeated
cursors, and deduplicates by opaque `event_id`. A known `invalid_cursor` or an
epoch change discards the partial traversal and permits one restart from page
one; a repeated reset fails closed. Only a terminal traversal atomically
replaces the owner-qualified local snapshot and deletes unseen revoked rows. A
changed epoch also clears that owner's notification-read outbox.

`event_id` is the idempotent notification identity for traversal deduplication.
Android preserves the server `created_at` value and does not synthesize a local
clinical timestamp. Raw FCM content is ignored for display and deep linking:
the client posts no system notification and only accepts the exact data-only
envelope `{"event_id":"<opaque UUID>"}` before queuing an authenticated API
sync. It rejects missing/invalid UUIDs, extra data keys, and notification
title/body payloads. The account-qualified worker revalidates `/api/me` before
clinical/notification reads and commits only for the same session incarnation
and Room account generation. No clinical lock-screen notification is produced.

## Search transport privacy

Android release builds emit no HTTP request logging. Debug logging is disabled
for the production flavor and, when enabled for dev/stage, logs only a redacted
method/path label with query strings and numeric object IDs removed.

Patient search is the breaking `POST /api/patients/` contract. Its JSON body is
`query` (required, 3..80 characters), optional `page_size` (default 10, maximum
20), and optional opaque `cursor`. The response is `next_cursor` plus minimal
`id`, `uhid`, and `name` results ordered by `uhid ASC, id ASC`. The cursor is
bound to normalized query, query class, page size/order, actor/scope/auth
version, and snapshot boundary. A known expired/invalid cursor clears partial
results and restarts once from `cursor=null`; repeated or unknown failures stay
closed. GET is rejected by the server, and Android has no
query-parameter search method, so names, UHIDs, and phones never enter a
patient-search URL. The server must enforce current patient scope on every page
and a 30/minute authenticated-actor throttle.

## Case-search integration

Non-search lists retain `GET /api/cases/` without `q`. Search uses only
`POST /api/cases/search/` with body fields `query`, `page_size`, `cursor`,
`bucket`, `assigned_to`, `scope_context`, `category`, and `subcategory`; the
response contains `next_cursor`, full case summaries, and stats. Android keeps
every filter fixed across cursor pages. A known `invalid_cursor` clears the
partial result and restarts once from `cursor=null`; it never falls back to a
PHI-bearing query URL.
