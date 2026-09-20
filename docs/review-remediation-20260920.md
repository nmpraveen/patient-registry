# Whole-project review remediation

Baseline: `2d1f38ff1623f21e74cd53ca3531336eb989798b`. This release addresses the demonstrated defects and bounded performance/cleanup work from the September 20 review. Supported delivery remains web and responsive web; retained Android history is not an active release target.

## Correctness and security

| Review finding | Result and regression coverage |
| --- | --- |
| Dashboard notes overwrite a newer diagnosis | Notes endpoint accepts only notes and a signed actor/case/patient/notes baseline. A stale note replacement returns 409; missing/tampered/wrong-actor baselines fail. Hidden diagnosis input has been removed. |
| Delayed clinical previews discard newer edits | Shared form snapshots invalidate stale responses before HTMX out-of-band swaps. Category drafts preserve intentionally empty values and unchecked boxes. Browser tests delay both create and edit responses. |
| Revoked JWT completes an in-flight mutation | Original token security context is revalidated after actor/security locks for keyed/unkeyed mutations, receipt replay, legacy notes and device registration. PostgreSQL tests commit revocation on another connection before the mutation lock. |
| Related web session race found during independent review | Notes and task mutations validate the locked actor against the original session authentication version, password hash, active status and required device approval before authorization/target lookup. |
| Backup receipt and embedded evidence refer to different checkpoints | Backup takes an immutable evidence snapshot under the exporter lock, releases the lock, then derives all archived metadata from that snapshot. A concurrent checkpoint-advance fixture verifies the identity. |
| Configured live evidence root overrides snapshot verification | Explicit verifier options select the immutable backup/restored evidence after configuration is loaded. Regression fixtures prove a configured live tree cannot redirect snapshot validation or hide corruption in the selected tree. |
| Audit watermark skips lower IDs that commit late | Migration `patients.0046` adds recoverable UUID acknowledgements and transactionally recorded export progress. Selection uses unacknowledged committed event UUIDs, never `id > watermark`. Exact segment data is durable before acknowledgement. PostgreSQL commit-inversion, crash/replay and foreign-chain restoration tests cover the protocol. |
| Due-range matches two different tasks | Both bounds apply to one correlated task query. Invalid/reversed dates yield a controlled empty result with a concise filter error. |
| Displayed age stops advancing | Current age derives from DOB when available, including API/search/selected-patient displays. Raw stored values remain in optimistic edit baselines and entered-age fallback. Browser date calculation uses calendar components, avoiding ISO UTC/local-day drift. |
| Exporter creates importer-rejected ZIP | Generated members and total sizes use the import contract. Excessively compressible members are stored without compression rather than weakening decompression defenses. Oversized exports fail with a full-backup instruction; previous recovery files are retained. Publication uses a flushed temporary file and atomic rename. |
| Opposing throttle lock order | Successful authentication clearing now locks IP before account, matching attempt reservation. A real overlapping PostgreSQL regression covers both paths. |
| Failed note saves discard drafts | Error feedback updates without rebuilding the user's textarea. Browser regression covers a failed save. |
| Cleared/abandoned intake search results reappear | Generation checks and cancellation invalidate pending/debounced requests after clear, Escape, selection and mode changes. |
| Enhanced date controls lose names/focus | Enhancement preserves accessible labels/descriptions and uses the component focus contract; browser assertions inspect the actual input. |
| WebAuthn fallback emits empty native objects | Explicit property/buffer serialization supports prototype-accessor credentials. Native Chromium virtual-authenticator registration and assertion exercise the fallback with native JSON helpers disabled. |
| Patient creator sees inaccessible case totals | Patient list/search aggregates and bounded child summaries share the same authorized-case scope. Intake identity lookup keeps its separate capability without exposing case history. |
| Non-ASCII cursor raises 500 | Shared cursor validation rejects malformed URL-safe tokens with a controlled 400. |
| Local backup inherits broad permissions | Retained manual helper checks commands/results and creates private directories/files under umask 077. Encrypted offsite backup remains the production deployment/recovery workflow. |
| Evidence export re-counts old request logs | Persistent per-file cursors export bounded complete new lines across append/rename/copytruncate/retained rotations. Missing or ambiguous continuity fails closed. Initial legacy rollout can replay a bounded current log once; subsequent unchanged logs are empty. |
| Deploy and restore can overlap | Mutating deployment/recovery modes share one host operation lock. Independent scratch verification remains isolated from production. |

## Performance and legacy disposition

