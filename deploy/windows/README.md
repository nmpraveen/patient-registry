# Windows independent MEDTRACK verifier

Requires PowerShell 7.2+, a working Bash/Python/coreutils environment, and a separately reviewed source checkout. It does not deploy the app or provision credentials. Install only on the independent verifier, never on the VPS or NAS.

## Private JSON contract

Copy `verifier.example.json` outside Git and replace every example path. Restrict config, status and hooks to the intentional task account and administrators. No secrets belong in this JSON: reference private `backup.env` and alert helper paths.

| Field | Meaning |
|---|---|
| `SourceRoot` | Absolute Windows reviewed checkout path, used for preflight. |
| `BashSourceRoot` | Same checkout in the selected Bash environment, absolute POSIX path. |
| `BashExecutable` | Absolute Bash executable; arguments are passed directly with `ProcessStartInfo.ArgumentList`, never `bash -lc`. |
| `BackupConfigPath` | Absolute Bash path to private `backup.env`; use the same receipt/attempt and health cache for every mode. |
| `DockerExecutable`, `DockerContext` | Absolute Windows Docker CLI and explicit independent local context. |
| `DockerDesktopExecutable` | Optional absolute Desktop executable, started hidden only if Docker is unavailable; omit to fail without startup. |
| `PowerShellExecutable` | Absolute PowerShell 7 executable used by scheduled tasks. |
| `StatusDirectory` | Absolute private Windows directory for atomic latest-attempt JSON records and shared lock. |
| `AlertScriptPath` | Absolute existing Pushover PowerShell helper accepting `-Title` and `-Message`, returning nonzero on delivery failure. Runs as the task account. |
| `RunTimeoutSeconds` | Verifier timeout, 1..21600 (default example 14400). Child process trees are terminated on timeout. |
| `TaskNamePrefix` | Stable task prefix; only letters, digits, `_`, `-`. |

The installer passes status and alert paths separately to the wrapper so malformed/unreadable JSON still produces a failed attempt and an alert. Keep those task arguments synchronized if moving config. A missing/unwritable status destination is explicitly reported and is never success. Bash and its hooks must resolve the same local paths as `SourceRoot`; a WSL/Linux configuration must use that environment's paths and dependencies. For Git Bash with native Windows Python/rclone, verify argument path conversion and NTFS access in the actual task account. Private adapters may translate paths (for example with `cygpath`) but must preserve exit status and every production gate.

`backup.env` supplies `MEDTRACK_SCRATCH_RESTORE_HOOK`, `MEDTRACK_SCRATCH_RESTORE_ALERT_HOOK`, `MEDTRACK_SCRATCH_RESTORE_RECEIPT`, optional `MEDTRACK_SCRATCH_RESTORE_ATTEMPT`, rclone config/remote, health cache, and the live security-evidence hook. See `../backup/backup.env.example`. The restore hook must perform real independent recovery checks for the actual source images. The evidence hook must independently verify a freshly fetched complete chain within the existing two-hour lag gate; a weekly restored evidence snapshot cannot meet that live gate. The Windows health invocation forces `--production` after private config loading; all full-scrub, receipt-age, ciphertext and evidence checks remain mandatory.

## Manual run and registration

```powershell
$configPath = 'C:\IndependentVerifier\private\verifier.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
# Seed real proof in this order, checking each exit code and private artifacts.
./Invoke-MedtrackVerifier.ps1 -ConfigPath $configPath -StatusDirectory $config.StatusDirectory -AlertScriptPath $config.AlertScriptPath -Mode Restore
./Invoke-MedtrackVerifier.ps1 -ConfigPath $configPath -StatusDirectory $config.StatusDirectory -AlertScriptPath $config.AlertScriptPath -Mode FullScrub
./Invoke-MedtrackVerifier.ps1 -ConfigPath $configPath -StatusDirectory $config.StatusDirectory -AlertScriptPath $config.AlertScriptPath -Mode Health
# Explicit current-account policy for new tasks:
./Install-MedtrackVerifierTasks.ps1 -ConfigPath $configPath -AccountPolicy CurrentUserInteractive
# Existing intentional principal, preserved by default:
./Install-MedtrackVerifierTasks.ps1 -ConfigPath $configPath
```

Run these as separate commands and stop on failure. Interactive policy runs only while the account is logged on: it is not logged-out unattended coverage. Default `PreserveExisting` refuses new tasks, preserves each existing principal/logon/run-level, and refuses password-logon re-registration rather than guessing credentials. Provision such tasks using an operator credential-aware route. S4U/network/DPAPI accessibility must be proven under the actual account; registration does not prove access. Explicit interactive policy refuses to replace a different existing account.

Restore runs Saturday 01:00, FullScrub Sunday 01:00, Health daily at 00:00/06:00/12:00/18:00 (machine local time). Weekly full scrubs must remain within the existing eight-day gate. All tasks are hidden, `StartWhenAvailable`, `IgnoreNew`, with execution limit `RunTimeoutSeconds + 600` seconds for startup and alerting. A shared exclusive file lock prevents different modes running concurrently; a collision fails and alerts, so inspect missed/overlapping long runs. The installer reads back principal, logon, triggers, next run, last result and settings. It does not start tasks. Verify actual scheduled executions and off-host alerts before claiming operational completion.

## Results and failure simulation

`StatusDirectory/Restore.json`, `Health.json`, and `FullScrub.json` contain `format`, `mode`, `simulation`, attempt ID, UTC timestamps, `status`, `stage`, `alertDelivery`, and exit code. Success is accepted only after the selected runner exits zero. Health refuses missing/running/failed Restore or FullScrub state; FullScrub requires successful Restore state. For restore, the shell additionally records the same-directory `.attempt` (or explicit override), and binds success to the exact receipt ID and SHA-256. Old receipts without this contract need a real rerun. Interrupted runs stay `running` and fail closed. No raw hook output is persisted by the generic wrapper; private hooks can maintain restricted logs if needed, without PHI/secrets in status or notifications.

```powershell
./Invoke-MedtrackVerifier.ps1 -ConfigPath $configPath -StatusDirectory $config.StatusDirectory -AlertScriptPath $config.AlertScriptPath -Mode Restore -SimulateFailure Docker
```

Allowed simulations: `Preflight`, `Docker`, `Launch`, `Runner`, `Alert`. They write only `StatusDirectory/simulation/<Mode>.json`, never read private JSON, start Docker/Bash, send notifications, or replace real status. They always fail (exit 1; alert-delivery simulation exits 2). They exercise wrapper failure reporting only, and are not proof of real restore, scheduler execution or alert delivery. The automated test suite separately injects fake executable/helper failures through the real process-launch path.
