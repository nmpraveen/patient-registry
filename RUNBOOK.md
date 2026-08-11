# RUNBOOK.md

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
docker compose exec web python manage.py migrate
```

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

Restore a full backup:

```powershell
.\scripts\restore.sh backups\<timestamp>
docker compose up -d
docker compose exec web python manage.py migrate
```

Never run `docker compose down -v` unless deleting the database volume is intentional.

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

Deploy only the reviewed full commit:

```bash
./scripts/deploy-production.sh <expected-full-git-commit>
```

Acceptance:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py check --deploy
curl --fail --silent --show-error --resolve book.naveenhospital.net:443:127.0.0.1 https://book.naveenhospital.net/login/ >/dev/null
curl --fail --silent --show-error https://book.naveenhospital.net/login/ >/dev/null
```

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
```

OAuth requirements:

- authorize the intended backup Google account with rclone's `drive.file` scope
- set the External OAuth app to **In production** before authorization; Google's Testing-mode refresh tokens expire after seven days and are not suitable for unattended backups
- keep the OAuth refresh token only in `/srv/medtrack/backup-secrets/rclone.conf`
- do not use Drive `sync` or `purge`; the scripts upload immutable unique names and delete only expired, exact-pattern tier files
- keep at least two recoverable off-VPS copies of the private `age` identity; the second copy was confirmed on 2026-08-11

Install the configuration and units after the reviewed commit is deployed:

```bash
install -d -m 0700 /srv/medtrack/backup-secrets /srv/medtrack/offsite-backups
install -d -m 0755 /etc/medtrack-backup
install -m 0600 deploy/backup/backup.env.example /etc/medtrack-backup/backup.env
install -m 0644 deploy/systemd/medtrack-offsite-backup@.service /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-offsite-backup-*.timer /etc/systemd/system/
install -m 0644 deploy/systemd/medtrack-offsite-backup-health.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/medtrack-offsite-backup@.service /etc/systemd/system/medtrack-offsite-backup-*.timer /etc/systemd/system/medtrack-offsite-backup-health.service
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
  medtrack-offsite-backup-health.timer
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

Run and inspect health checks:

```bash
systemctl start medtrack-offsite-backup-health.service
systemctl status --no-pager medtrack-offsite-backup-health.service
journalctl -u 'medtrack-offsite-backup*' --since '24 hours ago' --no-pager
```

Before each production deployment:

```bash
MEDTRACK_BACKUP_CONFIG=/etc/medtrack-backup/backup.env ./scripts/backup-offsite.sh --tier pre-deployment
systemctl start medtrack-nas-export.service
test "$(systemctl show medtrack-nas-export.service --property=Result --value)" = success
```

The second command publishes the newly completed pre-deployment ciphertext immediately instead of waiting for the hourly export timer. It does not contact the NAS; the NAS remains pull-only and fetches on its normal six-hour cadence.

A successful upload is not restore proof. On a separate scratch host, download one completed ciphertext plus its checksum, verify SHA-256, decrypt it with the offline identity, verify the internal `manifest.sha256`, list `database.dump` with `pg_restore --list`, and restore it into a new empty PostgreSQL database. Never test a restore over production.

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
.\gradlew.bat --no-daemon :app:assembleDebug
$apk = Join-Path $env:USERPROFILE ".codex\build\medtrack-android\app\outputs\apk\debug\app-debug.apk"
adb install -r $apk
adb shell pm clear com.naveenhospital.medtrack
adb shell am start -W -n com.naveenhospital.medtrack/.MainActivity
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
- Google Drive `Naveen-Hospital-Backups/MEDTRACK/production/canary/` - encrypted technical canary evidence only; recurring Drive-backed timers are disabled pending policy clearance.
