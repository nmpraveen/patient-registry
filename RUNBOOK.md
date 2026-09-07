# RUNBOOK.md

## Issue #113 follow-up and ANC actions

Closing ANC with retained tasks leaves those tasks discoverable in scoped web/API/native worklists until explicitly completed/cancelled; closure does not reopen the case. EDD-only attention and dormant/missing buckets remain active-only. Initial ANC date capture during reclassification is permitted only when the prior non-ANC case has no stored effective EDD.

After an ANC outcome, routine edits do not regenerate RCH reminders. Resume follow-up through an explicitly authorised task creation/reopen. Full case edits reject an intervening case update; Recent Cases writes only diagnosis/notes. Outcome imports require a date, reason, referral destination where applicable, and an explicit boolean follow-up choice; legacy records without an outcome remain supported.

The [Stage 1 runbook](docs/issue-113-stage-1.md) defines case-based counts, hospital-date predicates, explicit retention/cancellation, native online submissions, additive migrations and patient bundle compatibility. The new outcome date records delivery/referral dates where applicable; no outcome is inferred from tasks or EDD.

For a read-only review of historical closed ANC cases, run `python manage.py report_anc_reconciliation` in an authorised environment and review each reported case before any explicit action. No bulk reopen is provided. Migration 0040 adds outcome columns without changing existing cases/tasks; export/backup those columns before any schema reversal. Production activation still requires the existing deployment and backup gates.

## Android dependency upgrades

Use JDK 21 (required by Robolectric API 36) and Android SDK Platform 37.0 for the AGP 9 build. Keep targetSdk and minSdk changes separate from compileSdk updates. AGP supplies Kotlin support; Compose modules apply the matching Kotlin Compose compiler plugin. Run `bash scripts/update-android-verification-metadata.sh` to regenerate both strict locks and checksum metadata, review the artifact sources and checksums, then rerun `testDebugUnitTest lintRelease :app:lintProdRelease assembleRelease` without write flags. Verify a replaced wrapper JAR against the Gradle distribution wrapper checksum and update its adjacent `.sha256` file.

## Reproducible Build And Exact-Head CI

Production image inputs are immutable and the Docker context is closed by
default. Never replace the explicit Dockerfile copies with `COPY .` or broaden
`.dockerignore` to include the checkout.

Review dependency/image updates:

```powershell
python .\scripts\update-python-locks.py
python .\scripts\check_image_digests.py --remote
git diff -- requirements.in requirements.txt requirements-ci.in requirements-ci.txt Dockerfile docker-compose.yml docker-compose.prod.yml
```

After reviewing an upstream image tag and release notes, refresh its digest and
re-run all gates:

```powershell
python .\scripts\check_image_digests.py --update
```

Android dependency verification metadata must be updated serially, only after
the owning application lanes have made all three Android gates green:

```bash
bash scripts/update-android-verification-metadata.sh
git diff -- android/gradle/verification-metadata.xml
```

The script uses a fresh temporary Linux Gradle home and the same three tasks as
CI with `--no-daemon --max-workers=1`. Review every added artifact/checksum. Do
not use verification-metadata updates to mask a source compile, unit, lint, or
release failure.

Build one canonical OCI artifact for an exact committed revision, load/test
that same artifact, and scan it with unfixed findings included:

```powershell
docker buildx create --name medtrack-canonical --driver docker-container --use
python .\scripts\build_canonical_image.py --revision <full-git-sha> --image medtrack-review:<short-sha> --builder medtrack-canonical
bash scripts/verify_canonical_artifact.sh <full-git-sha> output
```

This stages the exact Git tree into a temporary directory, adds fake canaries
at credential/Firebase/backup/age/rclone/output/node-module/override/PHI paths,
builds a scratch context-audit image and exactly one canonical OCI runtime
artifact. The verifier derives the archive manifest digest, loads that archive,
and scans the immutable layers and exported filesystem. It never reads ignored
credential values. Trivy's JSON, the CycloneDX SBOM, provenance, canonical
metadata, receipt, and OCI tar remain in `output/`.

`security/container-vex.json` is empty while the image is clean. Any future
HIGH/CRITICAL residual must match exact CVE, package, installed version, target,
and canonical image digest and include status, HTTPS source, owner,
justification, creation time, and unexpired expiry. New, mismatched, stale, or
expired findings/waivers fail closed; secret findings can never be waived.

The same contract applies to every production service image:

```powershell
python .\scripts\verify_production_service_images.py --revision <full-git-sha> --builder medtrack-canonical --output output\production-images
```

