#requires -Version 7.2
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$wrapper = Join-Path $repo 'deploy/windows/Invoke-MedtrackVerifier.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('medtrack-wrapper-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
function Assert($condition, $message) { if (-not $condition) { throw $message } }
function Read-AtomicState([string]$Path) {
    # Poll without denying Windows rename/delete access to the atomic writer.
    $stream = [IO.File]::Open($Path, 'Open', 'Read', ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    $reader = [IO.StreamReader]::new($stream)
    try { $content = $reader.ReadToEnd() } finally { $reader.Dispose() }
    return $content | ConvertFrom-Json
}
try {
    $stubSource = Join-Path $testRoot 'stub.cs'
    @'
using System;
using System.IO;
class Stub {
  static int Main(string[] args) {
    bool docker = args.Length > 0 && args[0] == "--context";
    if (!docker) File.WriteAllLines(Environment.GetEnvironmentVariable("TEST_BASH_ARGS"), args);
    var release = Environment.GetEnvironmentVariable("TEST_RUNNER_RELEASE");
    if (!docker && !String.IsNullOrEmpty(release)) {
      for (int i = 0; i < 200 && !File.Exists(release); i++) System.Threading.Thread.Sleep(50);
      if (!File.Exists(release)) return 87;
    }
    var code = Environment.GetEnvironmentVariable(docker ? "TEST_DOCKER_EXIT" : "TEST_RUNNER_EXIT");
    return String.IsNullOrEmpty(code) ? 0 : Int32.Parse(code);
  }
}
'@ | Set-Content -LiteralPath $stubSource
    $stub = Join-Path $testRoot 'fake process.exe'
    & "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:exe "/out:$stub" $stubSource
    Assert ($LASTEXITCODE -eq 0) 'Stub compilation failed'
    $alert = Join-Path $testRoot 'fake alert.ps1'
    'param($Title,$Message); Add-Content -LiteralPath $env:TEST_ALERT_LOG -Value "synthetic"; exit ([int]$env:TEST_ALERT_EXIT)' | Set-Content -LiteralPath $alert
    $env:TEST_ALERT_LOG = Join-Path $testRoot 'alerts.log'
    $env:TEST_BASH_ARGS = Join-Path $testRoot 'args.txt'
    $env:TEST_ALERT_EXIT = '0'; $env:TEST_DOCKER_EXIT = '0'; $env:TEST_RUNNER_EXIT = '0'
    $status = Join-Path $testRoot 'state'
    $configPath = Join-Path $testRoot 'private config.json'
    $config = @{
        SourceRoot=$repo; BashSourceRoot='/c/synthetic source with spaces'; BashExecutable=$stub
        BackupConfigPath='/c/private config/backup.env'; DockerExecutable=$stub; DockerContext='synthetic-only'
        RunTimeoutSeconds=10
    }
    function Save-Config { $config | ConvertTo-Json | Set-Content -LiteralPath $configPath }
    function Run([string]$mode, [int]$expected, [string]$stage, [string]$simulation='None') {
        & (Join-Path $PSHOME 'pwsh.exe') -NoProfile -File $wrapper -ConfigPath $configPath -StatusDirectory $status -AlertScriptPath $alert -Mode $mode -SimulateFailure $simulation
        Assert ($LASTEXITCODE -eq $expected) "Wrong exit code for $mode / $stage"
        $directory = if ($simulation -eq 'None') { $status } else { Join-Path $status 'simulation' }
        $result = Get-Content -LiteralPath (Join-Path $directory "$mode.json") -Raw | ConvertFrom-Json
        Assert ($result.stage -eq $stage) "Wrong stage: $($result.stage) expected $stage"
        Assert ($result.status -eq $(if ($expected -eq 0) {'success'} else {'failure'})) 'Wrong status'
        return $result
    }
    Save-Config
    $result = Run Restore 0 complete
    Assert ($result.alertDelivery -eq 'not-needed') 'Success delivery wrong'
    $arguments = Get-Content -LiteralPath $env:TEST_BASH_ARGS
    Assert ($arguments.Count -eq 3 -and $arguments[2] -eq '/c/synthetic source with spaces/scripts/run-offsite-scratch-restore.sh') 'Bash arguments lost boundaries'
    Run FullScrub 0 complete | Out-Null
    Run Health 0 complete | Out-Null
    $arguments = Get-Content -LiteralPath $env:TEST_BASH_ARGS
    Assert ($arguments -contains '--production') 'Production gates not enforced'
    Assert ($arguments[-1] -eq 'incremental') 'Health mode did not select incremental'
    '{invalid' | Set-Content -LiteralPath $configPath
    Run Restore 1 preflight | Out-Null
    Save-Config
    Run Health 1 preflight | Out-Null
    $env:TEST_DOCKER_EXIT = '8'
    Run Restore 1 docker | Out-Null
    $env:TEST_DOCKER_EXIT = '0'
    $badExe = Join-Path $testRoot 'invalid.exe'
    'not an executable' | Set-Content -LiteralPath $badExe
    $config.BashExecutable = $badExe; Save-Config
    Run Restore 1 launch | Out-Null
    $config.BashExecutable = $stub; Save-Config
    $env:TEST_RUNNER_EXIT = '9'
    Run Restore 1 runner | Out-Null
    $env:TEST_ALERT_EXIT = '4'
    $result = Run Restore 2 runner
    Assert ($result.alertDelivery -eq 'failed') 'Alert failure was hidden'
    $env:TEST_RUNNER_EXIT = '0'; $env:TEST_ALERT_EXIT = '0'
    Run Restore 0 complete | Out-Null
    $before = Get-FileHash -LiteralPath (Join-Path $status 'Restore.json')
    $alertsBefore = (Get-Content -LiteralPath $env:TEST_ALERT_LOG).Count
    foreach ($simulation in @('Preflight','Docker','Launch','Runner','Alert')) {
        $stage = switch ($simulation) { Preflight {'preflight'} Docker {'docker'} Launch {'launch'} default {'runner'} }
        $expected = if ($simulation -eq 'Alert') {2} else {1}
        $result = Run Restore $expected $stage $simulation
        Assert ($result.simulation -eq $true) 'Simulation not labeled'
    }
    Assert ((Get-FileHash -LiteralPath (Join-Path $status 'Restore.json')).Hash -eq $before.Hash) 'Simulation altered real status'
    Assert ((Get-Content -LiteralPath $env:TEST_ALERT_LOG).Count -eq $alertsBefore) 'Simulation delivered notification'
    # Same-mode supersession, cross-mode contention, and interruption after a
    # Restore claim must all prevent an in-flight verifier publishing success.
    foreach ($scenario in @('Restore','Health','FullScrub','HealthInterrupted')) {
        Run Restore 0 complete | Out-Null
        Run FullScrub 0 complete | Out-Null
        $olderMode = if ($scenario -eq 'HealthInterrupted') { 'Health' } else { $scenario }
        $release = Join-Path $testRoot "release-$scenario"
        $info = [Diagnostics.ProcessStartInfo]::new()
        $info.FileName = Join-Path $PSHOME 'pwsh.exe'
        $info.UseShellExecute = $false; $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
        foreach ($argument in @('-NoProfile','-File',$wrapper,'-ConfigPath',$configPath,'-StatusDirectory',$status,'-AlertScriptPath',$alert,'-Mode',$olderMode)) { $info.ArgumentList.Add($argument) }
        $info.Environment['TEST_RUNNER_RELEASE'] = $release
        $older = [Diagnostics.Process]::new()
        $older.StartInfo = $info
        try {
            Assert ($older.Start()) 'Could not start concurrent fixture'
            $stdout = $older.StandardOutput.ReadToEndAsync()
            $stderr = $older.StandardError.ReadToEndAsync()
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            $olderState = $null
            do {
                $candidate = Read-AtomicState (Join-Path $status "$olderMode.json")
                if ($candidate.status -eq 'running' -and $candidate.stage -eq 'runner') { $olderState = $candidate; break }
                Start-Sleep -Milliseconds 20
            } while ([DateTime]::UtcNow -lt $deadline -and -not $older.HasExited)
            if ($null -eq $olderState) {
                $diagnostic = if ($older.HasExited) { "exit=$($older.ExitCode) stderr=$($stderr.GetAwaiter().GetResult())" } else { 'child still running' }
                throw "Older runner never reached bounded wait: scenario=$scenario lastStage=$($candidate.stage) $diagnostic"
            }
            if ($scenario -eq 'HealthInterrupted') {
                # Emulate a process killed immediately after its atomic claim,
                # before it can fail the execution lock or send an alert.
                $newer = Get-Content -LiteralPath (Join-Path $status 'Restore.json') -Raw | ConvertFrom-Json
                $newer.attemptId = [guid]::NewGuid().ToString('N'); $newer.status = 'running'
                $newer.stage = 'preflight'; $newer.exitCode = $null
                $stateLock = [IO.File]::Open((Join-Path $status 'status.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
                try {
                    $tempState = Join-Path $status 'interrupted.tmp'
                    [IO.File]::WriteAllText($tempState, ($newer | ConvertTo-Json))
                    [IO.File]::Move($tempState, (Join-Path $status 'Restore.json'), $true)
                } finally { $stateLock.Dispose() }
            } else {
                $newer = Run Restore 1 preflight
                Assert ($newer.attemptId -ne $olderState.attemptId) 'Concurrent attempt did not claim its own state'
                Assert ($newer.alertDelivery -eq 'delivered') 'Newer lock failure did not alert'
            }
            $newerHash = (Get-FileHash -LiteralPath (Join-Path $status 'Restore.json')).Hash
            [IO.File]::WriteAllText($release, 'release synthetic runner')
            Assert ($older.WaitForExit(5000)) 'Older runner did not finish after release'
            Assert ($older.ExitCode -ne 0) "In-flight $scenario returned success after invalidation"
            Assert ((Get-FileHash -LiteralPath (Join-Path $status 'Restore.json')).Hash -eq $newerHash) 'Older finalizer overwrote newer attempt'
            $final = Get-Content -LiteralPath (Join-Path $status "$olderMode.json") -Raw | ConvertFrom-Json
            Assert ($final.status -ne 'success') "In-flight $scenario published success after invalidation"
            $null = $stdout.GetAwaiter().GetResult(); $null = $stderr.GetAwaiter().GetResult()
            Run Health 1 preflight | Out-Null
        } finally {
            if (-not $older.HasExited) { $older.Kill($true); $older.WaitForExit() }
            $older.Dispose()
        }
    }
    Run Restore 0 complete | Out-Null
    $prior = Get-Content -LiteralPath (Join-Path $status 'Restore.json') -Raw | ConvertFrom-Json
    $prior.status = 'running'
    $prior | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $status 'Restore.json')
    Run Health 1 preflight | Out-Null
    'WINDOWS_VERIFIER_TEST_OK (synthetic only; no scheduler tasks or real notifications)'
} finally {
    foreach ($name in @('TEST_ALERT_LOG','TEST_BASH_ARGS','TEST_ALERT_EXIT','TEST_DOCKER_EXIT','TEST_RUNNER_EXIT')) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    $resolved = [IO.Path]::GetFullPath($testRoot)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'medtrack-wrapper-*') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

exit 0
