# MEDTRACK operations on Mac Studio

Mac Studio owns independent recovery verification and the deployment operator
connection. Production remains on the VPS; the NAS still pulls its ciphertext.
Keep Windex's keys, verifier and schedules until Mac access, NAS restore, full
Drive scrub, scheduled success and scheduled failure delivery all pass. Keep
sanitized acceptance receipts in local `output/mac-operations-migration-20261023/`.

## Installation

The owner installation is `~/Library/Application Support/MEDTRACK/operations`
(0700). Secrets, state and logs are private. `secrets/` contains the Mac SSH key
and pinned host configuration, MEDTRACK age identity, and single-remote rclone
configuration. The copied Drive grant is **drive.file**, which permits writes;
these scripts issue only reads. Never describe the grant itself as read-only.
Production environment values are not used for the scratch application.

Requirements: Homebrew Python 3.12, Bash, GNU coreutils/findutils/tar, age,
rclone, PowerShell, and Docker Desktop's `desktop-linux` context. Keep FileVault
enabled. `settings.json` identifies the local `seed_repository` and existing
bounded NAS `nas_download_helper`. NAS credentials remain in its Keychain-backed
toolkit; no NAS pull private key is copied.

An optional exact `operations_commit` in `settings.json` pins the separately
reviewed health-check source. Update it only to the accepted operations repair
commit. The application's restore source and images remain bound to the actual
production release; operations-only repairs do not require an app redeploy.

After explicit delivery authorization, set `config.json`'s `alert_command` to
the absolute Python executable and installed `bin/pushover_alert.py`. This uses
the owner's `pushover-notify` skill and Keychain through an echo-disabled PTY
and standard input. Alerts contain bounded operational text only. Provider
acceptance does not prove device display. Ambiguous delivery requires review
and is never retried automatically. Repeated accepted failures are suppressed
for six hours until a successful run intervenes.

Run `python3 deploy/macos/install.py` to install disabled; add `--enable` after
acceptance. It preserves secrets, refuses replacement during a verifier run,
and never changes Windex jobs. Disable work by setting `enabled` false or
unloading only `gui/$(id -u)/org.nmpraveen.medtrack.recovery` with `launchctl bootout`.

## Scheduling and recovery

The user LaunchAgent checks due work every 15 minutes and at login. Schedule in
America/Detroit: health 01:15, 07:15, 13:15 and 19:15; full scrub Saturday 08:00;
restore Sunday 03:30. Missed slots run at the next invocation. GUI login,
available Keychain, network and Docker Desktop are required. A cold restart
before FileVault/login unlock is not an unattended verifier state.

Use installed `bin/scheduler.py --root <private-root> status`, `restore`,
`scrub`, or `health`; `schedule` runs due work. One job runs at a time. Attempts
are persisted before preflight; failure, timeout or interruption invalidates
older success. The restore attempt/receipt follows the shared
`medtrack-independent-scratch-attempt-v1` contract and exact receipt hashing.
Timeout terminates the child process group with time for restore cleanup.
Inspect residual scratch resources after a force kill or power loss; a running
or interrupted attempt is never healthy.

Recovery fetches a complete archive/checksum/marker triplet from the fixed NAS
MEDTRACK archive through its existing toolkit, then checks ciphertext hash,
source commit and Drive completion metadata. It selects the newest backup and
requires its source to match production. Exact current web/PostgreSQL/Caddy
image IDs are exported through the scoped VPS helper and verified after local
loading. Historical releases require their matching verified source and images;
the routine fails closed instead of guessing compatibility.

Each restore has a unique internal Docker network, no published ports,
synthetic secrets, FCM disabled, exact linux/amd64 images and disposable volumes.
Canonical `restore.sh verify` checks payload, schema, identity and audit
invariants. A second isolated database checks password-backend login,
existing-account authorization, protected staff pages, anonymous denial and
rollback of all synthetic writes. A fresh independent snapshot validates the
full current audit evidence chain. Cleanup removes only the run's labeled
Compose resources and private plaintext directory.

Health requires the latest successful restore, Drive retention triplets,
freshness and independent evidence validation. Full scrub streams every retained
ciphertext through SHA-256; incremental checks follow canonical cache rules and
require a full scrub within eight days. Latest attempt plus matching success is
authoritative; a standalone old restore receipt is not. Patient data must never
enter Git, notifications or chat.

## Deployment

Install `medtrack_mac_ops.py` as root-owned, non-writable
`/usr/local/sbin/medtrack-mac-ops` on the VPS. It validates tracked files,
Git/Compose configuration, ignored environment and smoke hook. Sudoers may
authorize only enumerated operations with validated arguments. Do not grant
general sudo, shell or caller-selected executable/configuration paths. Image
export accepts only each service's current image ID. Preserve existing access
and validate the combined policy with `visudo`.

Installed Mac `bin/deploy.py` supports `status`, `authenticated-check`,
`build-receipt`, `authorize-release`, `backup`, `prepare`, `plan`, and `apply`.
Mutable operations require exact `--target`. Authorization takes `--manifest`,
`--provenance` and `--sbom` files from the reviewed trusted build. Root verifies
both GitHub signatures, main source/signer identity, main ancestry, and the
latest main-push `ci.yml` run. All jobs must succeed; the original seven named
checks are the minimum. Windows verifier checks are included when present.
Public GitHub evidence needs no credentials. Proof expires after two hours;
CI is rechecked before each mutation. API errors fail closed.

For a fresh pre-deployment backup, invoke the scheduler's `restore` with
`--backup-source drive --tier pre-deployment --archive <exact-archive-name>`.
It downloads only that complete encrypted triplet with the existing Drive
configuration and runs the same isolated verification and attempt/receipt
publication. This avoids waiting for the NAS's six-hour pull interval while
the two-hour pre-deployment receipt is valid. Routine scheduled restore still
uses the independently mirrored NAS copy.

Follow [RUNBOOK.md](../../RUNBOOK.md): review exact-source build/scan/signature
evidence; authorize source; `prepare` the target Git checkout; create a fresh
target-bound `backup` of the still-running source; independently restore it;
run `plan --evidence-id mac-<release>`;
inspect its retained migration plan; invoke `apply` only with the reviewed
`--plan-sha256`. Apply retains existing operation locks, backup, image,
migration, login and rollback gates. Migration acceptance against the current
release does not authorize deploying a different application version.

Preparation changes only the Git checkout. It precedes backup because the
canonical backup runner requires the checkout to match the intended target
while binding the dump to the currently running source image. Plan/apply still
require the fresh target-bound backup. A disconnected or timed-out deployment
client is not proof that a remote operation stopped: inspect status and retained
remote evidence before another operation; never interrupt an activation blindly.

Private deployment logs and receipts stay in the operations root. Production
restore activation remains a separately authorized emergency procedure with
outgoing patient identity fencing and RUNBOOK safeguards; scratch acceptance
never authorizes replacing the live database.

References: [GitHub workflow runs](https://docs.github.com/en/rest/actions/workflow-runs),
[workflow jobs](https://docs.github.com/en/rest/actions/workflow-jobs), and
[Apple scheduled jobs](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html).