This builds the exact committed `Dockerfile.postgres` and
`deploy/Dockerfile.caddy` from the requested Git revision, exports each build
once as a local canonical OCI archive, derives each `linux/amd64` manifest and
config digest, loads/smoke-tests the same archive, and writes separate Trivy,
SBOM, receipt, and VEX-policy hashes. No registry publication or invented
remote Caddy reference is part of this gate. PostgreSQL and Caddy use
independent empty ledgers in `security/postgres-vex.json` and
`security/caddy-vex.json`; a finding in either blocks supply-chain CI and the
trusted post-merge release/attestation workflow.

The deployment trust contract is `medtrack.build-context/v1`. Its digest is a
canonical SHA-256 over the Git mode, UTF-8 path, byte length, and blob bytes for
the committed Docker policy files and runtime allowlist. Ignored tests,
credentials, Firebase/service-account files, backups, age/rclone material,
outputs, node modules, local overrides, dumps, and PHI bundles cannot affect or
enter the receipt. Compute and verify it without trusting the working-tree diff:

```powershell
python .\scripts\build_context_receipt.py --revision <full-git-sha>
python .\scripts\build_context_receipt.py --revision <full-git-sha> --verify-image medtrack-review:<short-sha>
```

The verifier requires exact equality for these OCI labels:

- `org.opencontainers.image.revision=<40-character-git-sha>`
- `org.medtrack.build-context.schema=medtrack.build-context/v1`
- `org.medtrack.build-context.digest=sha256:<64-hex-context-digest>`

`deploy-production.sh` computes the digest from Git objects, stages that exact
commit with `git archive` into a temporary build context, passes the digest as a
build argument, reads the labels back before startup, and emits a single receipt
line: `MEDTRACK_BUILD_RECEIPT revision=<sha>
build_context_sha256=<digest> image=<image-id>`. Ops must store that line with
the reviewed deployment record and reject an image that fails the verifier.

The web image runs as the fixed non-root UID/GID `10001:10001`. Before the first
deployment of this image, the host backup directory named by `BACKUP_HOST_DIR`
must exist and be writable only by the intended operator and UID/GID 10001. The
deployment script tests both `/app/backups` and `/app/staticfiles` before it
starts or replaces the web service, also verifies `/tmp`, and fails closed if
any runtime write location is not writable.

GitHub Actions tests the pull request head SHA directly. The required checks are
listed in `.github/BRANCH_PROTECTION.md`. Branch protection is a post-merge
administrator action:

```powershell
.\scripts\apply-branch-protection.ps1 -ReviewerPolicy SoloSafe -SignedCommits NotRequired
.\scripts\apply-branch-protection.ps1 -Apply -ReviewerPolicy SoloSafe -SignedCommits NotRequired -ExpectedMainSha <40-character-merged-main-sha>
```

The first command is read-only. Do not use `-Apply` before the workflow exists
on `main` and has emitted all required check names.

## Local Demo Server

Use the local-only Test NNH server for demos and quick verification.

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
.\local-dev\test-nnh-up.ps1
.\local-dev\test-nnh-status.ps1
.\local-dev\test-nnh-health.ps1
```

Open `http://localhost:8000/login/` and sign in with `admin` / `pass`.

Stop it when it was only needed for the current task:

```powershell
.\local-dev\test-nnh-stop.ps1
```

Do not start a separate demo server unless the local Test NNH workflow is unusable and the reason is documented.

## Dashboard Discovery

After starting or reusing a local server, confirm it is visible to the Local Server Dashboard:

```powershell
.\local-dev\test-nnh-health.ps1
Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:3899/api/snapshot -TimeoutSec 10
```

If the dashboard is not running and server visibility matters, start it with:

```powershell
C:\Users\prave\Desktop\dashboard.cmd
```

## Docker App Commands

General app start:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Run migrations:

```powershell
docker compose --profile deploy run --rm migrate
```

Web startup does not run migrations. In production, use the reviewed plan/apply gate below instead of invoking this job directly.

Run tests:

```powershell
docker compose exec web python manage.py test
```

Seed demo data:

```powershell
docker compose exec web python manage.py seed_mock_data --count 30 --reset
```

Create an admin user for non-Test-NNH environments:

```powershell
docker compose exec web python manage.py createsuperuser
```

## Backup And Restore

Full environment backup before production updates:

```powershell
.\scripts\backup.sh
```

Routine patient-data backup:

```powershell
docker compose exec -T web python manage.py backup_patient_data --output-dir /app/backups --keep 30
```

Verify an encrypted full-recovery backup without changing production:

