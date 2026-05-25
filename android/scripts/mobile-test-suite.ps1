[CmdletBinding()]
param(
    [string]$EvidenceDir = "",
    [switch]$KeepServer,
    [switch]$SkipAndroid,
    [switch]$SkipDjango
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$androidRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $androidRoot

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDir = Join-Path $repoRoot "output\mobile-test-suite-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$startedServer = $false

function Write-Step {
    param([string]$Message)
    Write-Host "[mobile-tests] $Message"
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
    return [ordered]@{
        exitCode = [int]$process.ExitCode
        log = $logPath
        stdout = $stdoutPath
        stderr = $stderrPath
    }
}

function Get-ListeningPortPids {
    param([int]$Port)
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

try {
    Write-Step "Evidence: $EvidenceDir"

    $djangoResult = $null
    if (-not $SkipDjango) {
        if ((Get-ListeningPortPids -Port 8000).Count -eq 0) {
            Write-Step "Starting Test NNH server"
            $startedServer = $true
            Invoke-ProcessLogged `
                -Name "test-nnh-up" `
                -FilePath "powershell.exe" `
                -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "local-dev\test-nnh-up.ps1")) |
                Out-Null
        }
        else {
            Write-Step "Reusing existing listener on port 8000"
        }

        Write-Step "Running full Django test suite"
        $djangoResult = Invoke-ProcessLogged `
            -Name "django-tests" `
            -FilePath "docker" `
            -Arguments @("compose", "exec", "-T", "web", "python", "manage.py", "test")
    }

    $androidResult = $null
    if (-not $SkipAndroid) {
        Write-Step "Running Android unit tests"
        $androidResult = Invoke-ProcessLogged `
            -Name "android-test-debug-unit" `
            -FilePath (Join-Path $androidRoot "gradlew.bat") `
            -Arguments @("--no-daemon", "testDebugUnitTest") `
            -WorkingDirectory $androidRoot
    }

    $summary = [ordered]@{
        passed = (($SkipDjango -or ($djangoResult -and $djangoResult.exitCode -eq 0)) -and ($SkipAndroid -or ($androidResult -and $androidResult.exitCode -eq 0)))
        django = [ordered]@{
            skipped = [bool]$SkipDjango
            exitCode = if ($djangoResult) { $djangoResult.exitCode } else { $null }
            log = if ($djangoResult) { $djangoResult.log } else { $null }
        }
        android = [ordered]@{
            skipped = [bool]$SkipAndroid
            exitCode = if ($androidResult) { $androidResult.exitCode } else { $null }
            log = if ($androidResult) { $androidResult.log } else { $null }
        }
        evidenceDir = $EvidenceDir
    }
    Save-Json -Path (Join-Path $EvidenceDir "summary.json") -Value $summary -Depth 8
    if (-not $summary.passed) {
        throw "Mobile test suite failed. See $EvidenceDir"
    }
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
                -AllowFailure |
                Out-Null
        }
        catch {
            $cleanup["serverStopError"] = $_.Exception.Message
        }
    }
    Start-Sleep -Seconds 2
    $cleanup["port8000"] = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)
    $cleanup["adbDevices"] = try { (adb devices | Out-String).Trim() } catch { $_.Exception.Message }
    Save-Json -Path (Join-Path $EvidenceDir "cleanup-status.json") -Value $cleanup -Depth 6
}
