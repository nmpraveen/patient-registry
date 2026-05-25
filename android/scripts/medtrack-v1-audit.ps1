[CmdletBinding()]
param(
    [string]$EvidenceDir = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$androidRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $androidRoot
$outputRoot = Join-Path $repoRoot "output"

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDir = Join-Path $outputRoot "medtrack-v1-audit-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function Save-Json {
    param(
        [string]$Path,
        [object]$Value,
        [int]$Depth = 12
    )
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -Path $Path
}

function Get-SummaryCandidates {
    param([string]$Filter)
    if (-not (Test-Path $outputRoot)) {
        return @()
    }
    @(Get-ChildItem -Path $outputRoot -Directory -Filter $Filter -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object {
            $summaryPath = Join-Path $_.FullName "summary.json"
            if (Test-Path $summaryPath) {
                [pscustomobject]@{
                    Directory = $_.FullName
                    LastWriteTime = $_.LastWriteTime
                    SummaryPath = $summaryPath
                    Summary = Get-Content -Raw -Path $summaryPath | ConvertFrom-Json
                }
            }
        })
}

function Find-LatestPassingSummary {
    param(
        [string]$Filter,
        [scriptblock]$Predicate
    )
    foreach ($candidate in (Get-SummaryCandidates -Filter $Filter)) {
        if ($candidate.Summary.passed -eq $true -and (& $Predicate $candidate.Summary)) {
            return $candidate
        }
    }
    return $null
}

function Test-TruthyProperty {
    param(
        [object]$Object,
        [string]$Property
    )
    if ($null -eq $Object) {
        return $false
    }
    $propertyInfo = $Object.PSObject.Properties[$Property]
    if ($null -eq $propertyInfo) {
        return $false
    }
    $value = $propertyInfo.Value
    return $value -eq $true
}

function New-Requirement {
    param(
        [string]$Id,
        [string]$Requirement,
        [string]$Status,
        [string]$Evidence,
        [string]$Notes = ""
    )
    [ordered]@{
        id = $Id
        requirement = $Requirement
        status = $Status
        evidence = $Evidence
        notes = $Notes
    }
}

function Format-RequirementRow {
    param([object]$Requirement)
    $notes = ($Requirement.notes -replace "\|", "\/")
    $evidence = ((Format-EvidenceValue $Requirement.evidence) -replace "\|", "\/")
    return "| $($Requirement.id) | $($Requirement.status) | $($Requirement.requirement) | $evidence | $notes |"
}

function Format-MarkdownPath {
    param([string]$Path)
    $label = Split-Path -Leaf $Path
    $parent = Split-Path -Parent $Path
    if ($label -eq "summary.json" -or $label -eq "report.md") {
        $parentName = if ($parent) { Split-Path -Leaf $parent } else { "" }
        if ($parentName) {
            $label = "$parentName/$label"
        }
    }
    if ([string]::IsNullOrWhiteSpace($label)) {
        $label = $Path
    }
    return "[$label](<$Path>)"
}

function Format-EvidenceValue {
    param([object]$Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) {
        return "Not run."
    }
    $text = [string]$Value
    if ($text -like "*; *") {
        return (($text -split ";\s*" | ForEach-Object { Format-EvidenceValue $_ }) -join "; ")
    }
    if ($text -match "^[A-Za-z]:\\") {
        return Format-MarkdownPath -Path $text
    }
    return $text
}

$gradleBuildRoot = if ($env:MEDTRACK_ANDROID_BUILD_DIR) {
    $env:MEDTRACK_ANDROID_BUILD_DIR
}
else {
    Join-Path $env:USERPROFILE ".codex\build\medtrack-android"
}
$apkPath = Join-Path $gradleBuildRoot "app\outputs\apk\debug\app-debug.apk"
$apkHash = if (Test-Path $apkPath) { (Get-FileHash -Path $apkPath -Algorithm SHA256).Hash } else { "" }

$apiSmoke = Find-LatestPassingSummary -Filter "mobile-api-smoke-*" -Predicate {
    param($summary)
    $checks = $summary.checks
    $requiredChecks = @(
        "hasJwtLogin",
        "hasMe",
        "hasCategories",
        "hasVitalsThresholds",
        "hasCaseListTarget",
        "hasCaseDetail",
        "hasDeviceRegistration",
        "hasCallOutcomeWrite",
        "hasVitalsWrite",
        "hasTaskCompletionWrite",
        "hasNotificationList",
        "hasNotificationRead",
        "hasTokenRefresh",
        "hasLogout",
        "hasDashboardDiscovery"
    )
    $missing = @($requiredChecks | Where-Object { -not (Test-TruthyProperty -Object $checks -Property $_) })
    return $missing.Count -eq 0
}