| Area | Delivered change or explicit boundary |
| --- | --- |
| Recent task query amplification | Necessary task columns and assigned user are loaded together. The 20-task serialization regression takes two data queries. |
| Unbounded recent dashboard | Initial and subsequent summaries are bounded (default 20, maximum 50), with signed actor/scope/auth-version-bound keyset cursors. One expansion fetches only that case's detail and shares in-flight requests. |
| DOM layout work | Initial rows are retained rather than rebuilt; name fitting batches work through animation frames instead of rescanning the entire panel once per row. |
| API historical object materialization | List/search/write summaries load at most one next open task and one latest vital per case, plus grouped task counters. The unused task/activity join aggregate is removed. |
| Patient/universal search | Bounded visible case summaries and scoped counts replace per-patient child/count queries. Search data retrieval remains two queries for one versus ten matches. Case MTNO joins are explicit; the case branch is skipped when patient results fill the response. |
| Repeated inline assets | Stable base/dashboard/calls/theme/device CSS/JS move to cacheable local static files. Dynamic theme, endpoints and clinical JSON stay in private no-store HTML. Date component bootstrap is conditional on date controls, including dynamically inserted controls. |
| Global context | Theme and version values are reused within one request. No cross-request cache or stale invalidation contract is introduced. |
| Bundle memory | Patients/cases and lock acquisition are iterated in bounded batches. JSON/ZIP remains an explicitly size-limited in-memory format; full database recovery is the large-dataset path. Identity/consistency locks remain. |
| Notifications | Stale cleanup materializes a bounded ID set; every read independently enforces current authorization. Generic notification copy is centralized. FCM remains disabled; this release does not activate push or add an unused delivery service. |
| Backup health bandwidth | Incremental mode validates every remote identity and deeply hashes new/changed/uncacheable objects. A successful full scrub is mandatory at rollout and at least every eight days; weekly full-scrub units are provided. Scratch restore evidence remains mandatory. Existing deployments do not gain healthy status merely by installing this code. |
| Export acknowledgement work | Acknowledgements and progress share one streamed SQL transaction. Verified ancestry avoids reprocessing all retained event UUIDs during normal hourly runs; unprovable ancestry resets only recoverable delivery state and safely replays. |
| Docker caching | Revision metadata moves after dependency installation. Controlled BuildKit cache import/export is added while exact-artifact scanning and attestation remain required. |
| Shadowed legacy Python | Six overwritten definitions and their two orphan helpers are removed from `patients/views.py` (233 obsolete body lines at baseline). |
| Legacy templates/duplicate JavaScript | Unreferenced `case_form.html` is removed. Shared clinical/form-state utilities replace duplicated create/edit logic. |
| Task indexes | No speculative index is added without a representative PostgreSQL plan showing that it benefits the supported workload enough to justify write/storage cost. Bounded queries and removed join amplification are the delivered improvements. |
| Dataset/role locks | Retained: these serialize restore/receipt/authorization changes. A shared/exclusive replacement needs a complete concurrency protocol and contention evidence; deleting them is not a safe optimization. |
| Separate trusted release build | Retained: trusted main attestation cannot be replaced by signing an untrusted PR artifact. Caching reduces repeat work without changing the trust boundary. |
| Compatibility/history | Retained Android source, migrations, old supported API envelopes and local-only helpers. Deprecation alone does not establish that their data/security contracts can be deleted. |
| Required supply-chain and operations gates | Refresh verified Caddy/Alpine pins and the matching certificate package; refresh the retained Android Bouncy Castle security dependency without native feature work. Shell fixtures use private operation locks and portable log checks on unprivileged CI runners. No scanner exclusions or required-check bypasses are introduced. |

## Verification and rollout

Run the full Django suite against PostgreSQL, migration-from-zero/drift checks, strict OpenAPI, Node/browser regressions and every operations fixture. The existing seven exact-head required CI contexts stay mandatory. Independent reviewers review the implementation and the final pushed PR head; a local pass is not a production claim.

During rollout, pause the evidence-export timer while the source checkout changes and migration 0046 is pending. Preserve its prior active state and resume it after migration, then run and verify a fresh export. Do not weaken schema, lag, chain or recovery checks to bypass a failure.

Create a fresh encrypted pre-deployment recovery set, publish the ciphertext export, independently restore using the backup's exact source image ID, review the exact migration-plan hash, and use the guarded deployment script. Verify live authenticated reads and rolled-back synthetic mutations, then create and independently restore a post-deployment canary using the exact new image. Export publication is not proof of NAS arrival. Manual restore success does not certify unrelated scheduled-verifier health.

The implementation and deployment evidence are recorded in the PR and the local `medtrack-remediation-20260920` artifact directory. No real clinical records belong in tests, browser artifacts or release logs.
