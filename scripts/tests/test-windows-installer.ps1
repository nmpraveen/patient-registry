#requires -Version 7.2
# In-process cmdlet fakes: never registers or reads real scheduled tasks.
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$installer = Join-Path $repo 'deploy/windows/Install-MedtrackVerifierTasks.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('medtrack-installer-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
$global:MedtrackTestTasks = @{}
$global:MedtrackTestRegistrations = 0
function Assert($value, $message) { if (-not $value) { throw $message } }
function Get-ScheduledTask { [CmdletBinding()]param($TaskName,$TaskPath) return $global:MedtrackTestTasks[$TaskName] }
function Get-ScheduledTaskInfo { param($TaskName,$TaskPath) return @{NextRunTime='synthetic-next-run';LastTaskResult=0} }
function New-ScheduledTaskPrincipal { param($UserId,$LogonType,$RunLevel) return @{UserId=$UserId;LogonType=$LogonType;RunLevel=$RunLevel} }
function New-ScheduledTaskAction { param($Execute,$Argument,$WorkingDirectory) return @{Execute=$Execute;Arguments=$Argument;WorkingDirectory=$WorkingDirectory} }
function New-ScheduledTaskTrigger { param([switch]$Weekly,[switch]$Daily,$WeeksInterval,$DaysOfWeek,$At) return @{Weekly=[bool]$Weekly;Daily=[bool]$Daily;WeeksInterval=$WeeksInterval;DaysOfWeek=$DaysOfWeek;At=$At} }
function New-ScheduledTaskSettingsSet { param([switch]$StartWhenAvailable,$MultipleInstances,[switch]$Hidden,$ExecutionTimeLimit) return @{StartWhenAvailable=[bool]$StartWhenAvailable;MultipleInstances=$MultipleInstances;Hidden=[bool]$Hidden;ExecutionTimeLimit=$ExecutionTimeLimit} }
function Register-ScheduledTask {
    param($TaskName,$TaskPath,$Action,$Trigger,$Settings,$Principal,[switch]$Force)
    $global:MedtrackTestRegistrations++
    $global:MedtrackTestTasks[$TaskName] = @{TaskName=$TaskName;Principal=$Principal;Triggers=$Trigger;Settings=$Settings;Action=$Action}
}
try {
    $configPath = Join-Path $testRoot 'private config.json'
    @{StatusDirectory=(Join-Path $testRoot 'state');AlertScriptPath=$installer;PowerShellExecutable=(Join-Path $PSHOME 'pwsh.exe');TaskNamePrefix='Synthetic';RunTimeoutSeconds=14400} | ConvertTo-Json | Set-Content -LiteralPath $configPath
    $failed = $false
    try { & $installer -ConfigPath $configPath | Out-Null } catch { $failed = $true }
    Assert $failed 'Missing principal should require explicit account policy'
    Assert ($global:MedtrackTestRegistrations -eq 0) 'Default created new tasks'
    $output = & $installer -ConfigPath $configPath -AccountPolicy CurrentUserInteractive
    Assert ($global:MedtrackTestRegistrations -eq 3) 'Expected exactly three registrations'
    Assert ($output -match 'synthetic-next-run') 'Installer did not read back actual task info'
    $restore = $global:MedtrackTestTasks['Synthetic-Restore']
    $health = $global:MedtrackTestTasks['Synthetic-Health']
    $scrub = $global:MedtrackTestTasks['Synthetic-FullScrub']
    Assert ($restore.Principal.LogonType -eq 'Interactive') 'Wrong explicit logon policy'
    Assert ($restore.Triggers.Weekly -and $restore.Triggers.WeeksInterval -eq 1) 'Restore is not weekly'
    Assert ($scrub.Triggers.Weekly -and $scrub.Triggers.WeeksInterval -eq 1) 'Scrub is not weekly'
    Assert ($health.Triggers.Count -eq 4) 'Health needs four daily triggers'
    Assert (($health.Triggers.At -join ',') -eq '00:00,06:00,12:00,18:00') 'Health cadence changed'
    Assert ($restore.Settings.Hidden -and $restore.Settings.StartWhenAvailable -and $restore.Settings.MultipleInstances -eq 'IgnoreNew') 'Unsafe scheduler settings'
    Assert ($restore.Settings.ExecutionTimeLimit.TotalSeconds -eq 15000) 'Timeout lacks startup/alert allowance'
    Assert ($restore.Action.Arguments.Contains('-WindowStyle Hidden') -and $restore.Action.Arguments.Contains('"' + $configPath + '"')) 'Scheduler paths are not quoted/hidden'
    $restore.Principal = @{UserId='intentional-service-account';LogonType='S4U';RunLevel='Limited'}
    & $installer -ConfigPath $configPath | Out-Null
    Assert ($global:MedtrackTestTasks['Synthetic-Restore'].Principal.UserId -eq 'intentional-service-account') 'Existing account was changed'
    $before = $global:MedtrackTestRegistrations
    $failed = $false
    try { & $installer -ConfigPath $configPath -AccountPolicy CurrentUserInteractive | Out-Null } catch { $failed = $true }
    Assert ($failed -and $global:MedtrackTestRegistrations -eq $before) 'Different existing account was overwritten'
    $global:MedtrackTestTasks['Synthetic-Restore'].Principal.LogonType = 'Password'
    $failed = $false
    try { & $installer -ConfigPath $configPath | Out-Null } catch { $failed = $true }
    Assert ($failed -and $global:MedtrackTestRegistrations -eq $before) 'Password principal should be handed back to the operator'
    'WINDOWS_INSTALLER_TEST_OK (cmdlet fakes only; no real tasks)'
} finally {
    Remove-Variable MedtrackTestTasks, MedtrackTestRegistrations -Scope Global -ErrorAction SilentlyContinue
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if ($resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'medtrack-installer-*') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

exit 0