```bash
./scripts/restore.sh verify \
  --archive /absolute/path/medtrack-prod-<tier>-<timestamp>.tar.age \
  --checksum /absolute/path/medtrack-prod-<tier>-<timestamp>.tar.age.sha256 \
  --identity /offline/path/age-identity.txt \
  --expected-commit <full-git-sha> \
  --image-attestation /absolute/path/image.attestation \
  --receipt-dir /absolute/path/restore-receipt
```

Verification checks the ciphertext checksum, safe archive paths, regular-file/directory-only member types, every internal manifest hash, PostgreSQL catalog, recorded PostgreSQL version, exact clean Git commit, the canonical `medtrack.build-context/v1` revision/schema/digest labels, a new isolated database restore, migration state, the append-only AuditEvent table/trigger and recorded row/id lower bound, the security-evidence hash chain, Django deployment checks, ORM access, and `/login/`. Decrypted material and the scratch database are removed on exit. The build-context verifier delivered by PR #100 is mandatory; a missing verifier or mismatched label fails closed.

Production activation is an emergency operation, not the default restore mode. It additionally requires `MEDTRACK_ALLOW_PRODUCTION_RESTORE=1`, the exact `ACTIVATE_VERIFIED_MEDTRACK_RESTORE` confirmation token, an empty absolute rollback directory, and the same root-owned authenticated-login hook used by deployment. Before any switch it creates a fresh custom-format snapshot of the current production database, verifies its catalog, scratch-restores it, and runs the same Django checks. It then quiesces writes and renames databases rather than dropping production. Activation is accepted only after DB/web/Caddy health, exact running image identity, origin-bypassed and public HTTPS login-page checks, and the authenticated-login hook; a failed gate restores the retained database. Run activation as:

```bash
MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 ./scripts/restore.sh activate \
  --archive /absolute/path/medtrack-prod-<tier>-<timestamp>.tar.age \
  --checksum /absolute/path/medtrack-prod-<tier>-<timestamp>.tar.age.sha256 \
  --identity /offline/path/age-identity.txt \
  --expected-commit <full-git-sha> \
  --image-attestation /absolute/path/image.attestation \
  --receipt-dir /absolute/path/restore-receipt \
  --rollback-dir /absolute/empty/path/restore-rollback \
  --login-smoke-hook /root/medtrack-authenticated-login-smoke \
  --confirm ACTIVATE_VERIFIED_MEDTRACK_RESTORE
```

The retained activation receipt supports:

```bash
MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 ./scripts/restore.sh rollback \
  --receipt-dir /absolute/path/restore-receipt \
  --confirm ROLLBACK_MEDTRACK_RESTORE
```

Never reverse a destructive data migration in production. `patients.0028` now fails closed in reverse because reversal would delete master-patient records and unlink every case. Roll back with a verified database snapshot plus its matching application commit. Never run `docker compose down -v` unless deleting the database volume is intentional.

## Production VPS Deployment

Production checkout: `/srv/medtrack/app`

Production domain: `https://book.naveenhospital.net`

Preflight:

```bash
cd /srv/medtrack/app
test -f .env
git status --short
git rev-parse HEAD
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

Create a fresh encrypted pre-deployment backup and capture its receipt:

```bash
MEDTRACK_BACKUP_CONFIG=/etc/medtrack-backup/backup.env ./scripts/backup-offsite.sh --tier pre-deployment --target-commit <expected-full-git-commit>
systemctl start medtrack-nas-export.service
test "$(systemctl show medtrack-nas-export.service --property=Result --value)" = success
```

Generate the read-only migration plan and rollback-preparation evidence:

```bash
evidence_dir=/srv/medtrack/deploy-evidence/<deployment-id>
./scripts/deploy-production.sh plan <expected-full-git-commit> \
  --backup-receipt /srv/medtrack/offsite-backups/state/latest-pre-deployment.receipt \
  --evidence-dir "$evidence_dir"
sha256sum "$evidence_dir/migration-plan.txt"
```

The plan command requires the existing `db` container to already report healthy. It builds the reviewed Git-object-only web image and the pinned custom Caddy image, verifies their receipts/modules, and runs read-only Django planning in a disposable `--no-deps` container; it never pulls, starts, stops, or recreates the live `db`, `web`, or Caddy services. Preserve the emitted `MEDTRACK_BUILD_RECEIPT` line with the deployment evidence.

Review the migration plan. Then apply only the exact approved hash, using a root-owned executable login-smoke hook that obtains credentials outside the repository and emits no secrets or PHI:

```bash
./scripts/deploy-production.sh apply <expected-full-git-commit> \
  --backup-receipt /srv/medtrack/offsite-backups/state/latest-pre-deployment.receipt \
  --evidence-dir "$evidence_dir" \
  --approve-plan-sha256 <reviewed-plan-sha256> \
  --login-smoke-hook /root/medtrack-authenticated-login-smoke
