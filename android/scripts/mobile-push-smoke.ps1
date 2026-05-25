[CmdletBinding()]
param(
    [string]$Username = "admin",
    [string]$FirebaseToken = $env:MEDTRACK_FCM_TEST_TOKEN,
    [string]$EvidenceDir = "",
    [switch]$RequireFirebase,
    [switch]$KeepServer,
    [switch]$KeepDashboard
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$androidRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $androidRoot

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDir = Join-Path $repoRoot "output\mobile-push-smoke-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$startedServer = $false
$startedDashboard = $false
$runId = Get-Date -Format "yyyyMMddHHmmss"
$previousFcmToken = $env:MEDTRACK_FCM_TEST_TOKEN

function Write-Step {
    param([string]$Message)
    Write-Host "[push-smoke] $Message"
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

    $stdout = ""
    $stderr = ""
    if (Test-Path $stdoutPath) {
        $stdout = Get-Content -Raw -Path $stdoutPath
    }
    if (Test-Path $stderrPath) {
        $stderr = Get-Content -Raw -Path $stderrPath
    }

    @(
        "command: $FilePath $argumentString"
        "workingDirectory: $WorkingDirectory"
        "exitCode: $($process.ExitCode)"
        ""
        "[stdout]"
        $stdout
        ""
        "[stderr]"
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

function Save-Json {
    param(
        [string]$Path,
        [object]$Value,
        [int]$Depth = 12
    )
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -Path $Path
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
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
            $snapshot = Invoke-RestMethod -Uri "http://127.0.0.1:3899/api/snapshot" -TimeoutSec 10
            Save-Json -Path $dashboardSnapshotPath -Value $snapshot -Depth 8
            $snapshotText = $snapshot | ConvertTo-Json -Depth 8
            Assert-True ($snapshotText -like "*8000*") "Local Server Dashboard snapshot did not include port 8000."
            break
        }
        catch {
            if ((Get-Date) -ge $deadline) {
                throw "Local Server Dashboard did not verify Test NNH discovery: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $deadline)

    $usingRealToken = -not [string]::IsNullOrWhiteSpace($FirebaseToken)
    if ($usingRealToken) {
        $env:MEDTRACK_FCM_TEST_TOKEN = $FirebaseToken
    }
    else {
        $env:MEDTRACK_FCM_TEST_TOKEN = "mobile-push-smoke-$runId"
    }

    $python = @"
import json
import os
from django.contrib.auth import get_user_model
from django.utils import timezone
from api.models import MobileDeviceToken, MobileNotification, MobileNotificationType
from api.push import firebase_configured, send_mobile_notification
from patients.models import Case, CaseStatus

username = os.environ["MEDTRACK_PUSH_SMOKE_USERNAME"]
run_id = os.environ["MEDTRACK_PUSH_SMOKE_RUN_ID"]
token = os.environ["MEDTRACK_FCM_TEST_TOKEN"]
using_real_token = os.environ.get("MEDTRACK_PUSH_SMOKE_REAL_TOKEN") == "1"
user = get_user_model().objects.get(username=username)
case = Case.objects.filter(status=CaseStatus.ACTIVE).order_by("id").first() or Case.objects.order_by("id").first()
if case is None:
    raise RuntimeError("No case exists for mobile push smoke.")
device, _ = MobileDeviceToken.objects.update_or_create(
    token=token,
    defaults={
        "user": user,
        "platform": "android",
        "app_version": "local-push-smoke",
        "device_label": "Codex local push smoke",
        "is_active": True,
        "last_seen_at": timezone.now(),
    },
)
notification, _ = MobileNotification.objects.get_or_create(
    user=user,
    dedupe_key=f"mobile-push-smoke-{run_id}",
    defaults={
        "notification_type": MobileNotificationType.ASSIGNMENT,
        "title": "Mobile push smoke",
        "body": "Local MEDTRACK push smoke",
        "case": case,
        "payload": {
            "type": MobileNotificationType.ASSIGNMENT,
            "channel": "assignments",
            "case_id": case.pk,
        },
    },
)
configured = firebase_configured()
result = send_mobile_notification(notification)
device.refresh_from_db()
print(
    "MEDTRACK_PUSH_SMOKE_JSON="
    + json.dumps(
        {
            "firebase_configured": configured,
            "using_real_token": using_real_token,
            "notification_id": notification.pk,
            "case_id": case.pk,
            "device_active": device.is_active,
            "result": result,
        },
        sort_keys=True,
    )
)
"@

    $env:MEDTRACK_PUSH_SMOKE_USERNAME = $Username
    $env:MEDTRACK_PUSH_SMOKE_RUN_ID = $runId
    $env:MEDTRACK_PUSH_SMOKE_REAL_TOKEN = if ($usingRealToken) { "1" } else { "0" }

    Invoke-ProcessLogged `
        -Name "django-push-smoke" `
        -FilePath "docker" `
        -Arguments @(
            "compose",
            "exec",
            "-T",
            "-e",
            "MEDTRACK_FCM_TEST_TOKEN",
            "-e",
            "MEDTRACK_PUSH_SMOKE_USERNAME",
            "-e",
            "MEDTRACK_PUSH_SMOKE_RUN_ID",
            "-e",
            "MEDTRACK_PUSH_SMOKE_REAL_TOKEN",
            "web",
            "python",
            "manage.py",
            "shell",
            "-c",
            $python
        )

    $stdout = Get-Content -Raw -Path (Join-Path $EvidenceDir "django-push-smoke.stdout.log")
    $line = ($stdout -split "`r?`n" | Where-Object { $_ -like "MEDTRACK_PUSH_SMOKE_JSON=*" } | Select-Object -Last 1)
    Assert-True (-not [string]::IsNullOrWhiteSpace($line)) "Push smoke did not emit a JSON result."
    $result = $line.Substring("MEDTRACK_PUSH_SMOKE_JSON=".Length) | ConvertFrom-Json
    Save-Json -Path (Join-Path $EvidenceDir "push-result.json") -Value $result -Depth 10

    if ($RequireFirebase) {
        Assert-True $result.firebase_configured "RequireFirebase was set, but Firebase is not configured."
        Assert-True $result.using_real_token "RequireFirebase was set, but no real FCM token was supplied."
        Assert-True $result.result.sent "RequireFirebase was set, but Firebase delivery did not report sent=true."
    }
    elseif (-not $result.firebase_configured) {
        Assert-True ($result.result.reason -eq "fcm_not_configured") "Expected fcm_not_configured when Firebase config is missing."
    }

    $checks = [ordered]@{
        hasNotificationRow = [bool]$result.notification_id
        hasDeviceTokenRow = [bool]$result.device_active
        hasFirebaseConfigStatus = $null -ne $result.firebase_configured
        hasExpectedMissingConfigResult = (-not $result.firebase_configured -and $result.result.reason -eq "fcm_not_configured")
        hasRealDeliveryAttempt = ($result.firebase_configured -and $result.using_real_token)
    }
    $summary = [ordered]@{
        passed = $true
        username = $Username
        runId = $runId
        requireFirebase = [bool]$RequireFirebase
        usingRealToken = [bool]$result.using_real_token
        firebaseConfigured = [bool]$result.firebase_configured
        notificationId = $result.notification_id
        caseId = $result.case_id
        deliveryResult = $result.result
        checks = $checks
        evidenceDir = $EvidenceDir
    }
    Save-Json -Path (Join-Path $EvidenceDir "summary.json") -Value $summary -Depth 10
    Write-Step "PASS"
}
finally {
    if ($null -eq $previousFcmToken) {
        Remove-Item Env:\MEDTRACK_FCM_TEST_TOKEN -ErrorAction SilentlyContinue
    }
    else {
        $env:MEDTRACK_FCM_TEST_TOKEN = $previousFcmToken
    }
    Remove-Item Env:\MEDTRACK_PUSH_SMOKE_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:\MEDTRACK_PUSH_SMOKE_RUN_ID -ErrorAction SilentlyContinue
    Remove-Item Env:\MEDTRACK_PUSH_SMOKE_REAL_TOKEN -ErrorAction SilentlyContinue

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
