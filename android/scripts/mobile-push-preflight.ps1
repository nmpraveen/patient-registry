[CmdletBinding()]
param(
    [string]$EvidenceDir = "",
    [string]$FirebaseToken = $env:MEDTRACK_FCM_TEST_TOKEN,
    [switch]$RequireReady,
    [switch]$KeepServer,
    [switch]$KeepDashboard
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$androidRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $androidRoot

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDir = Join-Path $repoRoot "output\mobile-push-preflight-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$startedServer = $false
$startedDashboard = $false

function Write-Step {
    param([string]$Message)
    Write-Host "[push-preflight] $Message"
}

function Save-Json {
    param(
        [string]$Path,
        [object]$Value,
        [int]$Depth = 12
    )
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -Path $Path
}

function Join-ProcessArguments {
    param([string[]]$Arguments)
    (($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + ($_ -replace '"', '\"') + '"'
        }
        else {
            $_
        }
    }) -join " ")
}

function Invoke-ProcessLogged {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $repoRoot,
        [switch]$AllowFailure
    )

    $logPath = Join-Path $EvidenceDir "$Name.log"
    $stdoutPath = Join-Path $EvidenceDir "$Name.stdout.log"
    $stderrPath = Join-Path $EvidenceDir "$Name.stderr.log"
    $argumentString = Join-ProcessArguments -Arguments $Arguments
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $argumentString `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -NoNewWindow `
        -Wait `
        -PassThru

    $stdout = if (Test-Path $stdoutPath) { Get-Content -Raw -Path $stdoutPath } else { "" }
    $stderr = if (Test-Path $stderrPath) { Get-Content -Raw -Path $stderrPath } else { "" }
    @(
        "command: $FilePath $argumentString",
        "workingDirectory: $WorkingDirectory",
        "exitCode: $($process.ExitCode)",
        "",
        "[stdout]",
        $stdout,
        "",
        "[stderr]",
        $stderr
    ) | Set-Content -Path $logPath

    if ($process.ExitCode -ne 0 -and -not $AllowFailure) {
        throw "$Name failed with exit code $($process.ExitCode). See $logPath"
    }
    $script:LastProcessExitCode = $process.ExitCode
}

function Get-ListeningPortPids {
    param([int]$Port)
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url"
}

$androidConfigPath = Join-Path $androidRoot "app\google-services.json"
$credentialsPath = [string]($env:FCM_CREDENTIALS_FILE)
$credentialsExistsOnHost = $false
if (-not [string]::IsNullOrWhiteSpace($credentialsPath)) {
    try {
        $credentialsExistsOnHost = Test-Path (Resolve-Path -LiteralPath $credentialsPath -ErrorAction Stop)
    }
    catch {
        $credentialsExistsOnHost = $false
    }
}

$djangoStatus = [ordered]@{
    checked = $false
    firebaseConfigured = $false
    fcmEnabled = $false
    credentialsFileConfigured = $false
    credentialsFileVisibleToDjango = $false
    projectIdConfigured = $false
    error = $null
}

try {
    Write-Step "Evidence: $EvidenceDir"

    if ((Get-ListeningPortPids -Port 8000).Count -eq 0) {
        Write-Step "Starting Test NNH server"
        $startedServer = $true
        Invoke-ProcessLogged `
            -Name "test-nnh-up" `
            -FilePath "powershell.exe" `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "local-dev\test-nnh-up.ps1"))
    }
    else {
        Write-Step "Reusing existing listener on port 8000"
    }
    Wait-HttpOk -Url "http://localhost:8000/api/schema/" -TimeoutSeconds 90

    if ((Get-ListeningPortPids -Port 3899).Count -eq 0) {
        $dashboardCmd = "C:\Users\prave\Desktop\dashboard.cmd"
        if (Test-Path $dashboardCmd) {
            Write-Step "Starting Local Server Dashboard"
            $startedDashboard = $true
            Start-Process -FilePath $dashboardCmd -WindowStyle Hidden
        }
    }
    $dashboardSnapshotPath = Join-Path $EvidenceDir "dashboard-snapshot.json"
    $deadline = (Get-Date).AddSeconds(45)
    do {
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:3899/api/snapshot" -TimeoutSec 10 |
                ConvertTo-Json -Depth 8 |
                Set-Content -Path $dashboardSnapshotPath
            break
        }
        catch {
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $deadline)

    $python = @"
import json
from django.conf import settings
from api.push import firebase_configured, _credentials_file

