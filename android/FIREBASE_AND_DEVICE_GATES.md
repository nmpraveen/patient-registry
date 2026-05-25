# MEDTRACK Android external gate checklist

This file is the handoff for the remaining v1 gates that cannot be completed
without Firebase project material and a physical Android phone. Do not put
secrets, raw FCM tokens, service-account JSON, PHI, or patient screenshots in
Git.

## Current local proof

Local implementation is already covered by:

- `.\android\scripts\mobile-api-smoke.ps1`
- `.\android\scripts\mobile-test-suite.ps1`
- `.\android\scripts\biometric-emulator-smoke.ps1`
- `.\android\scripts\local-emulator-smoke.ps1 -OfflineWrites`
- `.\android\scripts\mobile-push-smoke.ps1`
- `.\android\scripts\medtrack-v1-audit.ps1`

The audit remains incomplete until the external gates below pass.

## Latest verified baseline

As of `2026-05-19T00:16:59Z`, local implementation and Test NNH verification
are passing.

- Latest audit report:
  `output/medtrack-v1-audit-20260518-201658/report.md`
- Latest audit summary:
  `output/medtrack-v1-audit-20260518-201658/summary.json`
- Current debug APK:
  `%USERPROFILE%/.codex/build/medtrack-android/app/outputs/apk/debug/app-debug.apk`
- Current debug APK SHA256:
  `4851E6738C8B00435E2E3B6C1EE449B9717F8DA9A88FC1AA6138AB8618469E79`
- Full emulator/offline smoke:
  `output/android-emulator-smoke-20260518-194636/summary.json`
- Full Django plus Android unit-test gate:
  `output/mobile-test-suite-20260518-201257/summary.json`
- Firebase preflight blocker evidence:
  `output/mobile-push-preflight-20260518-201557/summary.json`
- Physical-device preflight blocker evidence:
  `output/android-physical-device-smoke-20260518-201631/summary.json`

## Firebase inputs needed

Provide these locally only:

- `android/app/google-services.json`
- Firebase Admin SDK service account JSON on the host
- `MEDTRACK_FCM_TEST_TOKEN`, only if running direct-token push smoke
- `FCM_ENABLED=True`
- `FCM_CREDENTIALS_FILE=<host path to Firebase Admin SDK JSON>`
- `FCM_PROJECT_ID=<Firebase project id>` if the service account does not carry
  the intended project id

The repo root `.gitignore` already excludes:

- `android/app/google-services.json`
- `firebase-service-account*.json`
- `*firebase-adminsdk*.json`
- `*service-account*.json`

## Firebase readiness commands

From the repo root:

```powershell
.\android\scripts\mobile-push-preflight.ps1 -RequireReady
```

This must pass before attempting real delivery.

Direct-token server delivery smoke:

```powershell
.\android\scripts\mobile-push-smoke.ps1 -RequireFirebase
```

Full real-device delivery smoke:

```powershell
.\android\scripts\mobile-real-push-smoke.ps1 -NoBuild
```

The full real-device script runs physical-device offline-write smoke first,
waits for the app to register its device token, sends a push through Django,
and checks the Android notification surface through `adb`.

## Physical phone inputs needed

Use a low-end or representative clinic phone where possible.

- USB debugging enabled
- Device authorized in `adb devices`
- Battery saver disabled for the smoke run
- Notifications allowed for MEDTRACK when prompted
- Local Test NNH server can be reached through `adb reverse`

Physical smoke command:

```powershell
.\android\scripts\physical-device-smoke.ps1 -OfflineWrites
```

The v1 audit only counts this gate when the summary proves:

- `requirePhysicalDevice=true`
- `adbReverse=true`
- `apiBaseUrl=http://127.0.0.1:8000/`
- offline task completion queued and synced
- offline call outcome queued and synced
- offline vitals queued and synced

## Two-user field test record

After physical smoke passes, run this without recording patient names or PHI:

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

If issues are found, summarize behavior only. Do not include PHI, phone
numbers, patient names, screenshots with patient data, or raw tokens.

## Final audit

After the external gates pass:

```powershell
.\android\scripts\medtrack-v1-audit.ps1
```

The goal is complete only when this audit reports `goalComplete=true`.
