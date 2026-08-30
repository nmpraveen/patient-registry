# Android API Contract Coordination

This lane is based on server commit
`920357a58a69bd2e18ed03023a4273cd1493a066`, but its Android DTO tests pin the
breaking replacement contract coordinated with API remediation lane 2 / PR
#99. This document is intentionally separate from server implementation so the
two pull requests can be rebased without overlapping source changes.

## Authentication and device policy integration gate

Backend PR #103 is still under amendment. Its target identity includes JWT
access/refresh `auth_version` plus `/api/me` `data_scope`, rotating refresh
tokens with replay handling, and an explicit approved-mobile-device policy for
targeted accounts. Those DTOs and refresh/device tests are intentionally not
guessed in this lane. Lane 4 owns account/auth/local-security implementation;
lane 5 must be validated against PR #103's final exact head before integration.

## Case partial edits

At the base commit, the case edit-form response omits `surgery_done`, while the
PATCH endpoint treats omitted Boolean form data as false. That combination can
silently clear an existing surgery completion value when Android edits another
field.

Android now retains the edit-form baseline and uses a dedicated nullable update
DTO that sends only fields changed by the user. Fields omitted by the server are
therefore never converted from client defaults into destructive PATCH values.
For Surgery cases it additionally refuses to send any update when the server
did not provide `surgery_done`. This is a deliberate fail-closed compatibility
gate; no guessed Boolean is submitted.

The coordinated lane 2 contract provides all of the following; Android remains
fail-closed until the amended PR #99 head is available for exact integration:

1. The case edit-form payload includes an explicit, non-null
   `case.surgery_done` Boolean for Surgery cases.
2. PATCH has true partial-update semantics for every field: an absent key
   preserves the stored value. Explicit clearing must be distinguishable from
   omission for nullable fields.
3. PATCH returns `editable_case`, whose complete editable field set includes
   `surgery_done`, so the client can refresh from authoritative state.
4. Server tests prove an unrelated partial edit cannot change
   `surgery_done`, patient date of birth, alternate phone, or any other omitted
   field.

The contract test `ApiContractDtoTest` covers the legacy missing-field response,
the coordinated response, and the authoritative `editable_case`. After lane 2
merges, retain the nullable update DTO and fail-closed guard so a future schema
regression cannot be converted to a destructive default.

## Notification snapshot reconciliation

`GET /api/notifications/` accepts opaque `cursor` and optional `page_size`
(default 50, maximum 100), plus the existing `type` and `unread_only` filters.
Legacy `page` is invalid. The response is
`dataset_epoch`, `next_cursor`, and authorized generic notification results,
ordered by `created_at DESC, id DESC`. The cursor is filter-bound and preserves
the first-page snapshot boundary. It is also bound to page size/order,
actor/account/scope/auth version, filter identity, and epoch; any tampered,
stale-auth, or mismatched cursor must return 400/403 and is never silently
restarted by Android. Authorization is re-evaluated on every page.

Android requests 100 rows, follows `next_cursor` until null, rejects a repeated
cursor or dataset-epoch change mid-traversal, deduplicates by opaque `event_id`,
and atomically replaces the local snapshot only after traversal completes. This
removes unseen stale/revoked rows without exposing a partial page. A changed
dataset epoch also clears notification-read outbox entries in this lane; lane 4
owns the broader account-qualified cache/outbox security-boundary reset.

`event_id` is the idempotent notification identity for traversal deduplication.
Android preserves the server `created_at` value and does not synthesize a local
clinical timestamp. Raw FCM content is ignored for display and deep linking:
the client posts no system notification and only accepts the exact data-only
envelope `{"event_id":"<opaque UUID>"}` before queuing an authenticated API
sync. It rejects missing/invalid UUIDs, extra data keys, and notification
title/body payloads. The worker revalidates `/api/me` before
clinical/notification reads. Lane 2 must keep the server push payload opaque,
PHI-free, and data-only because an
Android notification payload can bypass `FirebaseMessagingService` in the
background. PR #103/lane 4 must bind `/api/me` identity/auth generation to the
account-qualified database before any authorized display is reintroduced.

## Search transport privacy

Android release builds emit no HTTP request logging. Debug logging is disabled
for the production flavor and, when enabled for dev/stage, logs only a redacted
method/path label with query strings and numeric object IDs removed.

Patient search is the breaking `POST /api/patients/` contract. Its JSON body is
`query` (required, 3..80 characters), optional `page_size` (default 10, maximum
20), and optional opaque `cursor`. The response is `next_cursor` plus minimal
`id`, `uhid`, and `name` results ordered by `uhid ASC, id ASC`. The cursor is
bound to normalized query, query class, page size/order, actor/scope/auth
version, and snapshot boundary. Invalid/tampered/stale-auth cursor use must fail
closed with 400/403. GET is rejected by the server, and Android has no
query-parameter search method, so names, UHIDs, and phones never enter a
patient-search URL. The server must enforce current patient scope on every page
and a 30/minute authenticated-actor throttle.