credentials_file = _credentials_file()
print(
    "MEDTRACK_PUSH_PREFLIGHT_JSON="
    + json.dumps(
        {
            "firebase_configured": firebase_configured(),
            "fcm_enabled": bool(getattr(settings, "FCM_ENABLED", False)),
            "credentials_file_configured": bool(str(getattr(settings, "FCM_CREDENTIALS_FILE", "")).strip()),
            "credentials_file_visible_to_django": bool(credentials_file),
            "project_id_configured": bool(str(getattr(settings, "FCM_PROJECT_ID", "")).strip()),
        },
        sort_keys=True,
    )
)
"@

    try {
        Invoke-ProcessLogged `
            -Name "django-firebase-preflight" `
            -FilePath "docker" `
            -Arguments @(
                "compose",
                "exec",
                "-T",
                "-e",
                "FCM_ENABLED",
                "-e",
                "FCM_CREDENTIALS_FILE",
                "-e",
                "FCM_PROJECT_ID",
                "web",
                "python",
                "manage.py",
                "shell",
                "-c",
                $python
            )
        $stdout = Get-Content -Raw -Path (Join-Path $EvidenceDir "django-firebase-preflight.stdout.log")
        $line = ($stdout -split "`r?`n" | Where-Object { $_ -like "MEDTRACK_PUSH_PREFLIGHT_JSON=*" } | Select-Object -Last 1)
        if ($line) {
            $payload = $line.Substring("MEDTRACK_PUSH_PREFLIGHT_JSON=".Length) | ConvertFrom-Json
            $djangoStatus.checked = $true
            $djangoStatus.firebaseConfigured = [bool]$payload.firebase_configured
            $djangoStatus.fcmEnabled = [bool]$payload.fcm_enabled
            $djangoStatus.credentialsFileConfigured = [bool]$payload.credentials_file_configured
            $djangoStatus.credentialsFileVisibleToDjango = [bool]$payload.credentials_file_visible_to_django
            $djangoStatus.projectIdConfigured = [bool]$payload.project_id_configured
        }
        else {
            $djangoStatus.error = "Django preflight did not emit JSON."
        }
    }
    catch {
        $djangoStatus.error = $_.Exception.Message
    }

    $checks = [ordered]@{
        hasAndroidGoogleServicesJson = Test-Path $androidConfigPath
        hasFcmTestToken = -not [string]::IsNullOrWhiteSpace($FirebaseToken)
        hasHostFcmEnabled = "$env:FCM_ENABLED".Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")
        hasHostCredentialsFile = -not [string]::IsNullOrWhiteSpace($credentialsPath)
        hostCredentialsFileExists = $credentialsExistsOnHost
        djangoPreflightChecked = [bool]$djangoStatus.checked
        djangoFirebaseConfigured = [bool]$djangoStatus.firebaseConfigured
    }

    $missing = @()
    if (-not $checks.hasAndroidGoogleServicesJson) { $missing += "android/app/google-services.json" }
    if (-not $checks.hasFcmTestToken) { $missing += "MEDTRACK_FCM_TEST_TOKEN" }
    if (-not $checks.hasHostFcmEnabled) { $missing += "FCM_ENABLED=true" }
    if (-not $checks.hasHostCredentialsFile) { $missing += "FCM_CREDENTIALS_FILE" }
    elseif (-not $checks.hostCredentialsFileExists) { $missing += "FCM_CREDENTIALS_FILE host path exists" }
    if (-not $checks.djangoFirebaseConfigured) { $missing += "Django firebase_configured() true" }

    $ready = $missing.Count -eq 0
    $summary = [ordered]@{
        passed = $ready
        reason = if ($ready) { "firebase_ready" } else { "missing_firebase_prerequisites" }
        checks = $checks
        missing = $missing
        django = $djangoStatus
        androidGoogleServicesJson = [ordered]@{
            path = $androidConfigPath
            exists = [bool]$checks.hasAndroidGoogleServicesJson
        }
        environment = [ordered]@{
            hasMedtrackFcmTestToken = [bool]$checks.hasFcmTestToken
            fcmEnabled = "$env:FCM_ENABLED"
            hasFcmCredentialsFile = [bool]$checks.hasHostCredentialsFile
            fcmCredentialsFileExistsOnHost = [bool]$checks.hostCredentialsFileExists
            hasFcmProjectId = -not [string]::IsNullOrWhiteSpace("$env:FCM_PROJECT_ID")
        }
        evidenceDir = $EvidenceDir
    }
    Save-Json -Path (Join-Path $EvidenceDir "summary.json") -Value $summary -Depth 12
    if ($RequireReady -and -not $ready) {
        throw "Firebase delivery is not ready: missing $($missing -join ', ')"
    }
    if ($ready) {
        Write-Step "READY"
    }
    else {
        Write-Step "NOT READY: missing $($missing -join ', ')"
    }
}
finally {
    $cleanup = [ordered]@{}
    if ($startedServer -and -not $KeepServer) {
        Write-Step "Stopping Test NNH server"
        try {
            Invoke-ProcessLogged `
                -Name "test-nnh-stop" `
                -FilePath "powershell.exe" `
                -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "local-dev\test-nnh-stop.ps1")) `
                -AllowFailure | Out-Null
        }
        catch {
            $cleanup["serverStopError"] = $_.Exception.Message
        }
    }
    if ($startedDashboard -and -not $KeepDashboard) {
        $dashboardPids = Get-ListeningPortPids -Port 3899
        foreach ($dashboardPid in $dashboardPids) {
            Stop-Process -Id $dashboardPid -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
    $cleanup["adbDevices"] = try { (adb devices | Out-String).Trim() } catch { $_.Exception.Message }
    $cleanup["port8000"] = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)
    $cleanup["port3899"] = @(Get-NetTCPConnection -State Listen -LocalPort 3899 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)
    Save-Json -Path (Join-Path $EvidenceDir "cleanup-status.json") -Value $cleanup -Depth 6
}
