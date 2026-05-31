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