$emulatorSmoke = Find-LatestPassingSummary -Filter "android-emulator-smoke-*" -Predicate {
    param($summary)
    $checks = $summary.checks
    $requiredChecks = @(
        "hasInbox",
        "hasSearch",
        "hasToday",
        "hasOverdue",
        "hasPatientRows",
        "hasRedFlagPill",
        "hasBottomNavigationOnHome",
        "hasCategoryFilterSheet",
        "hasSubcategoryFilterSheet",
        "hasInlineExpandedCard",
        "hasOpenCaseAction",
        "hasRiskReasonsSheet",
        "hasBiometricAvailabilityState",
        "hasPatternRelockScreen",
        "hasPatternUnlockRestoredSession",
        "hasOfflineTaskQueued",
        "hasOfflineCallQueued",
        "hasOfflineVitalsQueued",
        "hasOfflineWritesSynced",
        "hasSwipeCallDialer",
        "hasSwipeCallOutcomeSheet",
        "hasSwipeDoneSnackbar",
        "hasSwipeDoneResult",
        "hasCaseDetail",
        "hasVitalsRecorded",
        "hasNotificationsScreen",
        "hasNotificationDeepLink"
    )
    $missing = @($requiredChecks | Where-Object { -not (Test-TruthyProperty -Object $checks -Property $_) })
    return $missing.Count -eq 0 -and $summary.offlineWrites -ne $null
}

$pushSmoke = Find-LatestPassingSummary -Filter "mobile-push-smoke-*" -Predicate {
    param($summary)
    $checks = $summary.checks
    return (Test-TruthyProperty -Object $checks -Property "hasNotificationRow") -and
        (Test-TruthyProperty -Object $checks -Property "hasDeviceTokenRow") -and
        (Test-TruthyProperty -Object $checks -Property "hasFirebaseConfigStatus") -and
        (
            (Test-TruthyProperty -Object $checks -Property "hasExpectedMissingConfigResult") -or
            (Test-TruthyProperty -Object $checks -Property "hasRealDeliveryAttempt")
        )
}

$pushPreflight = @(
    Get-SummaryCandidates -Filter "mobile-push-preflight-*" |
        Sort-Object LastWriteTime -Descending
)[0]

$realPushSmoke = Find-LatestPassingSummary -Filter "mobile-real-push-smoke-*" -Predicate {
    param($summary)
    $checks = $summary.checks
    return $summary.usingRegisteredDeviceToken -eq $true -and
        (Test-TruthyProperty -Object $checks -Property "hasPhysicalDeviceSmoke") -and
        (Test-TruthyProperty -Object $checks -Property "hasRegisteredDeviceToken") -and
        (Test-TruthyProperty -Object $checks -Property "hasFirebaseConfigured") -and
        (Test-TruthyProperty -Object $checks -Property "hasDeliverySent") -and
        (Test-TruthyProperty -Object $checks -Property "hasDeviceNotificationEvidence")
}

$realPushDeliveryProved = ($realPushSmoke -ne $null) -or ($pushSmoke -and
    $pushSmoke.Summary.requireFirebase -eq $true -and
    $pushSmoke.Summary.usingRealToken -eq $true -and
    $pushSmoke.Summary.firebaseConfigured -eq $true -and
    $pushSmoke.Summary.deliveryResult.sent -eq $true)

$biometricSmoke = Find-LatestPassingSummary -Filter "android-biometric-smoke-*" -Predicate {
    param($summary)
    $checks = $summary.checks
    $requiredChecks = @(
        "hasFingerprintEnrollment",
        "hasBiometricAvailableOnSetup",
        "hasEnablePrompt",
        "hasBiometricEnabledMessage",
        "hasUnlockScreenUseBiometric",
        "hasUnlockPrompt",
        "hasBiometricUnlockRestoredHome",
        "hasDashboardDiscovery"
    )
    $missing = @($requiredChecks | Where-Object { -not (Test-TruthyProperty -Object $checks -Property $_) })
    return $missing.Count -eq 0
}

