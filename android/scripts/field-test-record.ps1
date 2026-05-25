[CmdletBinding()]
param(
    [string]$EvidenceDir = "",
    [string]$PhysicalSmokeSummary = "",
    [string]$DeviceModel = "",
    [string]$AndroidVersion = "",
    [string]$Tester1Role = "",
    [string]$Tester2Role = "",
    [switch]$HomeInboxPassed,
    [switch]$CallDonePassed,
    [switch]$VitalsPassed,
    [switch]$OfflineSyncPassed,
    [switch]$LockUnlockPassed,
    [switch]$ReadabilityPassed,
    [switch]$NoCrashOrAnr,
    [string]$Issues = "",
    [switch]$CreateTemplate
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$androidRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $androidRoot
$outputRoot = Join-Path $repoRoot "output"

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    $EvidenceDir = Join-Path $outputRoot "android-field-test-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function Save-Json {
    param(
        [string]$Path,
        [object]$Value,
        [int]$Depth = 10
    )
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -Path $Path
}

function Format-MarkdownPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return "Not found"
    }
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

function Get-LatestPassingPhysicalSmoke {
    if (-not (Test-Path $outputRoot)) {
        return $null
    }
    foreach ($dir in @(Get-ChildItem -Path $outputRoot -Directory -Filter "android-physical-device-smoke-*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)) {
        $summaryPath = Join-Path $dir.FullName "summary.json"
        if (-not (Test-Path $summaryPath)) {
            continue
        }
        $summary = Get-Content -Raw -Path $summaryPath | ConvertFrom-Json
        if ($summary.passed -eq $true -and $summary.requirePhysicalDevice -eq $true) {
            return $summaryPath
        }
    }
    return $null
}

if ([string]::IsNullOrWhiteSpace($PhysicalSmokeSummary)) {
    $PhysicalSmokeSummary = Get-LatestPassingPhysicalSmoke
}

$physicalSmokeValid = $false
$physicalSmokeOfflineWritesValid = $false
$physicalSmokeApkSha256 = ""
$physicalSmokeEvidenceDir = ""
if (-not [string]::IsNullOrWhiteSpace($PhysicalSmokeSummary) -and (Test-Path -LiteralPath $PhysicalSmokeSummary)) {
    $physicalSummary = Get-Content -Raw -Path $PhysicalSmokeSummary | ConvertFrom-Json
    $physicalSmokeValid = $physicalSummary.passed -eq $true -and $physicalSummary.requirePhysicalDevice -eq $true
    $physicalSmokeOfflineWritesValid = $physicalSmokeValid -and
        $physicalSummary.offlineWrites -ne $null -and
        $physicalSummary.checks.hasOfflineTaskQueued -eq $true -and
        $physicalSummary.checks.hasOfflineCallQueued -eq $true -and
        $physicalSummary.checks.hasOfflineVitalsQueued -eq $true -and
        $physicalSummary.checks.hasOfflineWritesSynced -eq $true
    $physicalSmokeApkSha256 = [string]$physicalSummary.apkSha256
    $physicalSmokeEvidenceDir = [string]$physicalSummary.evidenceDir
}

$checks = [ordered]@{
    homeInboxPassed = [bool]$HomeInboxPassed
    callDonePassed = [bool]$CallDonePassed
    vitalsPassed = [bool]$VitalsPassed
    offlineSyncPassed = [bool]$OfflineSyncPassed
    lockUnlockPassed = [bool]$LockUnlockPassed
    readabilityPassed = [bool]$ReadabilityPassed
    noCrashOrAnr = [bool]$NoCrashOrAnr
}

$missing = @()
if ([string]::IsNullOrWhiteSpace($DeviceModel)) { $missing += "DeviceModel" }
if ([string]::IsNullOrWhiteSpace($AndroidVersion)) { $missing += "AndroidVersion" }
if ([string]::IsNullOrWhiteSpace($Tester1Role)) { $missing += "Tester1Role" }
if ([string]::IsNullOrWhiteSpace($Tester2Role)) { $missing += "Tester2Role" }
if (-not $physicalSmokeValid) {
    $missing += "passing physical smoke summary"
}
elseif (-not $physicalSmokeOfflineWritesValid) {
    $missing += "passing physical offline-write smoke summary"
}
$failedChecks = @($checks.GetEnumerator() | Where-Object { $_.Value -ne $true } | ForEach-Object { $_.Key })

$passed = -not $CreateTemplate -and $missing.Count -eq 0 -and $failedChecks.Count -eq 0

$summary = [ordered]@{
    passed = $passed
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    templateOnly = [bool]$CreateTemplate
    device = [ordered]@{
        model = $DeviceModel
        androidVersion = $AndroidVersion
    }
    testers = @(
        [ordered]@{ index = 1; role = $Tester1Role },
        [ordered]@{ index = 2; role = $Tester2Role }
    )
    userCount = @($Tester1Role, $Tester2Role | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count
    checks = $checks
    issues = $Issues
    physicalSmokeSummary = $PhysicalSmokeSummary
    physicalSmokeValid = $physicalSmokeValid
    physicalSmokeOfflineWritesValid = $physicalSmokeOfflineWritesValid
    physicalSmokeApkSha256 = $physicalSmokeApkSha256
    physicalSmokeEvidenceDir = $physicalSmokeEvidenceDir
    missing = $missing
    failedChecks = $failedChecks
    evidenceDir = $EvidenceDir
}

$summaryPath = Join-Path $EvidenceDir "summary.json"
Save-Json -Path $summaryPath -Value $summary -Depth 10

$reportPath = Join-Path $EvidenceDir "report.md"
$lines = @(
    "# MEDTRACK Android Field Test Record"
    ""
    "- Generated: $($summary.generatedAt)"
    "- Passed: ``$passed``"
    "- Template only: ``$([bool]$CreateTemplate)``"
    "- Device model: ``$DeviceModel``"
    "- Android version: ``$AndroidVersion``"
    "- Physical smoke summary: $(Format-MarkdownPath -Path $PhysicalSmokeSummary)"
    "- Physical smoke evidence: $(Format-MarkdownPath -Path $physicalSmokeEvidenceDir)"
    "- Physical smoke APK SHA256: ``$physicalSmokeApkSha256``"
    "- Physical smoke offline writes valid: ``$physicalSmokeOfflineWritesValid``"
    ""
    "## Testers"
    ""
    "- Tester 1 role: ``$Tester1Role``"
    "- Tester 2 role: ``$Tester2Role``"
    ""
    "## Checks"
    ""
)
$lines += $checks.GetEnumerator() | ForEach-Object { "- $($_.Key): ``$($_.Value)``" }
$lines += @(
    ""
    "## Issues"
    ""
    $(if ([string]::IsNullOrWhiteSpace($Issues)) { "None recorded." } else { $Issues })
    ""
    "## Missing"
    ""
    $(if ($missing.Count -eq 0) { "None." } else { $missing -join ", " })
    ""
    "## Failed Checks"
    ""
    $(if ($failedChecks.Count -eq 0) { "None." } else { $failedChecks -join ", " })
)
$lines | Set-Content -Path $reportPath

Write-Host "[field-test] summary: $summaryPath"
Write-Host "[field-test] report: $reportPath"

if (-not $passed) {
    if ($CreateTemplate) {
        Write-Host "[field-test] Template written. Rerun without -CreateTemplate after two users complete the checks."
        exit 0
    }
    throw "Field test record is incomplete. Missing: $($missing -join ', '); failed checks: $($failedChecks -join ', ')"
}

Write-Host "[field-test] PASS"
