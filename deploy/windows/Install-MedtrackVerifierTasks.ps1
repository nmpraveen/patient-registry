#requires -Version 7.2
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ConfigPath,
    [ValidateSet('PreserveExisting','CurrentUserInteractive')][string]$AccountPolicy = 'PreserveExisting'
)
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$wrapper = Join-Path $PSScriptRoot 'Invoke-MedtrackVerifier.ps1'
foreach ($path in @($ConfigPath, $config.StatusDirectory, $config.AlertScriptPath, $config.PowerShellExecutable, $wrapper)) {
    if ([string]::IsNullOrWhiteSpace($path) -or -not [IO.Path]::IsPathFullyQualified($path) -or $path.Contains('"')) { throw 'Scheduler paths must be absolute and contain no quotes' }
}
foreach ($path in @($config.AlertScriptPath, $config.PowerShellExecutable)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Missing scheduler executable or alert helper' }
}
$prefix = [string]$config.TaskNamePrefix
if ($prefix -notmatch '^[A-Za-z0-9_-]+$') { throw 'TaskNamePrefix must contain only letters, numbers, dash and underscore' }
$timeout = [int]$config.RunTimeoutSeconds
if ($timeout -lt 1 -or $timeout -gt 21600) { throw 'Run timeout must be 1..21600 seconds' }
$currentAccount = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$plans = @()
# Validate every principal before changing any task.
foreach ($mode in @('Restore','Health','FullScrub')) {
    $name = "$prefix-$mode"
    $existing = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
    if ($AccountPolicy -eq 'CurrentUserInteractive') {
        if ($existing -and $existing.Principal.UserId -ne $currentAccount -and
            $existing.Principal.UserId -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
            throw "Refusing to replace a different account on $name; use PreserveExisting or explicitly retire that task first"
        }
        $principal = New-ScheduledTaskPrincipal -UserId $currentAccount -LogonType Interactive -RunLevel Limited
    } else {
        if (-not $existing) { throw "No existing principal for $name. Select CurrentUserInteractive explicitly, or provision the intentional unattended account separately." }
        if ($existing.Principal.LogonType -eq 'Password') { throw "Task $name uses password logon. Re-register it through an operator credential-aware route; this installer does not guess or collect credentials." }
        $principal = $existing.Principal
    }
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" -ConfigPath "{1}" -StatusDirectory "{2}" -AlertScriptPath "{3}" -Mode {4}' -f $wrapper, $ConfigPath, $config.StatusDirectory, $config.AlertScriptPath, $mode
    $action = New-ScheduledTaskAction -Execute $config.PowerShellExecutable -Argument $arguments -WorkingDirectory $PSScriptRoot
    $triggers = switch ($mode) {
        Restore { New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Saturday -At '01:00' }
        FullScrub { New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Sunday -At '01:00' }
        Health { foreach ($hour in @('00:00','06:00','12:00','18:00')) { New-ScheduledTaskTrigger -Daily -At $hour } }
    }
    # Allow Docker startup and failure alerting after the bounded verifier timeout.
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden -ExecutionTimeLimit (New-TimeSpan -Seconds ($timeout + 600))
    $plans += @{ Name=$name; Principal=$principal; Action=$action; Triggers=$triggers; Settings=$settings }
}
foreach ($plan in $plans) {
    if ($PSCmdlet.ShouldProcess($plan.Name, 'Register independent MEDTRACK verifier task')) {
        Register-ScheduledTask -TaskName $plan.Name -TaskPath '\' -Action $plan.Action -Trigger $plan.Triggers -Settings $plan.Settings -Principal $plan.Principal -Force | Out-Null
        $actual = Get-ScheduledTask -TaskName $plan.Name -TaskPath '\'
        $info = Get-ScheduledTaskInfo -TaskName $plan.Name -TaskPath '\'
        [pscustomobject]@{
            TaskName=$actual.TaskName; UserId=$actual.Principal.UserId; LogonType=[string]$actual.Principal.LogonType
            RunLevel=[string]$actual.Principal.RunLevel; Triggers=$actual.Triggers
            NextRunTime=$info.NextRunTime; LastTaskResult=$info.LastTaskResult
            Hidden=$actual.Settings.Hidden; StartWhenAvailable=$actual.Settings.StartWhenAvailable
            MultipleInstances=[string]$actual.Settings.MultipleInstances; ExecutionTimeLimit=$actual.Settings.ExecutionTimeLimit
        } | ConvertTo-Json -Depth 8
    }
}