$physicalDeviceSmoke = Find-LatestPassingSummary -Filter "android-physical-device-smoke-*" -Predicate {
    param($summary)
    $checks = $summary.checks
    $requiredChecks = @(
        "hasInbox",
        "hasSearch",
        "hasToday",
        "hasOverdue",
        "hasPatientRows",
        "hasRedFlagPill",
        "hasBottomNavigationOnHome",
        "hasCategoryFilterSheet",
        "hasSubcategoryFilterSheet",
        "hasInlineExpandedCard",
        "hasOpenCaseAction",
        "hasRiskReasonsSheet",
        "hasBiometricAvailabilityState",
        "hasPatternRelockScreen",
        "hasPatternUnlockRestoredSession",
        "hasOfflineTaskQueued",
        "hasOfflineCallQueued",
        "hasOfflineVitalsQueued",
        "hasOfflineWritesSynced",
        "hasSwipeCallDialer",
        "hasSwipeCallOutcomeSheet",
        "hasSwipeDoneSnackbar",
        "hasSwipeDoneResult",
        "hasCaseDetail",
        "hasVitalsRecorded",
        "hasNotificationsScreen",
        "hasNotificationDeepLink"
    )
    $missing = @($requiredChecks | Where-Object { -not (Test-TruthyProperty -Object $checks -Property $_) })
    return $missing.Count -eq 0 -and
        $summary.requirePhysicalDevice -eq $true -and
        $summary.adbReverse -eq $true -and
        $summary.apiBaseUrl -eq "http://127.0.0.1:8000/" -and
        $summary.offlineWrites -ne $null
}

$physicalDevicePreflight = @(
    Get-SummaryCandidates -Filter "android-physical-device-*" |
        Where-Object {
            $_.Summary.passed -eq $false -and
            $_.Summary.reason -eq "no_physical_device"
        }
)[0]

$fieldTest = Find-LatestPassingSummary -Filter "android-field-test-*" -Predicate {
    param($summary)
    $checks = $summary.checks
    $requiredChecks = @(
        "homeInboxPassed",
        "callDonePassed",
        "vitalsPassed",
        "offlineSyncPassed",
        "lockUnlockPassed",
        "readabilityPassed",
        "noCrashOrAnr"
    )
    $missing = @($requiredChecks | Where-Object { -not (Test-TruthyProperty -Object $checks -Property $_) })
    return $summary.templateOnly -ne $true -and
        $summary.userCount -ge 2 -and
        -not [string]::IsNullOrWhiteSpace([string]$summary.physicalSmokeSummary) -and
        $summary.physicalSmokeOfflineWritesValid -eq $true -and
        $missing.Count -eq 0
}

$mobileTestSuite = Find-LatestPassingSummary -Filter "mobile-test-suite-*" -Predicate {
    param($summary)
    return $summary.django.skipped -ne $true -and
        $summary.android.skipped -ne $true -and
        $summary.django.exitCode -eq 0 -and
        $summary.android.exitCode -eq 0
}

$moduleChecks = [ordered]@{
    androidRoot = Test-Path (Join-Path $repoRoot "android\settings.gradle.kts")
    appModule = Test-Path (Join-Path $repoRoot "android\app\build.gradle.kts")
    domainModule = Test-Path (Join-Path $repoRoot "android\core\domain\build.gradle.kts")
    dataModule = Test-Path (Join-Path $repoRoot "android\core\data\build.gradle.kts")
    networkModule = Test-Path (Join-Path $repoRoot "android\core\network\build.gradle.kts")
    pushModule = Test-Path (Join-Path $repoRoot "android\core\push\build.gradle.kts")
    authFeature = Test-Path (Join-Path $repoRoot "android\feature\auth\build.gradle.kts")
    homeFeature = Test-Path (Join-Path $repoRoot "android\feature\home\build.gradle.kts")
    caseFeature = Test-Path (Join-Path $repoRoot "android\feature\case\build.gradle.kts")
    notificationsFeature = Test-Path (Join-Path $repoRoot "android\feature\notifications\build.gradle.kts")
}

$apiFileChecks = [ordered]@{
    apiUrls = Test-Path (Join-Path $repoRoot "api\urls.py")
    apiViews = Test-Path (Join-Path $repoRoot "api\views.py")
    apiSerializers = Test-Path (Join-Path $repoRoot "api\serializers.py")
    apiModels = Test-Path (Join-Path $repoRoot "api\models.py")
    vitalsThresholds = Test-Path (Join-Path $repoRoot "patients\vitals_thresholds.py")
}

