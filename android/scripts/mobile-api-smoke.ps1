[CmdletBinding()]
param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Username = "admin",
    [string]$Password = "pass",
    [string]$EvidenceDir = "",
    [switch]$KeepServer,
    [switch]$KeepDashboard
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$androidRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $androidRoot

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDir = Join-Path $repoRoot "output\mobile-api-smoke-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$startedServer = $false
$startedDashboard = $false
$runId = Get-Date -Format "yyyyMMddHHmmss"
$responses = [ordered]@{}
$targetCase = $null
$targetTask = $null

function Write-Step {
    param([string]$Message)
    Write-Host "[api-smoke] $Message"
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

function Invoke-MobileApi {
    param(
        [string]$Name,
        [ValidateSet("GET", "POST")]
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [string]$AccessToken = ""
    )

    $uri = $BaseUrl.TrimEnd("/") + $Path
    $headers = @{ Accept = "application/json" }
    if ($AccessToken) {
        $headers["Authorization"] = "Bearer $AccessToken"
    }

    $request = @{
        Method = $Method
        Uri = $uri
        Headers = $headers
        TimeoutSec = 30
        UseBasicParsing = $true
    }
    if ($null -ne $Body) {
        $request["ContentType"] = "application/json"
        $request["Body"] = ($Body | ConvertTo-Json -Depth 16)
    }

    try {
        $response = Invoke-WebRequest @request
    }
    catch {
        $errorPath = Join-Path $EvidenceDir "$Name.error.txt"
        $_ | Out-String | Set-Content -Path $errorPath
        if ($_.Exception.Response) {
            $responses[$Name] = [ordered]@{
                method = $Method
                path = $Path
                status = [int]$_.Exception.Response.StatusCode
                error = $errorPath
            }
        }
        throw
    }

    $payload = $null
    if ($response.Content) {
        $payload = $response.Content | ConvertFrom-Json
        Save-Json -Path (Join-Path $EvidenceDir "$Name.json") -Value $payload
    }
    else {
        "" | Set-Content -Path (Join-Path $EvidenceDir "$Name.json")
    }

    $responses[$Name] = [ordered]@{
        method = $Method
        path = $Path
        status = [int]$response.StatusCode
    }
    return $payload
}

function Save-AuthEvidence {
    param(
        [string]$Name,
        [object]$Payload
    )
    $redacted = [ordered]@{
        redacted = $true
        access_present = [bool]$Payload.access
        refresh_present = [bool]$Payload.refresh
    }
    Save-Json -Path (Join-Path $EvidenceDir "$Name.json") -Value $redacted
}

function Get-MobileCaseResults {
    param([object]$Payload)
    if ($Payload -and $Payload.results) {
        return @($Payload.results)
    }
    return @()
}

function Find-SmokeCase {
    param([string]$AccessToken)

    $queries = @(
        "/api/cases/?bucket=overdue&assigned_to=all&page_size=50",
        "/api/cases/?bucket=today&assigned_to=all&page_size=50",
        "/api/cases/?bucket=upcoming&assigned_to=all&page_size=50",
        "/api/cases/?bucket=awaiting&assigned_to=all&page_size=50",
        "/api/cases/?bucket=all&assigned_to=all&page_size=50"
    )

    foreach ($query in $queries) {
        $safeName = "cases-" + (($query -replace "[^a-zA-Z0-9]+", "-").Trim("-").ToLowerInvariant())
        $payload = Invoke-MobileApi -Name $safeName -Method GET -Path $query -AccessToken $AccessToken
        foreach ($case in (Get-MobileCaseResults -Payload $payload)) {
            if ($case.next_task -and $case.next_task.can_complete) {
                return [pscustomobject]@{
                    Case = $case
                    Task = $case.next_task
                    Query = $query
                }
            }
        }
    }

    throw "No smoke target found with a completable next_task."
}

function New-SmokeNotification {
    param(
        [string]$CaseId,
        [string]$Username,
        [string]$RunId
    )

    $safeUsername = $Username.Replace("\", "\\").Replace("'", "\'")
    $safeRunId = $RunId.Replace("\", "\\").Replace("'", "\'")
    $code = "from django.contrib.auth import get_user_model; from api.models import MobileNotification, MobileNotificationType; from patients.models import Case; user=get_user_model().objects.get(username='$safeUsername'); case=Case.objects.get(pk=$CaseId); n,_=MobileNotification.objects.get_or_create(user=user,dedupe_key='mobile-api-smoke-$safeRunId',defaults={'notification_type': MobileNotificationType.ASSIGNMENT, 'title': 'Mobile API smoke', 'body': 'Local endpoint smoke', 'case': case, 'payload': {'case_id': case.id}}); print(n.id)"
    Invoke-ProcessLogged `
        -Name "create-smoke-notification" `
        -FilePath "docker" `
        -Arguments @("compose", "exec", "-T", "web", "python", "manage.py", "shell", "-c", $code)

    $stdoutPath = Join-Path $EvidenceDir "create-smoke-notification.stdout.log"
    $stdout = if (Test-Path $stdoutPath) { Get-Content -Raw -Path $stdoutPath } else { "" }
    $matches = [regex]::Matches($stdout, "\d+")
    if ($matches.Count -eq 0) {
        throw "Could not determine smoke notification id. See $stdoutPath"
    }
    return $matches[$matches.Count - 1].Value
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

    Wait-HttpOk -Url ($BaseUrl.TrimEnd("/") + "/api/schema/") -TimeoutSeconds 90

    if ((Get-ListeningPortPids -Port 3899).Count -eq 0) {
        $dashboardCmd = "C:\Users\prave\Desktop\dashboard.cmd"
        if (Test-Path $dashboardCmd) {
            Write-Step "Starting Local Server Dashboard"
            $startedDashboard = $true
            Start-Process -FilePath $dashboardCmd -WindowStyle Hidden
        }
    }

    $dashboardSnapshotPath = Join-Path $EvidenceDir "dashboard-snapshot.json"
    $dashboardDeadline = (Get-Date).AddSeconds(45)
    do {
        try {
            $snapshot = Invoke-RestMethod -Uri "http://127.0.0.1:3899/api/snapshot" -TimeoutSec 10
            Save-Json -Path $dashboardSnapshotPath -Value $snapshot -Depth 8
            $snapshotText = $snapshot | ConvertTo-Json -Depth 8
            Assert-True ($snapshotText -like "*8000*") "Local Server Dashboard snapshot did not include port 8000."
            break
        }
        catch {
            if ((Get-Date) -ge $dashboardDeadline) {
                throw "Local Server Dashboard did not verify Test NNH discovery: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $dashboardDeadline)

    $token = Invoke-MobileApi `
        -Name "auth-token" `
        -Method POST `
        -Path "/api/auth/token/" `
        -Body @{ username = $Username; password = $Password }
    Assert-True ([bool]$token.access) "Token response did not include access token."
    Assert-True ([bool]$token.refresh) "Token response did not include refresh token."
    $accessToken = $token.access
    $refreshToken = $token.refresh
    Save-AuthEvidence -Name "auth-token" -Payload $token

    $me = Invoke-MobileApi -Name "me" -Method GET -Path "/api/me/" -AccessToken $accessToken
    Assert-True ($me.username -eq $Username) "GET /api/me/ returned unexpected username."

    $categories = Invoke-MobileApi -Name "metadata-categories" -Method GET -Path "/api/metadata/categories/" -AccessToken $accessToken
    Assert-True (@($categories.categories).Count -gt 0) "Category metadata was empty."

    $thresholds = Invoke-MobileApi -Name "vitals-thresholds" -Method GET -Path "/api/vitals-thresholds/" -AccessToken $accessToken
    Assert-True ([bool]$thresholds.metrics) "Vitals thresholds payload did not include metrics."
    Assert-True ([bool]$thresholds.status_labels) "Vitals thresholds payload did not include status labels."

    $target = Find-SmokeCase -AccessToken $accessToken
    $targetCase = $target.Case
    $targetTask = $target.Task
    Write-Step "Target case $($targetCase.id), task $($targetTask.id), query $($target.Query)"

    $caseDetail = Invoke-MobileApi -Name "case-detail" -Method GET -Path "/api/cases/$($targetCase.id)/" -AccessToken $accessToken
    Assert-True ($caseDetail.case.id -eq $targetCase.id) "Case detail returned an unexpected case id."
    Assert-True (@($caseDetail.tasks).Count -gt 0) "Case detail returned no tasks."

    $deviceToken = "mobile-api-smoke-$runId"
    $device = Invoke-MobileApi `
        -Name "devices" `
        -Method POST `
        -Path "/api/devices/" `
        -AccessToken $accessToken `
        -Body @{
            token = $deviceToken
            platform = "android"
            app_version = "local-smoke"
            device_label = "Codex local API smoke"
        }
    Assert-True ([bool]$device.id) "Device registration did not return an id."

    $attemptedAt = (Get-Date).ToUniversalTime().ToString("o")
    $callOutcome = Invoke-MobileApi `
        -Name "call-outcome" `
        -Method POST `
        -Path "/api/cases/$($targetCase.id)/call-outcome/" `
        -AccessToken $accessToken `
        -Body @{
            outcome = "no-answer"
            task_id = [int]$targetTask.id
            note = "Mobile API smoke call outcome $runId"
            attempted_at = $attemptedAt
            client_write_id = "mobile-api-smoke-call-$runId"
        }
    Assert-True ([bool]$callOutcome.call_log.id) "Call outcome response did not include call_log.id."

    $vitals = Invoke-MobileApi `
        -Name "case-vitals" `
        -Method POST `
        -Path "/api/cases/$($targetCase.id)/vitals/" `
        -AccessToken $accessToken `
        -Body @{
            pr = 83
            spo2 = 97
            client_write_id = "mobile-api-smoke-vital-$runId"
        }
    Assert-True ([bool]$vitals.latest_vital_id) "Vitals response did not include latest_vital_id."

    $taskComplete = Invoke-MobileApi `
        -Name "task-complete" `
        -Method POST `
        -Path "/api/tasks/$($targetTask.id)/complete/" `
        -AccessToken $accessToken `
        -Body @{ client_write_id = "mobile-api-smoke-task-$runId" }
    Assert-True ($taskComplete.task.id -eq $targetTask.id) "Task completion response returned unexpected task id."

    $notificationId = New-SmokeNotification -CaseId $targetCase.id -Username $Username -RunId $runId
    $notifications = Invoke-MobileApi -Name "notifications" -Method GET -Path "/api/notifications/?unread_only=true&page_size=50" -AccessToken $accessToken
    $notificationMatch = @($notifications.results | Where-Object { $_.id -eq [int]$notificationId })
    Assert-True ($notificationMatch.Count -gt 0) "Notifications endpoint did not return the smoke notification."

    $notificationRead = Invoke-MobileApi -Name "notification-read" -Method POST -Path "/api/notifications/$notificationId/read/" -AccessToken $accessToken
    Assert-True ($notificationRead.id -eq [int]$notificationId) "Notification read endpoint returned unexpected id."

    $refresh = Invoke-MobileApi `
        -Name "auth-token-refresh" `
        -Method POST `
        -Path "/api/auth/token/refresh/" `
        -Body @{ refresh = $refreshToken }
    Assert-True ([bool]$refresh.access) "Refresh response did not include access token."
    Save-AuthEvidence -Name "auth-token-refresh" -Payload $refresh

    $logout = Invoke-MobileApi `
        -Name "auth-logout" `
        -Method POST `
        -Path "/api/auth/logout/" `
        -AccessToken $refresh.access `
        -Body @{ refresh = $refreshToken; device_token = $deviceToken }
    Assert-True ($logout.message -like "*Logged out*") "Logout response did not confirm logout."

    $checks = [ordered]@{
        hasJwtLogin = [bool]$token.access
        hasMe = $me.username -eq $Username
        hasCategories = @($categories.categories).Count -gt 0
        hasVitalsThresholds = [bool]$thresholds.metrics
        hasCaseListTarget = [bool]$targetCase.id
        hasCaseDetail = $caseDetail.case.id -eq $targetCase.id
        hasDeviceRegistration = [bool]$device.id
        hasCallOutcomeWrite = [bool]$callOutcome.call_log.id
        hasVitalsWrite = [bool]$vitals.latest_vital_id
        hasTaskCompletionWrite = $taskComplete.task.id -eq $targetTask.id
        hasNotificationList = $notificationMatch.Count -gt 0
        hasNotificationRead = $notificationRead.id -eq [int]$notificationId
        hasTokenRefresh = [bool]$refresh.access
        hasLogout = $logout.message -like "*Logged out*"
        hasDashboardDiscovery = Test-Path $dashboardSnapshotPath
    }

    $summary = [ordered]@{
        passed = $true
        baseUrl = $BaseUrl
        username = $Username
        runId = $runId
        targetCaseId = $targetCase.id
        targetTaskId = $targetTask.id
        notificationId = [int]$notificationId
        checks = $checks
        responses = $responses
        evidenceDir = $EvidenceDir
    }
    Save-Json -Path (Join-Path $EvidenceDir "summary.json") -Value $summary -Depth 10
    Write-Step "PASS"
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
