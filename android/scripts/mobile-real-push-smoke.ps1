[CmdletBinding()]
param(
    [string]$Username = "admin",
    [string]$Password = "pass",
    [string]$EvidenceDir = "",
    [switch]$NoBuild,
    [switch]$KeepServer,
    [int]$TokenTimeoutSeconds = 120,
    [int]$NotificationTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$androidRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $androidRoot
$packageName = "com.naveenhospital.medtrack"

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDir = Join-Path $repoRoot "output\mobile-real-push-smoke-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$runId = Get-Date -Format "yyyyMMddHHmmss"
$startedAt = (Get-Date).ToUniversalTime()
$serverWasRunning = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue).Count -gt 0

function Write-Step {
    param([string]$Message)
    Write-Host "[real-push-smoke] $Message"
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

function Get-PhysicalDeviceSerials {
    @(
        adb devices |
            Select-String -Pattern "^\S+\s+device$" |
            ForEach-Object { ($_ -split "\s+")[0] } |
            Where-Object { $_ -notlike "emulator-*" }
    )
}

function Write-NotReadySummary {
    param(
        [string]$Reason,
        [string[]]$Missing = @()
    )
    $summary = [ordered]@{
        passed = $false
        reason = $Reason
        missing = $Missing
        runId = $runId
        evidenceDir = $EvidenceDir
    }
    Save-Json -Path (Join-Path $EvidenceDir "summary.json") -Value $summary -Depth 8
}

function Wait-ForNotificationEvidence {
    param(
        [string]$DeviceSerial,
        [string]$Needle,
        [int]$TimeoutSeconds
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $dump = adb -s $DeviceSerial shell dumpsys notification --noredact 2>$null | Out-String
        $matches = @(
            $dump -split "`r?`n" |
                Where-Object { $_ -like "*$Needle*" -or $_ -like "*Mobile push smoke*" }
        )
        if ($matches.Count -gt 0) {
            $matches | Set-Content -Path (Join-Path $EvidenceDir "device-notification-evidence.txt")
            return $true
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    "" | Set-Content -Path (Join-Path $EvidenceDir "device-notification-evidence.txt")
    return $false
}

try {
    Write-Step "Evidence: $EvidenceDir"

    $devices = Get-PhysicalDeviceSerials
    if ($devices.Count -eq 0) {
        Write-NotReadySummary -Reason "no_physical_device" -Missing @("physical Android phone with USB debugging")
        throw "No physical Android device is attached. Connect a phone with USB debugging enabled, then rerun this script."
    }
    $deviceSerial = $devices[0]

    $missing = @()
    if (-not (Test-Path (Join-Path $androidRoot "app\google-services.json"))) {
        $missing += "android/app/google-services.json"
    }
    if ("$env:FCM_ENABLED".Trim().ToLowerInvariant() -notin @("1", "true", "yes", "on")) {
        $missing += "FCM_ENABLED=true"
    }
    if ([string]::IsNullOrWhiteSpace("$env:FCM_CREDENTIALS_FILE")) {
        $missing += "FCM_CREDENTIALS_FILE"
    }
    elseif (-not (Test-Path -LiteralPath "$env:FCM_CREDENTIALS_FILE")) {
        $missing += "FCM_CREDENTIALS_FILE host path exists"
    }
    if ($missing.Count -gt 0) {
        Write-NotReadySummary -Reason "missing_firebase_prerequisites" -Missing $missing
        throw "Firebase delivery is not ready: missing $($missing -join ', ')"
    }

    $physicalEvidenceDir = Join-Path $EvidenceDir "physical-device-smoke"
    Write-Step "Running physical-device smoke before push delivery"
    $physicalArgs = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (Join-Path $scriptRoot "physical-device-smoke.ps1"),
        "-Username",
        $Username,
        "-Password",
        $Password,
        "-EvidenceDir",
        $physicalEvidenceDir,
        "-OfflineWrites",
        "-KeepServer"
    )
    if ($NoBuild) {
        $physicalArgs += "-NoBuild"
    }
    Invoke-ProcessLogged `
        -Name "physical-device-smoke" `
        -FilePath "powershell.exe" `
        -Arguments $physicalArgs

    $physicalSummaryPath = Join-Path $physicalEvidenceDir "summary.json"
    if (-not (Test-Path $physicalSummaryPath)) {
        throw "Physical-device smoke did not write summary.json."
    }
    $physicalSummary = Get-Content -Raw -Path $physicalSummaryPath | ConvertFrom-Json
    if ($physicalSummary.passed -ne $true) {
        throw "Physical-device smoke did not pass. See $physicalSummaryPath"
    }

    Invoke-ProcessLogged `
        -Name "adb-grant-notifications" `
        -FilePath "adb" `
        -Arguments @("-s", $deviceSerial, "shell", "pm", "grant", $packageName, "android.permission.POST_NOTIFICATIONS") `
        -AllowFailure

    $title = "Mobile push smoke $runId"
    $body = "MEDTRACK Firebase delivery $runId"
    $python = @"
import hashlib
import json
import os
import time

from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime

from api.models import MobileDeviceToken, MobileNotification, MobileNotificationType
from api.push import firebase_configured, send_mobile_notification
from patients.models import Case, CaseStatus

username = os.environ["MEDTRACK_REAL_PUSH_USERNAME"]
run_id = os.environ["MEDTRACK_REAL_PUSH_RUN_ID"]
title = os.environ["MEDTRACK_REAL_PUSH_TITLE"]
body = os.environ["MEDTRACK_REAL_PUSH_BODY"]
started_at = parse_datetime(os.environ["MEDTRACK_REAL_PUSH_STARTED_AT"])
token_timeout = int(os.environ["MEDTRACK_REAL_PUSH_TOKEN_TIMEOUT"])
user = get_user_model().objects.get(username=username)

deadline = time.time() + token_timeout
device = None
while time.time() < deadline:
    candidates = (
        MobileDeviceToken.objects
        .filter(user=user, is_active=True)
        .exclude(token__startswith="mobile-push-smoke-")
        .order_by("-updated_at", "-id")
    )
    fresh = candidates.filter(updated_at__gte=started_at).first()
    device = fresh or candidates.first()
    if device:
        break
    time.sleep(3)

if device is None:
    print("MEDTRACK_REAL_PUSH_JSON=" + json.dumps({"ok": False, "reason": "no_registered_device_token"}))
    raise SystemExit(2)

case = Case.objects.filter(status=CaseStatus.ACTIVE).order_by("id").first() or Case.objects.order_by("id").first()
if case is None:
    raise RuntimeError("No case exists for mobile real push smoke.")

notification = MobileNotification.objects.create(
    user=user,
    notification_type=MobileNotificationType.ASSIGNMENT,
    title=title,
    body=body,
    case=case,
    dedupe_key=f"mobile-real-push-smoke-{run_id}",
    payload={
        "type": MobileNotificationType.ASSIGNMENT,
        "channel": "assignments",
        "case_id": case.pk,
        "run_id": run_id,
    },
)
configured = firebase_configured()
result = send_mobile_notification(notification)
print(
    "MEDTRACK_REAL_PUSH_JSON="
    + json.dumps(
        {
            "ok": True,
            "firebase_configured": configured,
            "notification_id": notification.pk,
            "case_id": case.pk,
            "device": {
                "id": device.pk,
                "device_label": device.device_label,
                "platform": device.platform,
                "app_version": device.app_version,
                "updated_at": device.updated_at.isoformat(),
                "token_sha256_12": hashlib.sha256(device.token.encode("utf-8")).hexdigest()[:12],
            },
            "delivery_result": result,
        },
        sort_keys=True,
    )
)
"@

    $env:MEDTRACK_REAL_PUSH_USERNAME = $Username
    $env:MEDTRACK_REAL_PUSH_RUN_ID = $runId
    $env:MEDTRACK_REAL_PUSH_TITLE = $title
    $env:MEDTRACK_REAL_PUSH_BODY = $body
    $env:MEDTRACK_REAL_PUSH_STARTED_AT = $startedAt.ToString("o")
    $env:MEDTRACK_REAL_PUSH_TOKEN_TIMEOUT = [string]$TokenTimeoutSeconds

    Write-Step "Sending Firebase push to the app-registered FCM token"
    Invoke-ProcessLogged `
        -Name "django-real-push-smoke" `
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
            "-e",
            "MEDTRACK_REAL_PUSH_USERNAME",
            "-e",
            "MEDTRACK_REAL_PUSH_RUN_ID",
            "-e",
            "MEDTRACK_REAL_PUSH_TITLE",
            "-e",
            "MEDTRACK_REAL_PUSH_BODY",
            "-e",
            "MEDTRACK_REAL_PUSH_STARTED_AT",
            "-e",
            "MEDTRACK_REAL_PUSH_TOKEN_TIMEOUT",
            "web",
            "python",
            "manage.py",
            "shell",
            "-c",
            $python
        )

    $stdout = Get-Content -Raw -Path (Join-Path $EvidenceDir "django-real-push-smoke.stdout.log")
    $line = ($stdout -split "`r?`n" | Where-Object { $_ -like "MEDTRACK_REAL_PUSH_JSON=*" } | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($line)) {
        throw "Real push smoke did not emit a JSON result."
    }
    $result = $line.Substring("MEDTRACK_REAL_PUSH_JSON=".Length) | ConvertFrom-Json
    Save-Json -Path (Join-Path $EvidenceDir "real-push-result.json") -Value $result -Depth 10
    if ($result.ok -ne $true) {
        throw "Real push smoke failed before delivery: $($result.reason)"
    }
    if ($result.firebase_configured -ne $true) {
        throw "Django did not report firebase_configured() == true."
    }
    if ($result.delivery_result.sent -ne $true) {
        throw "Firebase delivery did not report sent=true."
    }

    Write-Step "Checking device notification evidence"
    $hasDeviceNotificationEvidence = Wait-ForNotificationEvidence `
        -DeviceSerial $deviceSerial `
        -Needle $runId `
        -TimeoutSeconds $NotificationTimeoutSeconds

    $checks = [ordered]@{
        hasPhysicalDeviceSmoke = $physicalSummary.passed -eq $true
        hasRegisteredDeviceToken = $null -ne $result.device.id
        hasFirebaseConfigured = $result.firebase_configured -eq $true
        hasDeliverySent = $result.delivery_result.sent -eq $true
        hasDeviceNotificationEvidence = $hasDeviceNotificationEvidence
    }
    $summary = [ordered]@{
        passed = ($checks.hasPhysicalDeviceSmoke -and $checks.hasRegisteredDeviceToken -and $checks.hasFirebaseConfigured -and $checks.hasDeliverySent -and $checks.hasDeviceNotificationEvidence)
        runId = $runId
        username = $Username
        deviceSerial = $deviceSerial
        physicalSmokeSummary = $physicalSummaryPath
        usingRegisteredDeviceToken = $true
        firebaseConfigured = [bool]$result.firebase_configured
        notificationId = $result.notification_id
        caseId = $result.case_id
        registeredDevice = $result.device
        deliveryResult = $result.delivery_result
        checks = $checks
        evidenceDir = $EvidenceDir
    }
    Save-Json -Path (Join-Path $EvidenceDir "summary.json") -Value $summary -Depth 10

    if (-not $summary.passed) {
        throw "Real push smoke did not find device notification evidence."
    }
    Write-Step "PASS"
}
finally {
    Remove-Item Env:\MEDTRACK_REAL_PUSH_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:\MEDTRACK_REAL_PUSH_RUN_ID -ErrorAction SilentlyContinue
    Remove-Item Env:\MEDTRACK_REAL_PUSH_TITLE -ErrorAction SilentlyContinue
    Remove-Item Env:\MEDTRACK_REAL_PUSH_BODY -ErrorAction SilentlyContinue
    Remove-Item Env:\MEDTRACK_REAL_PUSH_STARTED_AT -ErrorAction SilentlyContinue
    Remove-Item Env:\MEDTRACK_REAL_PUSH_TOKEN_TIMEOUT -ErrorAction SilentlyContinue

    $cleanup = [ordered]@{}
    if (-not $serverWasRunning -and -not $KeepServer) {
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
    Start-Sleep -Seconds 2
    $cleanup["adbDevices"] = try { (adb devices | Out-String).Trim() } catch { $_.Exception.Message }
    $cleanup["port8000"] = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)
    Save-Json -Path (Join-Path $EvidenceDir "cleanup-status.json") -Value $cleanup -Depth 6
}
