#requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ConfigPath,
    [Parameter(Mandatory)][string]$StatusDirectory,
    [Parameter(Mandatory)][string]$AlertScriptPath,
    [ValidateSet('Restore','Health','FullScrub')][string]$Mode = 'Health',
    [ValidateSet('None','Preflight','Docker','Launch','Runner','Alert')][string]$SimulateFailure = 'None'
)
$ErrorActionPreference = 'Stop'
$simulation = $SimulateFailure -ne 'None'
# Simulation cannot read private config, start Docker, run Bash or send notifications.
if ($simulation) { $StatusDirectory = Join-Path $StatusDirectory 'simulation' }
$state = [ordered]@{
    format = 'medtrack-windows-attempt-v1'; mode = $Mode; simulation = $simulation
    attemptId = [guid]::NewGuid().ToString('N'); status = 'running'
    startedUtc = [DateTime]::UtcNow.ToString('o'); updatedUtc = ''; stage = 'preflight'
    alertDelivery = 'not-needed'; exitCode = $null
}
$lock = $null
$code = 1
function Write-State([switch]$Claim) {
    [IO.Directory]::CreateDirectory($StatusDirectory) | Out-Null
    $path = Join-Path $StatusDirectory "$Mode.json"
    # All modes share this short transaction lock: ownership, dependency checks
    # and replacement must be atomic with concurrent claims, even failed runs.
    $writerLock = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    try {
        while ($null -eq $writerLock) {
            try { $writerLock = [IO.File]::Open((Join-Path $StatusDirectory 'status.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
            catch [IO.IOException] {
                if ([DateTime]::UtcNow -ge $deadline) { throw }
                Start-Sleep -Milliseconds 20
            }
        }
        if (-not $Claim) {
            $latest = [IO.File]::ReadAllText($path) | ConvertFrom-Json
            if ($latest.attemptId -ne $state.attemptId) { throw 'Status belongs to a newer attempt' }
        }
        if ($state.status -eq 'success') {
            if ($Mode -eq 'Health') { Assert-SuccessfulState 'Restore'; Assert-SuccessfulState 'FullScrub' }
            if ($Mode -eq 'FullScrub') { Assert-SuccessfulState 'Restore' }
        }
        $state.updatedUtc = [DateTime]::UtcNow.ToString('o')
        $temp = "$path.$($state.attemptId).tmp"
        $bytes = [Text.Encoding]::UTF8.GetBytes(($state | ConvertTo-Json))
        $stream = [IO.File]::Open($temp, 'Create', 'Write', 'None')
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
        [IO.File]::Move($temp, $path, $true)
    } finally { if ($null -ne $writerLock) { $writerLock.Dispose() } }
}
function Invoke-QuietProcess([string]$Executable, [string[]]$Arguments, [int]$TimeoutSeconds, [hashtable]$Environment = @{}, [switch]$TrackRunner) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($arg in $Arguments) { $info.ArgumentList.Add($arg) }
    foreach ($key in $Environment.Keys) { $info.Environment[$key] = $Environment[$key] }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    $started = $false
    try {
        if (-not $process.Start()) { throw 'Process launch failed' }
        $started = $true
        if ($TrackRunner) { $state.stage = 'runner'; Write-State }
        # Drain streams without retaining output (hooks can print private data).
        $stdout = $process.StandardOutput.BaseStream.CopyToAsync([IO.Stream]::Null)
        $stderr = $process.StandardError.BaseStream.CopyToAsync([IO.Stream]::Null)
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill($true); $process.WaitForExit(); throw 'Process timed out'
        }
        $null = $stdout.GetAwaiter().GetResult(); $null = $stderr.GetAwaiter().GetResult()
        return $process.ExitCode
    } finally {
        if ($started -and -not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
    }
}
function Assert-SuccessfulState([string]$Name) {
    $previous = Get-Content -LiteralPath (Join-Path $StatusDirectory "$Name.json") -Raw | ConvertFrom-Json
    if ($previous.format -ne 'medtrack-windows-attempt-v1' -or $previous.mode -ne $Name -or
        $previous.simulation -ne $false -or $previous.status -ne 'success' -or
        $previous.alertDelivery -ne 'not-needed' -or $previous.exitCode -ne 0) { throw 'Prior verifier attempt is not successful' }
}
try {
    Write-State -Claim
    if ($simulation) {
        $state.stage = switch ($SimulateFailure) { Preflight {'preflight'} Docker {'docker'} Launch {'launch'} default {'runner'} }
        throw 'Bounded synthetic failure'
    }
    $lock = [IO.File]::Open((Join-Path $StatusDirectory 'runner.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    foreach ($name in @('SourceRoot','BashSourceRoot','BashExecutable','BackupConfigPath','DockerExecutable','DockerContext')) {
        if ([string]::IsNullOrWhiteSpace($config.$name)) { throw 'Missing required configuration' }
    }
    foreach ($path in @($config.SourceRoot, $config.BashExecutable, $config.DockerExecutable, $AlertScriptPath)) {
        if (-not [IO.Path]::IsPathFullyQualified($path) -or -not (Test-Path -LiteralPath $path)) { throw 'Missing absolute local path' }
    }
    if ($config.BashSourceRoot -notmatch '^/' -or $config.BackupConfigPath -notmatch '^/') { throw 'Bash paths must be absolute' }
    $timeout = [int]$config.RunTimeoutSeconds
    if ($timeout -lt 1 -or $timeout -gt 21600) { throw 'Run timeout must be 1..21600 seconds' }
    if ($Mode -eq 'Health') { Assert-SuccessfulState 'Restore'; Assert-SuccessfulState 'FullScrub' }
    if ($Mode -eq 'FullScrub') { Assert-SuccessfulState 'Restore' }
    $state.stage = 'docker'; Write-State
    $dockerArgs = @('--context', [string]$config.DockerContext, 'info', '--format', '{{.OSType}}')
    if ((Invoke-QuietProcess $config.DockerExecutable $dockerArgs 30) -ne 0) {
        if (-not $config.DockerDesktopExecutable -or -not [IO.Path]::IsPathFullyQualified($config.DockerDesktopExecutable) -or -not (Test-Path -LiteralPath $config.DockerDesktopExecutable)) { throw 'Docker unavailable' }
        Start-Process -FilePath $config.DockerDesktopExecutable -WindowStyle Hidden | Out-Null
        $ready = $false
        for ($attempt = 0; $attempt -lt 12; $attempt++) {
            Start-Sleep -Seconds 5
            if ((Invoke-QuietProcess $config.DockerExecutable $dockerArgs 10) -eq 0) { $ready = $true; break }
        }
        if (-not $ready) { throw 'Docker startup failed' }
    }
    $state.stage = 'launch'; Write-State
    $entry = if ($Mode -eq 'Restore') { 'run-offsite-scratch-restore.sh' } else { 'check-offsite-backups.sh' }
    if (-not (Test-Path -LiteralPath (Join-Path $config.SourceRoot "scripts/$entry"))) { throw 'Reviewed entrypoint missing' }
    $arguments = @('--noprofile', '--norc', "$($config.BashSourceRoot.TrimEnd('/'))/scripts/$entry")
    if ($Mode -ne 'Restore') { $arguments += @('--production', '--hash-mode', $(if ($Mode -eq 'FullScrub') { 'all' } else { 'incremental' })) }
    $runnerCode = Invoke-QuietProcess $config.BashExecutable $arguments $timeout @{
        MEDTRACK_BACKUP_CONFIG = [string]$config.BackupConfigPath
        MEDTRACK_HEALTH_PRODUCTION_MODE = '1'; DOCKER_CONTEXT = [string]$config.DockerContext
    } -TrackRunner
    if ($runnerCode -ne 0) { throw 'Verifier runner failed' }
    $state.status = 'success'; $state.stage = 'complete'; $state.exitCode = 0
    Write-State
    $code = 0
} catch {
    $state.status = 'failure'; $state.exitCode = 1; $state.alertDelivery = 'pending'
    try { Write-State } catch { [Console]::Error.WriteLine('MEDTRACK_STATUS_WRITE_FAILED') }
    try {
        if ($simulation) {
            if ($SimulateFailure -eq 'Alert') { throw 'Synthetic alert delivery failure' }
            $state.alertDelivery = 'simulated'
        } else {
            $alertCode = Invoke-QuietProcess (Join-Path $PSHOME 'pwsh.exe') @('-NoProfile','-NonInteractive','-File', $AlertScriptPath,
                '-Title', 'MEDTRACK verifier failure', '-Message', "Mode=$Mode stage=$($state.stage); inspect private runner status.") 60
            if ($alertCode -ne 0) { throw 'Alert delivery failed' }
            $state.alertDelivery = 'delivered'
        }
    } catch { $state.alertDelivery = 'failed'; $state.exitCode = 2 }
    try { Write-State } catch { [Console]::Error.WriteLine('MEDTRACK_STATUS_WRITE_FAILED'); $state.exitCode = 2 }
    $code = $state.exitCode
    [Console]::Error.WriteLine("MEDTRACK_VERIFIER_FAIL mode=$Mode stage=$($state.stage) alert_delivery=$($state.alertDelivery) simulation=$simulation")
} finally { if ($null -ne $lock) { $lock.Dispose() } }
exit $code