$dashboardSnapshot = if ($apiSmoke) { Test-Path (Join-Path $apiSmoke.Directory "dashboard-snapshot.json") } else { $false }
$currentApkMatchesSmoke = $apkHash -and $emulatorSmoke -and ($emulatorSmoke.Summary.apkSha256 -eq $apkHash)
$offlineWritesProved = $emulatorSmoke -and
    $emulatorSmoke.Summary.offlineWrites.afterCallLogCount -gt $emulatorSmoke.Summary.offlineWrites.beforeCallLogCount -and
    $emulatorSmoke.Summary.offlineWrites.afterVitalCount -gt $emulatorSmoke.Summary.offlineWrites.beforeVitalCount

$adbDevices = (adb devices | Out-String).Trim()
$port8000 = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)

$requirements = @(
    New-Requirement `
        -Id "R1" `
        -Requirement "Native Android Kotlin/Compose project exists with app/core/feature module split." `
        -Status ($(if (($moduleChecks.Values | Where-Object { $_ -ne $true }).Count -eq 0) { "passed" } else { "failed" })) `
        -Evidence "android/settings.gradle.kts and expected module build files" `
        -Notes "App package is com.naveenhospital.medtrack."
    New-Requirement `
        -Id "R2" `
        -Requirement "DRF API app and shared vitals-threshold module exist without altering core patient schemas." `
        -Status ($(if (($apiFileChecks.Values | Where-Object { $_ -ne $true }).Count -eq 0) { "passed" } else { "failed" })) `
        -Evidence "api/*.py and patients/vitals_thresholds.py" `
        -Notes "Schema-altering patient model changes are not asserted by this audit."
    New-Requirement `
        -Id "R3" `
        -Requirement "Mobile REST surface works against local Test NNH with JWT, cases, writes, thresholds, notifications, and device registration." `
        -Status ($(if ($apiSmoke) { "passed" } else { "missing" })) `
        -Evidence ($(if ($apiSmoke) { $apiSmoke.SummaryPath } else { "No passing mobile-api-smoke summary found." })) `
        -Notes ($(if ($dashboardSnapshot) { "Dashboard discovery evidence present." } else { "Dashboard snapshot missing." }))
    New-Requirement `
        -Id "R4" `
        -Requirement "Current debug APK is the same artifact used in the latest full emulator/offline smoke." `
        -Status ($(if ($currentApkMatchesSmoke) { "passed" } else { "failed" })) `
        -Evidence ($(if ($emulatorSmoke) { $emulatorSmoke.SummaryPath } else { "No passing android-emulator-smoke summary found." })) `
        -Notes "Current APK SHA256: $apkHash"
    New-Requirement `
        -Id "R5" `
        -Requirement "Canva-style home flow with bottom navigation, search, counters/buckets, category/sub-category filters, inline card expansion with Open case, red-flag reasons sheet, card gestures, case detail, vitals, notifications, and deep link are emulator-smoked." `
        -Status ($(if ($emulatorSmoke) { "passed" } else { "missing" })) `
        -Evidence ($(if ($emulatorSmoke) { $emulatorSmoke.SummaryPath } else { "No passing android-emulator-smoke summary found." })) `
        -Notes ($(if ($emulatorSmoke) { "Biometric availability: $($emulatorSmoke.Summary.biometricAvailability); bottomNav=$($emulatorSmoke.Summary.checks.hasBottomNavigationOnHome); filters=$($emulatorSmoke.Summary.checks.hasCategoryFilterSheet)/$($emulatorSmoke.Summary.checks.hasSubcategoryFilterSheet); expanded=$($emulatorSmoke.Summary.checks.hasInlineExpandedCard); openCase=$($emulatorSmoke.Summary.checks.hasOpenCaseAction); redSheet=$($emulatorSmoke.Summary.checks.hasRiskReasonsSheet)" } else { "" }))
    New-Requirement `
        -Id "R6" `
        -Requirement "Offline-first task, call outcome, and vitals writes queue offline and drain through WorkManager." `
        -Status ($(if ($offlineWritesProved) { "passed" } else { "missing" })) `
        -Evidence ($(if ($emulatorSmoke) { $emulatorSmoke.SummaryPath } else { "No passing offline emulator smoke summary found." })) `
        -Notes ($(if ($offlineWritesProved) { "Call logs $($emulatorSmoke.Summary.offlineWrites.beforeCallLogCount) -> $($emulatorSmoke.Summary.offlineWrites.afterCallLogCount); vitals $($emulatorSmoke.Summary.offlineWrites.beforeVitalCount) -> $($emulatorSmoke.Summary.offlineWrites.afterVitalCount)." } else { "" }))
    New-Requirement `
        -Id "R7" `
        -Requirement "FCM dispatch boundary is locally verified and does not break normal use when Firebase credentials are absent." `
        -Status ($(if ($pushSmoke) { "passed" } else { "missing" })) `
        -Evidence ($(if ($pushSmoke) { $pushSmoke.SummaryPath } else { "No passing mobile-push-smoke summary found." })) `
        -Notes ($(if ($pushSmoke) { "firebaseConfigured=$($pushSmoke.Summary.firebaseConfigured); delivery=$($pushSmoke.Summary.deliveryResult.reason)" } else { "" }))
    New-Requirement `
        -Id "R8" `
        -Requirement "Smoke cleanup left no Test NNH listener and no attached Android emulator/device." `
        -Status ($(if ($port8000.Count -eq 0 -and $adbDevices -eq "List of devices attached") { "passed" } else { "failed" })) `
        -Evidence "Current OS checks: Get-NetTCPConnection :8000 and adb devices" `
        -Notes "port8000=$($port8000.Count); adb='$adbDevices'"
    New-Requirement `
        -Id "R9" `
        -Requirement "Full Django test suite and Android debug unit tests pass for the current mobile/API worktree." `
        -Status ($(if ($mobileTestSuite) { "passed" } else { "missing" })) `
        -Evidence ($(if ($mobileTestSuite) { $mobileTestSuite.SummaryPath } else { "No passing mobile-test-suite summary found." })) `
        -Notes ($(if ($mobileTestSuite) { "Django exit=$($mobileTestSuite.Summary.django.exitCode); Android exit=$($mobileTestSuite.Summary.android.exitCode)." } else { "Run android/scripts/mobile-test-suite.ps1." }))
    New-Requirement `
        -Id "G1" `
        -Requirement "Successful biometric unlock on an enrolled Android device/AVD." `
        -Status ($(if ($biometricSmoke) { "passed" } else { "external-gate" })) `
        -Evidence ($(if ($biometricSmoke) { $biometricSmoke.SummaryPath } else { "No enrolled biometric device/AVD evidence in current local artifacts." })) `
        -Notes ($(if ($biometricSmoke) { "Enrolled emulator biometric unlock restored the MEDTRACK session." } else { "Current emulator evidence proves availability gating only." }))
    New-Requirement `
        -Id "G2" `
        -Requirement "Real Firebase push delivery with Firebase credentials and a real FCM registration token." `
        -Status ($(if ($realPushDeliveryProved) { "passed" } else { "external-gate" })) `
        -Evidence ($(if ($realPushSmoke) { $realPushSmoke.SummaryPath } elseif ($realPushDeliveryProved -and $pushSmoke) { $pushSmoke.SummaryPath } elseif ($pushPreflight) { $pushPreflight.SummaryPath } elseif ($pushSmoke) { $pushSmoke.SummaryPath } else { "No Firebase delivery evidence." })) `
        -Notes ($(if ($realPushSmoke) { "Registered Android device token received Firebase delivery and device notification evidence was found." } elseif ($realPushDeliveryProved) { "Real Firebase delivery returned sent=true." } elseif ($pushPreflight) { "Preflight missing: $(@($pushPreflight.Summary.missing) -join ', ')" } else { "Run mobile-real-push-smoke.ps1 with Firebase config and a USB Android device." }))
    New-Requirement `
        -Id "G3" `
        -Requirement "Low-end Android device offline-write smoke and 2-user field test." `
        -Status ($(if ($physicalDeviceSmoke -and $fieldTest) { "passed" } else { "external-gate" })) `
        -Evidence ($(if ($physicalDeviceSmoke -and $fieldTest) { "$($physicalDeviceSmoke.SummaryPath); $($fieldTest.SummaryPath)" } elseif ($physicalDeviceSmoke) { $physicalDeviceSmoke.SummaryPath } elseif ($fieldTest) { $fieldTest.SummaryPath } elseif ($physicalDevicePreflight) { $physicalDevicePreflight.SummaryPath } else { "No physical low-end device / field-test artifact in this workspace." })) `
        -Notes ($(if ($physicalDeviceSmoke -and $fieldTest) { "Physical offline-write smoke and 2-user field test both passed." } elseif ($physicalDeviceSmoke) { "Physical offline-write smoke exists; 2-user field test still requires target users." } elseif ($fieldTest) { "2-user field test exists; physical offline-write smoke still missing." } elseif ($physicalDevicePreflight) { "Latest preflight confirms no physical Android device is attached." } else { "Requires access to target device/users." }))
)