```

Apply revalidates the fresh ciphertext triplet, exact commit-labeled images and migration plan, creates a new custom-format rollback dump, restores it into an isolated scratch database, retains a database clone and prior web image, runs the one-shot migration, requires DB/web/Caddy health, origin-bypassed and public HTTPS login-page checks, Django deployment checks, and the authenticated login hook. The recovery trap is installed before the first stop: failures while stopping, terminating connections, or creating the rollback clone restart the prior release, while failures after the clone is ready restore the retained database and image. The deployment receipt documents the manual rollback inputs; use `deploy-production.sh rollback` only with explicit operator approval.

Acceptance:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py check --deploy
curl --fail --silent --show-error --resolve book.naveenhospital.net:443:127.0.0.1 https://book.naveenhospital.net/login/ >/dev/null
curl --fail --silent --show-error https://book.naveenhospital.net/login/ >/dev/null
```

Last verified production deployment (2026-08-23):

- live commit `a5dff668b23c52e5a71431807a291573f9e0404c` from merged PR #95;
- migration `patients.0036_remove_plaintext_password_notes` applied and the removed table absent;
- real administrator login, authenticated `/patients/`, and user-management UI passed over public HTTPS;
- rollback-only live authorization smoke passed assigned access, forged-ID denial, and reassignment revocation without retaining synthetic records;
- pre-deployment archive `medtrack-prod-pre-deployment-20260823T174416Z.tar.age` passed Drive verification, immediate NAS export, and off-site health checks.

Before a future code update, run `./scripts/backup.sh` and preserve the resulting backup outside the VPS. Never deploy from a dirty checkout and never run `docker compose down -v` during an update.

## Encrypted Google Drive Recovery Backups

The production backup remote is `medtrack-drive:Naveen-Hospital-Backups/MEDTRACK/production`. Backup payloads are encrypted before upload; filenames and tier names are not encrypted. Never put the private `age` identity or a decrypted archive on the VPS.

