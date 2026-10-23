# Retained backup integrity catalog

This optional verifier policy recognizes exact, independently approved historical
triplet bytes. It does not authorize restores, establish missing provenance, modify
archives or markers, or enroll objects automatically. `scripts/restore.sh` is
unchanged. Configure it only after independent provenance review; an old filename
or a successful decryption alone is not approval.

## Configuration

Keep the catalog and its independent SHA-256 pin in private verifier configuration
outside backup storage. The pin must come from the approved review, never from
an automatic download or a hash calculated from an untrusted catalog at runtime.

```dotenv
MEDTRACK_LEGACY_CATALOG=/etc/medtrack-backup/retained-integrity.json
MEDTRACK_LEGACY_CATALOG_SHA256=<independently-approved-64-lowercase-hex-digest>
```

Both variables are optional together and required together. The path must be
absolute. Windows private adapters must pass the corresponding native Python
path. Neither variable changes the Windows wrapper's JSON schema. Do not place
real catalog entries or private backup metadata in the repository.

Schema (values below are synthetic placeholders, not an enrollment file):

```json
{
  "catalog_format": "medtrack-retained-legacy-v1",
  "policy_version": "medtrack-retained-integrity-v1",
  "namespace": "synthetic:backup/production",
  "entries": [
    {
      "tier": "weekly",
      "archive": "medtrack-prod-weekly-20200101T000000Z.tar.age",
      "format": "offsite-v1",
      "ciphertext_size": 123,
      "ciphertext_sha256": "<64 lowercase hex>",
      "checksum_file_sha256": "<64 lowercase hex of raw .sha256 bytes>",
      "marker_file_sha256": "<64 lowercase hex of raw .complete bytes>"
    }
  ]
}
```

The namespace must exactly equal `RCLONE_REMOTE`, including remote name, case and
path; use a canonical path without trailing slash, empty components, `.` or `..`.
Tier is `rapid`, `daily`, `weekly` or `monthly`. Names must exactly match that tier
and a real UTC calendar timestamp. Ciphertext size is a positive integer, not a
JSON boolean/string. Unknown fields, duplicate JSON keys/entries, unsupported
versions, and catalogs over 2 MiB or 4,096 entries are rejected. Entries are finite
allowlisted identities, not age or missing-field rules. An entry that has already
retired legitimately does not have to remain present.

## Exact marker shapes

| Shape | Required fields | Acceptance |
|---|---|---|
| `offsite-v1` (`c801447` writer) | `archive`, `sha256`, `completed_utc` | Pinned retained object only |
| `offsite-v2` (`0ac9814` writer) | v1 plus `source_commit`, `intended_target_commit` | Pinned retained object only |
| `offsite-v3` (`3bd2114` writer) | v2 plus `security_evidence_chain_sha256` | Pinned retained object only |
| Current (`9db9f88` onward) | v3 plus `drive_verified`, `drive_verified_epoch` | All eight fields required; newest per tier must be current |

The six-field historical v3 shape also needs an independent pin. Otherwise,
removing both Drive fields from a current marker would be indistinguishable from
the legitimate historical writer. This preserves retained six-field objects
without a generic downgrade path. It requires their own provenance review before
private enrollment, separate from any three-field inventory.

`format` names describe the completion-marker shape, not the decrypted payload
version or running application image. A historically verified v4 payload written
before the Drive-field change can have the six-field `offsite-v3` marker shape;
its separate provenance review must bind the actual writer, image and payload.

All shapes require unique fields, exact archive/timestamp/checksum matching and
valid hashes. Fields historically present remain mandatory and validated. Current
Drive verification must equal `1`, with a positive epoch no earlier than archive
creation and no later than verification time. Marker/checksum files use the writer's
ASCII/LF encoding; checksum content is exactly `SHA256`, two spaces, filename and
one LF. Raw legacy file hashes additionally bind line order and every byte.

## Run and acceptance binding

At startup the verifier reads the catalog once, verifies its independent pin and
schema, and makes a private snapshot. Every consumer verifies the captured
snapshot digest. Replacing the original catalog during a run cannot change its
decisions or the digest written to its receipt; altered snapshot bytes fail.

Full-scrub receipts now use `medtrack-full-ciphertext-scrub-v2`, recording
`metadata_policy=medtrack-retained-integrity-v1` and `legacy_catalog_sha256`
(`none` when disabled). Object hash-cache acceptance is also scoped to that pair.
A policy/pin change or removal cannot reuse old acceptance. Existing v1 scrub
receipts require a fresh successful `--hash-mode all`, even with no catalog.
Do not edit receipts or manufacture success to migrate state.

```bash
MEDTRACK_BACKUP_CONFIG=/etc/medtrack-backup/backup.env \
  ./scripts/check-offsite-backups.sh --production --hash-mode all
MEDTRACK_BACKUP_CONFIG=/etc/medtrack-backup/backup.env \
  ./scripts/check-offsite-backups.sh --production --hash-mode incremental
```

Every retained triplet still counts toward existing retention/orphan limits.
Legacy ciphertext size is checked against remote metadata and streamed bytes;
all/incremental hashing and stable-identity requirements remain. Even diagnostic
`latest` mode verifies cataloged ciphertext. Production still rejects `latest`.
Newest-per-tier freshness, full-scrub age, independent successful restore attempt
and receipt, and current evidence-chain/lag hooks all remain mandatory. Catalog
acceptance cannot satisfy those gates. A full-scrub receipt is published only
after all gates and a final snapshot integrity check pass.

Synthetic coverage: `test_offsite_legacy_catalog`, `test_offsite_legacy_health`,
existing offsite-health and scratch-state/attempt lock regressions. Source tests
and catalog approval are separate from actual scheduled execution and restore
proof; runtime installation remains an operator/coordinator step after exact-head
review and CI.