$failedOrMissingLocal = @($requirements | Where-Object { $_.status -in @("failed", "missing") })
$externalGates = @($requirements | Where-Object { $_.status -eq "external-gate" })
$localStatus = if ($failedOrMissingLocal.Count -eq 0) { "local-verification-passed" } else { "local-verification-incomplete" }
$goalComplete = $failedOrMissingLocal.Count -eq 0 -and $externalGates.Count -eq 0

$summary = [ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    localStatus = $localStatus
    goalComplete = $goalComplete
    currentApk = [ordered]@{
        path = $apkPath
        sha256 = $apkHash
    }
    evidence = [ordered]@{
        apiSmoke = if ($apiSmoke) { $apiSmoke.SummaryPath } else { $null }
        emulatorSmoke = if ($emulatorSmoke) { $emulatorSmoke.SummaryPath } else { $null }
        biometricSmoke = if ($biometricSmoke) { $biometricSmoke.SummaryPath } else { $null }
        physicalDeviceSmoke = if ($physicalDeviceSmoke) { $physicalDeviceSmoke.SummaryPath } else { $null }
        physicalDevicePreflight = if ($physicalDevicePreflight) { $physicalDevicePreflight.SummaryPath } else { $null }
        pushSmoke = if ($pushSmoke) { $pushSmoke.SummaryPath } else { $null }
        pushPreflight = if ($pushPreflight) { $pushPreflight.SummaryPath } else { $null }
        realPushSmoke = if ($realPushSmoke) { $realPushSmoke.SummaryPath } else { $null }
        fieldTest = if ($fieldTest) { $fieldTest.SummaryPath } else { $null }
        mobileTestSuite = if ($mobileTestSuite) { $mobileTestSuite.SummaryPath } else { $null }
    }
    moduleChecks = $moduleChecks
    apiFileChecks = $apiFileChecks
    requirements = $requirements
    cleanup = [ordered]@{
        adbDevices = $adbDevices
        port8000 = $port8000
    }
    evidenceDir = $EvidenceDir
}

