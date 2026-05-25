# MEDTRACK Android v1

Native Android companion app for MEDTRACK using Kotlin, Jetpack Compose, Room, WorkManager, Retrofit, and Firebase Cloud Messaging.

This directory is intentionally separate from the Django app. The Retrofit API points at the DRF mobile endpoints mounted under `/api/...` in this repo.

## Design reference

The app follows the Canva V2a direction as product guidance, not a pixel-perfect target:

- Source design: [MEDTRACK Android - Three Directions](https://www.canva.com/d/HaGkmevHt_3PPWh)
- Local inspection folder: [`../.codex/canva-inspection/`](../.codex/canva-inspection/)
- Home card crop: [`../.codex/canva-inspection/medtrack-home-phone-crop.png`](../.codex/canva-inspection/medtrack-home-phone-crop.png)
- Behavior states crop: [`../.codex/canva-inspection/medtrack-behaviors-phone-crop.png`](../.codex/canva-inspection/medtrack-behaviors-phone-crop.png)

Preserve these V2a traits in implementation: search at top, tappable stat strip, Today/Upcoming/Overdue/Awaiting/Red pills, compact expandable patient cards, Healthicons category/subcategory icons, red-flag reasons sheet, swipe-left Call, swipe-right Done, and a dense rural-clinic worklist layout.

## Modules

- `:app` - Android entry point, navigation shell, manifest.
- `:core:designsystem` - MEDTRACK Compose theme, colors, shared surfaces.
- `:core:domain` - app-facing models.
- `:core:network` - Retrofit service and DTOs.
- `:core:data` - Room entities, DAOs, repository, WorkManager sync worker.
- `:core:push` - Firebase Messaging channels, token registration, and notification display.
- `:feature:auth` - login, biometric, and pattern unlock screens.
- `:feature:home` - Canva V2a-inspired inbox, filters, card actions, and offline write status.
- `:feature:case` - case detail, task completion, vitals history, and vitals entry.
- `:feature:calls` - call outcome sheet and call workflow surfaces.
- `:feature:notifications` - notification inbox.

## V1 phase map

| Phase | Current implementation surface | Verification |
|---|---|---|
| Phase 0 - Bootstrap | Gradle modules, app id `com.naveenhospital.medtrack`, Material 3 theme, Roboto Flex, Healthicons vector drawables. | `.\gradlew.bat --no-daemon :app:assembleDebug` |
| Phase 1 - Django API | `../api/` DRF app, JWT auth, case/task/vitals/notifications/devices endpoints, vitals thresholds extraction. | `docker compose exec web python manage.py test` |
| Phase 2 - Auth and lock | Username/password login, encrypted refresh token, in-memory access token, pattern unlock, biometric unlock, 15-minute relock. | `.\android\scripts\local-emulator-smoke.ps1` covers login, biometric availability gating, and pattern unlock; `.\android\scripts\biometric-emulator-smoke.ps1` covers successful biometric auth on an enrolled AVD. |
| Phase 3 - Home inbox | Canva V2a-inspired inbox, search, counters, filters, expandable cards, red sheet, swipe call/done. | `.\android\scripts\local-emulator-smoke.ps1` |
| Phase 4 - Case detail and writes | Case detail, task completion, vitals form, call outcome sheet, optimistic writes with `client_write_id`. | `.\android\scripts\local-emulator-smoke.ps1 -OfflineWrites` |
| Phase 5 - Offline sync | Room caches and WorkManager pending-write drain for task/call/vitals/notification-read writes, plus 409 server-wins conflict records. | `.\android\scripts\local-emulator-smoke.ps1 -OfflineWrites` |
| Phase 6 - FCM and notifications | Env-gated Firebase token registration, notification channels, Django notification log and push dispatch. | `.\android\scripts\mobile-push-smoke.ps1` verifies missing-config safety; pass `-RequireFirebase` with `MEDTRACK_FCM_TEST_TOKEN` for real delivery. |
| Phase 7 - Polish and field testing | Empty/loading/error states, pull-to-refresh, low-light Material 3 surface treatment, Crashlytics-gated build support. | Emulator smoke passes; low-end offline-write device smoke and 2-user field test are still field gates. |

## Open

Open the `android/` directory in Android Studio. If you use the command line, run Gradle from this folder with an installed Android SDK:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug
```

## Emulator Backend

The debug build defaults to the local Test NNH server through Android Emulator host loopback:

```text
MEDTRACK_API_BASE_URL=http://10.0.2.2:8000/
```

That maps to the Django server at `http://localhost:8000` on the Windows host. Override it for another target:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug -PMEDTRACK_API_BASE_URL=https://example.com/
```

## Local Emulator Smoke

Use the same local Android emulator workflow as the MarkUS project. This machine has the `MarkUS_Latest_API37` and `MarkUS_Local` AVDs installed, plus `adb.exe` on PATH and `emulator.exe` at:

```powershell
$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe
```

For the repeatable smoke path, run this from the repo root:

```powershell
.\android\scripts\local-emulator-smoke.ps1
```

The script starts or reuses the local Test NNH backend, verifies Local Server Dashboard discovery, builds and installs the debug APK, drives login/pattern/home, checks biometric availability messaging, checks the V2a inbox/card interactions, opens case detail, adds a vital reading, opens the notification inbox, simulates a notification-tap deep link into case detail, saves screenshots/XML plus summary JSON under `output/android-emulator-smoke-*`, and cleans up only the server/emulator/dashboard processes it started.

Use the offline gate when validating Phase 5 behavior:

```powershell
.\android\scripts\local-emulator-smoke.ps1 -OfflineWrites
```

That path disables emulator network, queues task completion, call outcome, and vitals writes, restores network, forces WorkManager, and confirms the Test NNH server received the synced rows.

## Local Biometric Smoke

Use the MarkUS AVD for a repeatable enrolled-biometric verification:

```powershell
.\android\scripts\biometric-emulator-smoke.ps1
```

The script starts or reuses Test NNH, ensures `MarkUS_Latest_API37` has a fingerprint enrolled, installs the debug APK, logs in, enables MEDTRACK biometric unlock, force-stops/reopens the app, authenticates with `adb emu finger touch 1`, confirms the inbox is restored, writes `summary.json` under `output/android-biometric-smoke-*`, and cleans up only the server/emulator/dashboard processes it started.

## Local API Smoke

Use this before or after emulator runs when you need direct evidence that the DRF mobile surface works against the local Test NNH backend:

```powershell
.\android\scripts\mobile-api-smoke.ps1
```

The script starts or reuses `http://localhost:8000`, verifies Local Server Dashboard discovery, logs in with the local demo credentials, smokes `/api/me/`, category metadata, vitals thresholds, case list/detail, device registration, all three mobile writes, notifications read, token refresh, and logout. It stores each response plus `summary.json` under `output/mobile-api-smoke-*` and stops only the server/dashboard processes it started.

## Local Test Suite

Run the backend and Android unit-test gate from the repo root:

```powershell
.\android\scripts\mobile-test-suite.ps1
```

The script starts or reuses Test NNH, runs `docker compose exec -T web python manage.py test`, runs `.\gradlew.bat --no-daemon testDebugUnitTest` from `android/`, writes logs plus `summary.json` under `output/mobile-test-suite-*`, and stops only the Test NNH server it started.

For manual testing, start or reuse the local Django backend from the repo root:

```powershell
.\local-dev\test-nnh-up.ps1
```

Then build and install the debug APK from `android/`:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug
$apk = Join-Path $env:USERPROFILE ".codex\build\medtrack-android\app\outputs\apk\debug\app-debug.apk"
adb install -r $apk
adb shell monkey -p com.naveenhospital.medtrack 1
```

Gradle writes Android build outputs to `%USERPROFILE%\.codex\build\medtrack-android` by default so Dropbox does not convert generated `.class` files into placeholder reparse points. Set `MEDTRACK_ANDROID_BUILD_DIR` before running Gradle if you need a different local build-output path.

If no emulator is running, start the AVD first:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd MarkUS_Latest_API37
```

For this local emulator path, keep the default `http://10.0.2.2:8000/` API base URL. Do not use `10.0.2.2` for shared APKs or handoff builds.

## Physical Device Smoke

For low-end phone verification over USB, connect the phone with USB debugging enabled and run from the repo root:

```powershell
.\android\scripts\physical-device-smoke.ps1 -OfflineWrites
```

The wrapper uses `adb reverse tcp:8000 tcp:8000`, builds the debug APK with `MEDTRACK_API_BASE_URL=http://127.0.0.1:8000/`, runs the same login/home/card/case/notification/offline-write smoke against the local Test NNH server, and writes evidence under `output/android-physical-device-smoke-*`. This avoids LAN exposure for the local Django server. The v1 audit only counts the physical-device gate when this summary also proves offline task, call, and vitals writes queued and synced.

## Two-user Field Test Record

After the low-end physical-device smoke passes, record the two-user field-test gate without storing patient names or PHI:

```powershell
.\android\scripts\field-test-record.ps1 `
  -DeviceModel "Redmi 9A" `
  -AndroidVersion "12" `
  -Tester1Role "Nurse" `
  -Tester2Role "Caller" `
  -HomeInboxPassed `
  -CallDonePassed `
  -VitalsPassed `
  -OfflineSyncPassed `
  -LockUnlockPassed `
  -ReadabilityPassed `
  -NoCrashOrAnr `
  -Issues "None"
```

To create a blank checklist artifact before field testing:

```powershell
.\android\scripts\field-test-record.ps1 -CreateTemplate
```

The script writes `summary.json` and `report.md` under `output/android-field-test-*`. The verification audit counts the field-test gate only when it finds both a passing physical-device offline-write smoke and a passing two-user field-test record.

## Firebase / Crashlytics

The app builds without Firebase project secrets. When `android/app/google-services.json` exists, the build automatically applies the Google Services and Crashlytics Gradle plugins. Without that file, FCM token fetch is skipped at runtime and normal login/API/offline sync still works.

The remaining Firebase and physical-device gates are tracked in `FIREBASE_AND_DEVICE_GATES.md`. That file lists the exact local-only files, environment variables, and smoke commands needed once Firebase credentials and a USB Android phone are available.

## Local Push Smoke

Use this to verify that the Django FCM dispatch boundary is safe in local Test NNH:

```powershell
.\android\scripts\mobile-push-smoke.ps1
```

With no Firebase credentials configured, the expected result is `sent=false` with `reason=fcm_not_configured`; that is a pass because normal API writes must not break without Firebase secrets. For a real Firebase delivery smoke, set a real Android FCM registration token in `MEDTRACK_FCM_TEST_TOKEN`, configure `FCM_ENABLED=True` plus `FCM_CREDENTIALS_FILE`, and run:

```powershell
.\android\scripts\mobile-push-smoke.ps1 -RequireFirebase
```

The script redacts the token from evidence, creates a local mobile notification, calls Django's `send_mobile_notification`, writes `summary.json` under `output/mobile-push-smoke-*`, and stops only the Test NNH server/dashboard processes it started.

Before attempting real delivery, check every required Firebase prerequisite with:

```powershell
.\android\scripts\mobile-push-preflight.ps1
```

The preflight checks `android/app/google-services.json`, `MEDTRACK_FCM_TEST_TOKEN`, `FCM_ENABLED`, `FCM_CREDENTIALS_FILE`, whether the credentials file exists on the host, and whether Django reports `firebase_configured() == true`. It writes `summary.json` under `output/mobile-push-preflight-*` without printing secrets.

For the full real-device delivery gate, connect a USB Android phone, configure Firebase for both Android and Django, then run:

```powershell
.\android\scripts\mobile-real-push-smoke.ps1
```

This wrapper runs the physical-device offline-write smoke, waits for the app to register its real FCM token with Django, sends a Firebase push to that registered token, checks the device notification surface through `adb`, and writes redacted evidence under `output/mobile-real-push-smoke-*`. It never writes the raw FCM token to the evidence files.

## V1 Verification Audit

After running the API, test-suite, emulator/offline, biometric, physical-device when available, push preflight, push smoke, and real-device push scripts, consolidate the current local proof with:

```powershell
.\android\scripts\medtrack-v1-audit.ps1
```

The audit compares the latest passing smoke artifacts against the current APK hash, checks required local evidence, and writes `summary.json` plus `report.md` under `output/medtrack-v1-audit-*`. It keeps real Firebase delivery and low-end/field testing as external gates until those artifacts exist.
