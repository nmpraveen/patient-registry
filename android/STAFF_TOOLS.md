# Staff tools — issue 113 Stage 5

PhoneBook, Reminders and Announcements are available from **Me → Staff tools**.
Home shows a static current announcement and due-reminder count when applicable.
These records are independent of clinical cases, tasks, sync receipts and patient bundles.

## Online behavior

The existing JWT/device session transport is reused. Staff data is held in memory,
bound to the verified account and session incarnation. It is cleared before account
commit and on logout/revocation. Old requests cannot repopulate a new session.
Entry, resume, pull-to-refresh and the Refresh button perform fresh reads; visible
screens refresh at least once a minute. Failed reads clear visible stale records.
No staff mutation is added to the clinical outbox and no external push is generated.

PhoneBook searches and pages the server directory, supports per-user favourites,
shows all numbers/extensions, and opens ACTION_DIAL. The extension is shown for manual
entry; the app does not place a call or require CALL_PHONE. Refreshing a deactivated
contact removes it from usable detail. Favourite PUT sends an explicit Boolean set.

Reminders show due notices, pending occurrences and completion history. Detail shows
the fixed anchor, recurrence, assignee and notice interval. Assignment selects active
staff and PATCHes the displayed definition version. Completing an occurrence sends
its definition_version; a stale first completion fails with 409. A repeat completion
is naturally idempotent after the server rechecks current scope. The client never
advances recurrence, creates a local occurrence, or owns scheduling. Lost responses
are reconciled by Refresh; writes are not silently retried with a new baseline.

Announcement audience, scheduling and expiry are enforced by normal consumption
endpoints, never management queries. Server time plus monotonic request elapsed time
controls inclusive start/exclusive expiry, conservatively including response transit.
Expired rows disappear within the one-second UI tick and trigger a fresh request.
There is no ticker or animation. Missing/invalid server time fails closed.

## Integration and verification

Network additions are isolated in StaffOperationsApi/StaffDtos; MedtrackApi inherits
that interface so the existing security transport remains the single implementation.
Clinical test fakes explicitly reject unexpected staff operations. No Room migration,
dependency, minimum API change, or clinical payload change is introduced.

Focused tests cover directory/favourite and completion wire contracts, server time,
stale session/request rejection, failed-refresh clearing, inactive contacts, version
preservation, dialer sanitation and expiry boundaries/response latency. Integrated
Stage 5 must run the affected Android unit targets and lint, then perform synthetic
emulator smoke after the true Stage 4 predecessor is integrated. Local implementation
and unit checks do not constitute production or physical-device acceptance.


### Current profile authorization and shared transport

Staff tools require `GET /api/me/` capability `staff_operations: true`. Unknown
profiles and older responses without this additive capability remain disabled,
even if role names or `manage_settings` suggest staff access. The verified profile
activates the session only after account commit. Home, Profile and direct staff
navigation observe that authorized session. A refreshed profile denying access or
a staff HTTP 403 clears all staff content and ends polling; a new verified allowed
profile can enable it again. Session/request guards still discard obsolete results.

Staff operations reuse the account's existing `MedtrackApi` instance, including its
single refresh authenticator and rotating-token lock. Automatic token refresh also
publishes its verified profile for current staff permission changes. This change
does not alter the separate background sync client architecture.
