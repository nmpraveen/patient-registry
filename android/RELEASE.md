# Android Release Runbook

## Release environments

The app has three environment flavors:

| Flavor | Application ID | Default API | Debug build |
|---|---|---|---|
| `dev` | `com.naveenhospital.medtrack.dev` | `http://10.0.2.2:8000/` | enabled |
| `stage` | `com.naveenhospital.medtrack.stage` | `https://medtrack-stage.invalid/` | enabled |
| `prod` | `com.naveenhospital.medtrack` | `https://book.naveenhospital.net/` | disabled |

The deliberately invalid stage default prevents an unconfigured stage build
from talking to production. Override the URLs with
`MEDTRACK_DEV_API_BASE_URL`, `MEDTRACK_STAGE_API_BASE_URL`, or
`MEDTRACK_PROD_API_BASE_URL` as Gradle properties or environment variables.

Release metadata is stored in `version.properties`. `VERSION_CODE` must only
increase for uploaded artifacts. `VERSION_NAME` uses `YYYY.M.D.REVISION`.

## External signing

No keystore, password, alias, or service credential belongs in the repository.
Set all four values in the release environment:

```text
MEDTRACK_SIGNING_STORE_FILE
MEDTRACK_SIGNING_STORE_PASSWORD
MEDTRACK_SIGNING_KEY_ALIAS
MEDTRACK_SIGNING_KEY_PASSWORD
```

A partial signing configuration fails during Gradle configuration. With none of
the values present, `unsignedReleaseArtifacts` produces review-only unsigned
APK/AAB files. With all four present, use `bundleProdForPlay`; it verifies that
signing is configured before building the production AAB.

## Reproducible release gate

Run from `android/` in a clean exact-head checkout:

```powershell
.\gradlew.bat --no-daemon --max-workers=1 test
.\gradlew.bat --no-daemon --max-workers=1 lint
.\gradlew.bat --no-daemon --max-workers=1 assembleDevDebug
.\gradlew.bat --no-daemon --max-workers=1 unsignedReleaseArtifacts
.\scripts\verify-dependencies.ps1
.\scripts\build-release-artifacts.ps1 -SkipBuild
```

Gradle outputs stay in this worktree under `android/.build/`. Audited handoff
artifacts are copied to `android/release-artifacts/<version>/<git-sha>/` with:

- unsigned production APK and AAB;
- `SHA256SUMS.txt`;
- CycloneDX `sbom.cdx.json` built from committed dependency locks;
- `provenance.json` with source/build identity;
- `artifact-audit.json` proving the package scan passed.

The committed wrapper JAR hash and strict Gradle dependency locks are checked
offline by `verify-dependencies.ps1`. Regenerate locks only during an intentional
dependency update with the relevant task plus `--write-locks`, inspect the diff,
and then rerun the offline gate without `--write-locks`.

The full `lint` task resolves Android-test lint models as well as production
models. If strict mode reports that
`:app:devDebugAndroidTestCompileClasspath` has no lock state after a deliberate
toolchain/configuration change, regenerate it once with `lint --write-locks`,
review the lock diff, and prove the normal strict-mode `lint` command passes.

## Play compatibility

The project compiles and targets Android API 36. It uses Android Gradle Plugin
8.9.1 with Gradle 8.11.1, the documented minimum-compatible toolchain for API
36. The production release format is Android App Bundle (AAB).

This build readiness does not override the broader MEDTRACK release NO-GO:
account-scoped encrypted local state, a verified PHI-free server FCM producer,
exact server contract coordination, real Firebase delivery, physical-device
validation, and the two-user field test remain external gates. The Android
consumer posts no raw-FCM system notification, ignores all untrusted FCM
display/case/phone fields, and treats push only as a request for authenticated
API refresh.
