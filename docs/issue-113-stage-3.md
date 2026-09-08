# Permanent patient identity

Every Patient has one server-allocated MTNO, for example `MT-000123`. It stays the same when hospital UHID, contact details or case information changes. A patient with several cases has the same MTNO on every case. The normalized `MT-<digits>` namespace is reserved for permanent MTNOs, so it cannot be assigned as hospital UHID. Hospital UHID is optional; different patients with missing UHID remain separate. Names and phone numbers are search/duplicate-review hints, never automatic identity keys.

Register a patient with or without UHID. MTNO appears after saving; it cannot be typed or edited. Add a hospital UHID later through the existing patient/case identity editor. Existing hospital and legacy temporary identifiers remain intact. An incompatible legacy hospital identifier already in the reserved namespace stops migration for an explicit reviewed reconciliation decision; it is never silently rewritten or dropped. Legacy clients explicitly requesting a temporary identifier still work; current quick entry creates MTNO without manufacturing UHID.

Search accepts MTNO, UHID, name and phone within the existing role/access scope. Exact legacy MTNO/UHID aliases resolve to the permitted surviving patient after a merge. Source demographics and private issuance UUIDs are not exposed in alias results. Patient-search cursors use immutable IDs, allowing multiple blank-UHID rows to paginate. Clients must restart an invalidated opaque cursor. Case worklist order remains unchanged.

## Merge and recovery

Merge requires the existing merge capability and permission for every affected case. Confirmation uses the target MTNO. The source Patient and original MTNO are preserved; cases move to the target and display its MTNO. The original number becomes a traceable alias through the existing merge edge. Chains and re-merging a terminal target are not newly enabled.

The existing `recover_patient_merge` command remains restricted to active superusers and checks expiry, topology, intervening changes and immutable moved-case evidence. Recovery restores the source cases to the source MTNO; it does not allocate new numbers or alter the target identity. Expired or conflicting recovery requires the established verified full database recovery route. Ordinary identity edits/merges preserve mobile write receipts and pending outbox semantics; search snapshots restart and authorized case refresh receives current MTNO/UHID.

## Migration and data preservation

The additive sequence adds nullable identity fields and issuance state, backfills existing Patients (including merged records), then enforces mandatory immutable identity. The durable ledger binds MTNO to a private UUID and survives patient deletion and patient-only replacement. Allocation uses a database row lock and uniqueness constraints. The high-water mark only increases; it never resets to the maximum remaining Patient row. Numbers on uncommitted, rolled-back registrations have not been issued to a patient.

Existing nonblank legacy UHIDs are retained. Patientless cases may be linked only using unambiguous, exact nonblank identifiers and compatible existing evidence. All nonblank identity evidence across each complete orphan UHID group, including an existing Patient, is checked before links or issuance; a blank first row cannot hide conflicting later rows. Blank/conflicting identifiers or invalid merge topology stop migration pending a reviewed reconciliation mapping. No patient is inferred from shared names/phones; no blank-key grouping, fabricated demographics, clinical-history rewrite or task generation occurs during backfill. Migration 0044 refuses reversal before removing any guard or constraint, so a failed downgrade leaves identity enforcement and its migration record intact. Reverse migration cannot remove already issued identity; use a matching verified database snapshot with the outgoing identity checkpoint retained.

## Bundles and restore

The identity-aware bundle is schema 4, following Stage 2 schema 3 for call reasons. It retains import support for schemas 1, 2 and 3. Schema 4 links cases and merges by MTNO, supports blank UHID, and carries issuance bindings/high-water metadata. Older formats require explicit nonblank UHID mapping and cannot prove historical MTNO continuity by themselves. Conflicting number/UUID bindings and reserved-namespace UHIDs reject before replacement in every supported format. Import takes the shared dataset gate before allocation and Patient/Case locks; API keyed writes, unkeyed writes and receipt replay take the same gate before actor and target locks. Existing case editors retain Patient-before-Case locking and recheck current linkage. Outcome/task/call history continues to round-trip.

Patient-only import rejects before deletion if replacement would invalidate protected local merge-recovery evidence. It can export merged identities and import them into an eligible fresh target; it does not invent historical audit evidence or recreate an undo window. Full database backup/restore preserves actual audit and recovery records. Never disable their protection to force a patient-only import.

Restoring an older snapshot needs a verified outgoing allocation checkpoint before writes resume. A snapshot cannot prove which numbers were issued after its capture. Capture and carry forward the latest durable issuance bindings/high-water when activating an older database or rolling back; advance only upward. If total loss also destroyed that checkpoint, write activation fails pending a verified upper bound. Restoring a fresh synthetic snapshot successfully does not prove this older-snapshot case.

## Mobile compatibility

API case rows, patient search and edit-prefill responses add read-only `mtno`; requests continue using integer patient/case IDs. UHID remains a string and may be empty. New Android clients tolerate missing MTNO from old servers/cache, add it through an additive Room migration and populate it on authorized refresh. They never allocate numbers locally, rewrite queued identities or send MTNO as a mutable PATCH field. Existing account encryption, revocation and idempotency controls remain in effect.

Implementation validation and exact limitations are recorded in the Stage 3 coordination report. No source/CI/local test result establishes production migration, activation or physical-device acceptance.