Policy note: [Google Drive API policy](https://developers.google.com/workspace/drive/api/terms) restricts using a developer app/project as a general backup mechanism without Google's express prior written consent. On 2026-08-11 the owner explicitly chose personal-use operation and enabled the recurring timers after the technical restore and key-copy gates passed. That is an operator risk decision, not a legal or policy-compliance conclusion. The independent Synology ciphertext mirror below prevents Google Drive from being the only off-VPS copy. The narrow [`drive.file` scope](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) limits technical access; it does not override the use-case restriction.

Required root-only paths:

```text
/etc/medtrack-backup/backup.env                 mode 0600
/srv/medtrack/backup-secrets/rclone.conf        mode 0600
/srv/medtrack/backup-secrets/age-recipient.txt  mode 0644 (public key only)
/srv/medtrack/offsite-backups/                  mode 0700
/srv/medtrack/security-logs/                     owner root, group 10001, mode 3770
/srv/medtrack/security-evidence/                 mode 0700
```

OAuth requirements:

- authorize the intended backup Google account with rclone's `drive.file` scope
- set the External OAuth app to **In production** before authorization; Google's Testing-mode refresh tokens expire after seven days and are not suitable for unattended backups
- keep the OAuth refresh token only in `/srv/medtrack/backup-secrets/rclone.conf`
- do not use Drive `sync` or `purge`; the scripts upload immutable unique names and delete only expired, exact-pattern tier files
- keep at least two recoverable off-VPS copies of the private `age` identity; the second copy was confirmed on 2026-08-11

On the VPS, install the writer-side configuration and units after the reviewed commit is deployed. Do not install the independent scratch-restore runner or copy an `age` identity to this host:

```bash
install -d -m 0700 /srv/medtrack/backup-secrets /srv/medtrack/offsite-backups /srv/medtrack/security-evidence
install -d -m 3770 -o root -g 10001 /srv/medtrack/security-logs
install -d -m 0755 /etc/medtrack-backup
install -m 0600 deploy/backup/backup.env.example /etc/medtrack-backup/backup.env
install -m 0644 deploy/systemd/medtrack-offsite-backup@.service /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-offsite-backup-{rapid,daily,weekly,monthly}.timer /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-security-evidence-export.service /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-security-evidence-export.timer /etc/systemd/system/
install -m 0644 deploy/logrotate/medtrack-security-logs /etc/logrotate.d/medtrack-security-logs
install -m 0644 deploy/systemd/medtrack-patient-backup-scheduler.service /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-patient-backup-scheduler.timer /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/medtrack-offsite-backup@.service /etc/systemd/system/medtrack-offsite-backup-{rapid,daily,weekly,monthly}.timer /etc/systemd/system/medtrack-security-evidence-export.service /etc/systemd/system/medtrack-security-evidence-export.timer
systemctl daemon-reload
```

Run an encrypted canary and inspect only ciphertext metadata:

```bash
MEDTRACK_BACKUP_CONFIG=/etc/medtrack-backup/backup.env ./scripts/backup-offsite.sh --tier canary
rclone --config /srv/medtrack/backup-secrets/rclone.conf lsl medtrack-drive:Naveen-Hospital-Backups/MEDTRACK/production/canary
```

Technical gates used before enabling the four backup schedules:

- live encrypted canary verification
- independent scratch PostgreSQL/Django restore
- confirmed second offline/password-manager copy of the private `age` identity
- explicit owner decision for the selected unattended remote, with the remaining provider-policy risk recorded

```bash
systemctl enable --now \
  medtrack-offsite-backup-rapid.timer \
  medtrack-offsite-backup-daily.timer \
  medtrack-offsite-backup-weekly.timer \
  medtrack-offsite-backup-monthly.timer \
  medtrack-security-evidence-export.timer
systemctl list-timers 'medtrack-offsite-backup*'
```

Schedule and retention (all calendar times are `Asia/Kolkata`):

| Tier | Schedule | Maximum completed sets |
|---|---|---:|
| Rapid | 00:15, 06:15, 12:15, 18:15 daily, up to 5-minute jitter | 28 |
| Daily | 02:15 daily, up to 10-minute jitter | 30 |
| Weekly | Sunday 03:15, up to 15-minute jitter | 12 |
| Monthly | Day 1 at 04:15, up to 20-minute jitter | 12 |
| Pre-deployment | Manual before deployment | 14 |

On the independent verifier, use a separate exact reviewed checkout and separate root-only config. This host—not the VPS or NAS—holds the offline restore identity. Its `MEDTRACK_SCRATCH_RESTORE_HOOK` must download a completed Drive triplet, run `restore.sh verify` against isolated PostgreSQL/Django, retain the verified security-evidence tree at `MEDTRACK_SECURITY_EVIDENCE_ROOT`, and return nonzero on any mismatch. Its alert hook must deliver outside that host. Install and enable both independent timers:

```bash
install -d -m 0700 /var/lib/medtrack-backup-health /srv/medtrack/security-evidence
install -m 0644 deploy/systemd/medtrack-offsite-backup-health.service /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-offsite-backup-health.timer /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-offsite-scratch-restore.service /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-offsite-scratch-restore.timer /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/medtrack-offsite-backup-health.service /etc/systemd/system/medtrack-offsite-backup-health.timer /etc/systemd/system/medtrack-offsite-scratch-restore.service /etc/systemd/system/medtrack-offsite-scratch-restore.timer
systemctl daemon-reload
systemctl enable --now medtrack-offsite-scratch-restore.timer medtrack-offsite-backup-health.timer
```

Run and inspect health checks on that independent verifier:

```bash
systemctl start medtrack-offsite-backup-health.service
systemctl status --no-pager medtrack-offsite-backup-health.service
journalctl -u 'medtrack-offsite-backup*' --since '24 hours ago' --no-pager
```

Every production health pass requires complete archive/checksum/marker triplets for each retained set, cross-checks marker/checksum/evidence-chain metadata, streams every retained ciphertext through SHA-256, runs the independently restored evidence-chain/lag hook, and requires a fresh scratch-restore receipt whose runner has a mandatory alert hook. These requirements are not optional in `MEDTRACK_HEALTH_PRODUCTION_MODE=1`. The VPS-side schedules remain green only as upload evidence; the independent verifier is the authoritative recovery-health signal. Keep the private `age` identity off the VPS and NAS.

Enable the single-owner patient-data schedule runner after installing its units:

```bash
systemctl enable --now medtrack-patient-backup-scheduler.timer
systemctl start medtrack-patient-backup-scheduler.service
systemctl status --no-pager medtrack-patient-backup-scheduler.service
```

Gunicorn workers and management-command startup do not create scheduler threads. Saving schedule settings records policy only; the supervised one-shot service owns execution.

Before each production deployment:

```bash
MEDTRACK_BACKUP_CONFIG=/etc/medtrack-backup/backup.env ./scripts/backup-offsite.sh --tier pre-deployment --target-commit <expected-full-git-commit>
systemctl start medtrack-nas-export.service
test "$(systemctl show medtrack-nas-export.service --property=Result --value)" = success
```

The second command publishes the newly completed pre-deployment ciphertext immediately instead of waiting for the hourly export timer. It does not contact the NAS; the NAS remains pull-only and fetches on its normal six-hour cadence.

A successful upload is not restore proof. On a separate scratch host, download one completed ciphertext plus its checksum, verify SHA-256, decrypt it with the offline identity, verify the internal `manifest.sha256` and security-evidence chain, list `database.dump` with `pg_restore --list`, and restore it into a new empty PostgreSQL database. Prove the AuditEvent table, append-only trigger, migration, row lower bound, and max-id lower bound. Never test a restore over production.

### Audit, request-log, and edge-auth evidence

PR #103 defines `public.patients_auditevent`, migration `patients.0037_backend_auth_clinical_security`, and trigger `patients_auditevent_append_only`. Do not enable the production backup/evidence units until that exact schema is integrated and the combined-head scratch tests pass. The backup records the running source commit/image/schema separately from the intended target commit; the source image must restore the pre-deployment database, while the deployment receipt binds the target.

Gunicorn runs as UID `10001`; Caddy runs separately as UID `10002`; both use the restricted runtime-log GID `10001`. They write only timestamp, method, status, duration, and response size to the root-owned, setgid/sticky, group-writable security-log directory. Never add request bodies, URI/path/query strings, authorization or cookie headers, client IPs, usernames, patient search text, or clinical payloads. The hourly root exporter selects only coarse AuditEvent identity/time/category/action/outcome/source fields, bounds rows and log bytes, creates a SHA-256 chained segment, alerts on lag/discontinuity or sustained safe failure/429 counts, and retains 2,160 hourly segments (90 days) with a continuity anchor. Encrypted Drive archives and the pull-only NAS mirror contain the retained segments, anchor, checkpoint, and their manifest hashes. Recovery starts from the anchor, verifies every retained segment, and cross-checks the final chain with the backup marker/receipt.

The custom Caddy image is built from digest-pinned Caddy 2.11.4 builder/runtime images with `github.com/mholt/caddy-ratelimit` pinned at commit `5625512f24f6f59d6f64fb3aafe5eecff0b286db`. It runs as `10002:10001` with all capabilities dropped except `NET_BIND_SERVICE` and `no-new-privileges` enabled. Before the first non-root deployment, run `docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps --user 0:0 caddy chown -R 10002:10001 /data /config` once for any existing Caddy volumes and verify `/srv/medtrack/security-logs` has the ownership and mode above; new volumes inherit the reviewed image ownership. CI builds the exact committed Dockerfile into one canonical OCI archive and binds its BuildKit manifest, OCI manifest/config, loaded image ID, Dockerfile/Caddyfile hashes, Trivy report, SBOM, and VEX policy in the service receipt. Startup, deploy, and restore validation require UID/GID `10002:10001`, `http.handlers.rate_limit`, and the exact Caddyfile; stock Caddy fails this gate. Web/admin login, JWT obtain, JWT refresh, and device-verification paths have separate coarse endpoint classes with global static caps followed by per-client burst and sustained windows. The global handler bounds the number of dynamic client buckets that can be created per window; IPv6 is grouped at `/64`; the module sweeps expired buckets every minute; 429 responses include `Retry-After` and a fixed PHI-free body. Backend application throttles remain mandatory and must not be weakened.

Caddy is currently the public edge, so `{remote_host}` is the direct TCP peer and forwarded client-IP headers are not trusted. Caddy replaces any inbound `X-Medtrack-Client-IP` with that direct peer and connects to Django from the fixed `172.30.0.10` edge address. Do not combine a Caddy `header_up` delete and set for the same case-insensitive header: Caddy 2.11 canonicalizes the set key differently and the delete can remove the replacement. Django accepts the replacement header only from the exact `172.30.0.10/32` allowlist, canonicalizes IPv4/IPv6 addresses, and otherwise uses `REMOTE_ADDR`. Production startup fails if the expected Caddy address is absent from the configured allowlist. The web container intentionally has no fixed edge address so one-shot planning containers cannot collide with a running web instance. If a CDN or load balancer is introduced, stop and review explicit provider CIDRs, enable strict right-to-left trusted-proxy parsing, prove direct-origin bypass is blocked, and rerun the edge runtime fixture. Never use arbitrary client-supplied forwarding headers or broad private-range trust as the limiter key.

Verified 2026-08-11 recovery proof:

- deployed commit `73e551ec79cd96fd191a51abc62ce34d95b47c8c`
- canary `medtrack-prod-canary-20260811T165254Z.tar.age`
- external and 9-entry internal SHA-256 verification passed
- 283-entry PostgreSQL custom dump restored into isolated PostgreSQL 16.14
- 30 public tables and 69 Django migration rows restored
- exact-commit Django check, migration check, ORM query, and `/login/` HTTP 200 passed
- rapid, daily, weekly, monthly, and health timers enabled after the owner accepted the remaining Drive policy risk

## Restricted Synology NAS Ciphertext Mirror

The NAS mirror is a separate failure domain from Google Drive and is deliberately pull-only:

```text
root-only VPS ciphertext cache
  -> root-published append-only export
  -> SFTP-only read account (public key, no shell, no forwarding)
  -> NAS incoming quarantine (networked fetcher)
  -> checksum-valid complete triplets only
  -> NAS archive (network-disabled promoter)
```

Live paths and cadence:

| Component | Location or cadence |
|---|---|
| VPS ciphertext source | `/srv/medtrack/offsite-backups/local` |
| VPS SFTP chroot | `/srv/medtrack/nas-export`, with `/data` exposed read-only |
| VPS export refresh | Every hour, with up to 5 minutes of jitter |
| NAS user-facing destination | `Home/Backups/MEDTRACK` |
| NAS physical destination | `/volume1/homes/nmpraveen/Backups/MEDTRACK` |
| NAS encrypted fetch | Every 6 hours |
| Incoming-to-archive promotion | Every 5 minutes |
| Incoming/archive ceilings | 20 GiB each; fail closed, no automatic deletion |

Install the VPS export only with the NAS-generated public key:

```bash
sudo ./deploy/nas-export/install-nas-export.sh \
  --public-key-file /absolute/path/to/medtrack-nas-pull.pub
systemctl status --no-pager medtrack-nas-export.timer
systemctl show medtrack-nas-export.service --property=Result --value
sshd -T -C user=medtrack-nas-pull,host=localhost,addr=127.0.0.1
```

The installer creates `medtrack-nas-pull` as an SFTP-only chrooted account, keeps its authorized key outside the chroot, adds it to the existing SSH `AllowUsers` line, validates `sshd` before reload, and starts the hardened export timer. The export script accepts only complete, checksum-valid MEDTRACK tier triplets. Existing same-name files must be byte-identical, so source deletion does not delete the export and a changed same-name source fails closed.

NAS containment rules:

- the fetcher runs non-root with a read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, a 256 MiB memory limit, and only the incoming area writable
- the promoter runs non-root with `network_mode: none`, cannot see SFTP credentials, and has the incoming area read-only plus archive/state writable
- the private `age` identity never enters the VPS or NAS; both hold ciphertext only
- strict filename filters, per-file/transfer ceilings, complete-triplet checks, and SHA-256 verification limit what a compromised VPS can feed the NAS
- no container has the Docker socket, NAS media mounts, or access to other NAS folders
- there is no automatic NAS deletion; space exhaustion fails closed and requires operator review

Residual limitation: this Synology kernel exposes AppArmor but not Docker's normal seccomp profile and did not honor the requested PID/CPU limits. Memory limits, namespace/mount separation, capability dropping, `no-new-privileges`, the SFTP read-only boundary, and the two-container split remain enforced. A compromised VPS could still send correctly named malicious ciphertext or consume the bounded incoming/archive allocation, but it cannot decrypt existing backups, directly write the archive, or reach other NAS data through these containers.

Verified 2026-08-11 NAS recovery proof:

- five initial tiers fetched and promoted; every archive SHA-256 passed
- restricted VPS write attempt returned `permission denied`, and the test file remained absent
- fetcher had no archive mount; promoter had no network or credentials; no NAS `age` identity was present
- NAS-sourced canary matched both external checksums and all 9 internal manifest entries
- 283-entry dump restored into isolated PostgreSQL 16.14 with 30 public tables and 69 migration rows
- exact backup commit passed Django deployment/migration checks, ORM queries, and `/login/` HTTP 200
- all decrypted scratch material and disposable restore infrastructure were removed after verification

## Android Local Verification

Fast manual emulator start and login:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
.\local-dev\test-nnh-status.ps1
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd MarkUS_Local -gpu swiftshader_indirect
adb wait-for-device
adb shell svc power stayon true
adb shell input keyevent 224
adb shell wm dismiss-keyguard
cd android
.\gradlew.bat --no-daemon --max-workers=1 :app:assembleDevDebug
$apk = Join-Path (Get-Location) ".build\app\outputs\apk\dev\debug\app-dev-debug.apk"
adb install -r $apk
adb shell pm clear com.naveenhospital.medtrack.dev
adb shell am start -W -n com.naveenhospital.medtrack.dev/com.naveenhospital.medtrack.MainActivity
```

Log in with `admin` / `pass`. On first run after clearing app data, set the pattern with top-left, top-middle, top-right, then middle-right dots; tap Save and Continue. Deny the Android notification permission prompt unless notification behavior is being tested.

Known emulator failure: if `MarkUS_Latest_API37` is attached but screenshots are black, `dumpsys activity users` reports `RUNNING_LOCKED`, or SystemUI/NotificationShade remains focused, kill that emulator and use `MarkUS_Local`. If `am start` says `.MainActivity` does not exist but `dumpsys package com.naveenhospital.medtrack` lists `.MainActivity`, this is the same emulator lock/profile problem, not an APK build problem.

API smoke:

```powershell
.\android\scripts\mobile-api-smoke.ps1
```

Backend plus Android unit tests:

```powershell
.\android\scripts\mobile-test-suite.ps1
```

Release-ready Android verification is serialized to avoid resource contention:

```powershell
cd android
.\gradlew.bat --no-daemon --max-workers=1 test
.\gradlew.bat --no-daemon --max-workers=1 lintProdRelease
.\gradlew.bat --no-daemon --max-workers=1 assembleDevDebug
.\gradlew.bat --no-daemon --max-workers=1 unsignedReleaseArtifacts
.\scripts\verify-dependencies.ps1
.\scripts\build-release-artifacts.ps1 -SkipBuild
```

See `android/RELEASE.md` for flavor endpoints, external signing inputs,
Play/API compatibility, dependency-lock maintenance, and artifact contents.

Emulator smoke:

```powershell
.\android\scripts\local-emulator-smoke.ps1 -OfflineWrites
```

For a non-biometric emulator smoke on the reliable manual AVD, pass `-AvdName MarkUS_Local`.

Biometric smoke on enrolled AVD:

```powershell
.\android\scripts\biometric-emulator-smoke.ps1
```

Screenshot handoff evidence from the latest Android review:

```powershell
output\android-claude-handoff-final-20260531-105420\CLAUDE_HANDOFF.md
output\android-claude-handoff-final-20260531-105420\contact-sheet.png
```

That handoff covers the major runtime screens and includes remaining-work notes for create-case persistence, lock routing, Firebase delivery, physical-device smoke, and field testing.

Final local/external gate audit:

```powershell
.\android\scripts\medtrack-v1-audit.ps1
```

## Firebase And Device Gates

Firebase preflight:

```powershell
.\android\scripts\mobile-push-preflight.ps1 -RequireReady
```

Direct-token Firebase smoke:

```powershell
.\android\scripts\mobile-push-smoke.ps1 -RequireFirebase
```

Physical device offline smoke:

```powershell
.\android\scripts\physical-device-smoke.ps1 -OfflineWrites
```

Full real-device push smoke:

```powershell
.\android\scripts\mobile-real-push-smoke.ps1 -NoBuild
```

Two-user field-test record:

```powershell
.\android\scripts\field-test-record.ps1 `
  -DeviceModel "<model>" `
  -AndroidVersion "<version>" `
  -Tester1Role "<role>" `
  -Tester2Role "<role>" `
  -HomeInboxPassed `
  -CallDonePassed `
  -VitalsPassed `
  -OfflineSyncPassed `
  -LockUnlockPassed `
  -ReadabilityPassed `
  -NoCrashOrAnr `
  -Issues "None"
```

Do not write raw FCM tokens, service-account JSON, PHI, patient names, or patient screenshots into evidence artifacts.

## Generated Outputs

- `backups/` - backup bundles; sensitive and gitignored.
- `output/` - smoke/audit evidence created by Android/API scripts.
- `staticfiles/` - collected Django static files.
- `%USERPROFILE%\.codex\build\medtrack-android\` - Android Gradle build output outside Dropbox.
- Docker volume `test_nnh_state` - Test NNH demo SQLite state.
- `/srv/medtrack/offsite-backups/` - root-only local ciphertext cache and success-state files.
- Google Drive `Naveen-Hospital-Backups/MEDTRACK/production/` - encrypted canary, rapid, daily, weekly, monthly, and pre-deployment recovery tiers; recurring timers are active by explicit owner decision.
