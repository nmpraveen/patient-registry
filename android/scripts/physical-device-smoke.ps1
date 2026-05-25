[CmdletBinding()]
param(
    [string]$Username = "admin",
    [string]$Password = "pass",
    [string]$EvidenceDir = "",
    [switch]$NoBuild,
    [switch]$OfflineWrites,
    [switch]$KeepServer
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDir = Join-Path $repoRoot "output\android-physical-device-smoke-$timestamp"
}

$devices = @(
    adb devices |
        Select-String -Pattern "^\S+\s+device$" |
        ForEach-Object { ($_ -split "\s+")[0] } |
        Where-Object { $_ -notlike "emulator-*" }
)

if ($devices.Count -eq 0) {
    New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
    [ordered]@{
        passed = $false
        reason = "no_physical_device"
        message = "Connect a physical Android phone with USB debugging enabled, then rerun this script."
        evidenceDir = $EvidenceDir
    } | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $EvidenceDir "summary.json")
    throw "No physical Android device is attached. Connect a phone with USB debugging enabled, then rerun this script."
}

& (Join-Path $scriptRoot "local-emulator-smoke.ps1") `
    -Username $Username `
    -Password $Password `
    -EvidenceDir $EvidenceDir `
    -ApiBaseUrl "http://127.0.0.1:8000/" `
    -RequirePhysicalDevice `
    -UseAdbReverse `
    -NoBuild:$NoBuild `
    -OfflineWrites:$OfflineWrites `
    -KeepServer:$KeepServer