$summaryPath = Join-Path $EvidenceDir "summary.json"
Save-Json -Path $summaryPath -Value $summary -Depth 12

$reportPath = Join-Path $EvidenceDir "report.md"
$lines = @(
    "# MEDTRACK Android v1 Verification Audit"
    ""
    "- Generated: $($summary.generatedAt)"
    "- Local status: ``$localStatus``"
    "- Goal complete: ``$goalComplete``"
    "- Current APK SHA256: ``$apkHash``"
    ""
    "## Evidence"
    ""
    "- API smoke: $(Format-EvidenceValue $summary.evidence.apiSmoke)"
    "- Emulator/offline smoke: $(Format-EvidenceValue $summary.evidence.emulatorSmoke)"
    "- Biometric smoke: $(Format-EvidenceValue $summary.evidence.biometricSmoke)"
    "- Physical-device smoke: $(Format-EvidenceValue $summary.evidence.physicalDeviceSmoke)"
    "- Physical-device preflight: $(Format-EvidenceValue $summary.evidence.physicalDevicePreflight)"
    "- Push smoke: $(Format-EvidenceValue $summary.evidence.pushSmoke)"
    "- Push preflight: $(Format-EvidenceValue $summary.evidence.pushPreflight)"
    "- Real push smoke: $(Format-EvidenceValue $summary.evidence.realPushSmoke)"
    "- Field test: $(Format-EvidenceValue $summary.evidence.fieldTest)"
    "- Mobile test suite: $(Format-EvidenceValue $summary.evidence.mobileTestSuite)"
    ""
    "## Requirements"
    ""
    "| ID | Status | Requirement | Evidence | Notes |"
    "|---|---|---|---|---|"
)
$lines += $requirements | ForEach-Object { Format-RequirementRow -Requirement $_ }
$lines += @(
    ""
    "## Interpretation"
    ""
    "This audit can prove local implementation and Test NNH verification only. It intentionally keeps the goal incomplete while real Firebase delivery and low-end/field testing remain unverified."
)
$lines | Set-Content -Path $reportPath

Write-Host "[audit] $localStatus"
Write-Host "[audit] summary: $summaryPath"
Write-Host "[audit] report: $reportPath"
if ($failedOrMissingLocal.Count -gt 0) {
    Write-Host "[audit] local gaps:"
    $failedOrMissingLocal | ForEach-Object { Write-Host " - $($_.id): $($_.status) $($_.requirement)" }
    exit 1
}
