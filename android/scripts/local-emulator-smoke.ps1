[CmdletBinding()]
param(
    [string]$AvdName = "MarkUS_Latest_API37",
    [string]$Username = "admin",
    [string]$Password = "pass",
    [string]$EvidenceDir = "",
    [string]$ApiBaseUrl = "http://10.0.2.2:8000/",
    [string]$DeviceUnlockPin = "1234",
    [switch]$NoBuild,
    [switch]$OfflineWrites,
    [switch]$RequirePhysicalDevice,
    [switch]$UseAdbReverse,
    [switch]$KeepServer,
    [switch]$KeepEmulator
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$androidRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $androidRoot
$packageName = "com.naveenhospital.medtrack"
$emulatorExe = Join-Path $env:LOCALAPPDATA "Android\Sdk\emulator\emulator.exe"
$gradleBuildRoot = if ($env:MEDTRACK_ANDROID_BUILD_DIR) {
    $env:MEDTRACK_ANDROID_BUILD_DIR
}
else {
    Join-Path $env:USERPROFILE ".codex\build\medtrack-android"
}
$apkPath = Join-Path $gradleBuildRoot "app\outputs\apk\debug\app-debug.apk"

if (-not $EvidenceDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceDir = Join-Path $repoRoot "output\android-emulator-smoke-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$startedServer = $false
$startedDashboard = $false
$startedEmulator = $false
$networkDisabled = $false
$adbReverseEnabled = $false
$serial = $null

function Write-Step {
    param([string]$Message)
    Write-Host "[smoke] $Message"
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

function Get-AdbDeviceSerials {
    @(adb devices |
        Select-String -Pattern "^\S+\s+device$" |
        ForEach-Object { ($_ -split "\s+")[0] })
}

function Wait-ForDevice {
    param([int]$TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $devices = @(Get-AdbDeviceSerials)
        if ($devices.Count -gt 0) {
            return $devices[0]
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for Android emulator/device."
}

function Wait-ForBoot {
    param(
        [string]$DeviceSerial,
        [int]$TimeoutSeconds = 180
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $booted = (adb -s $DeviceSerial shell getprop sys.boot_completed 2>$null).Trim()
        if ($booted -eq "1") {
            adb -s $DeviceSerial shell input keyevent 224 | Out-Null
            adb -s $DeviceSerial shell wm dismiss-keyguard | Out-Null
            adb -s $DeviceSerial shell input keyevent 82 | Out-Null
            return
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $DeviceSerial to boot."
}

function Unlock-DeviceIfNeeded {
    param([string]$DeviceSerial)
    adb -s $DeviceSerial shell input keyevent 224 | Out-Null
    adb -s $DeviceSerial shell wm dismiss-keyguard | Out-Null
    Start-Sleep -Seconds 1
    if ($DeviceSerial -notlike "emulator-*") {
        return
    }
    if ([string]::IsNullOrWhiteSpace($DeviceUnlockPin)) {
        return
    }
    $lockDisabled = (adb -s $DeviceSerial shell locksettings get-disabled 2>$null | Out-String).Trim()
    if ($lockDisabled -notmatch "true") {
        Invoke-AdbTextInput -DeviceSerial $DeviceSerial -Value $DeviceUnlockPin
        adb -s $DeviceSerial shell input keyevent 66 | Out-Null
        Start-Sleep -Seconds 2
        adb -s $DeviceSerial shell wm dismiss-keyguard | Out-Null
    }
}

function Wait-ForHomeReady {
    param(
        [string]$DeviceSerial,
        [int]$TimeoutSeconds = 90
    )
    adb -s $DeviceSerial shell input keyevent 224 | Out-Null
    adb -s $DeviceSerial shell wm dismiss-keyguard | Out-Null
    adb -s $DeviceSerial shell cmd statusbar collapse 2>$null | Out-Null
    adb -s $DeviceSerial shell input keyevent 3 | Out-Null

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $xml = Get-UiXml -DeviceSerial $DeviceSerial -Attempts 2
            if ($xml -like "*com.google.android.apps.nexuslauncher*" -and ($xml -like "*Play Store*" -or $xml -like "*Phone*" -or $xml -like "*Google search*")) {
                Start-Sleep -Seconds 3
                return
            }
        }
        catch {
            $windowDump = (adb -s $DeviceSerial shell dumpsys window 2>$null | Out-String)
            if ($windowDump -like "*com.google.android.apps.nexuslauncher*" -or $windowDump -like "*NexusLauncher*") {
                Start-Sleep -Seconds 3
                return
            }
            adb -s $DeviceSerial shell cmd statusbar collapse 2>$null | Out-Null
            adb -s $DeviceSerial shell input keyevent 3 | Out-Null
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for Android launcher to stabilize."
}

function Test-AppForeground {
    param([string]$DeviceSerial)
    $windowDump = (adb -s $DeviceSerial shell dumpsys window 2>$null | Out-String)
    return ($windowDump -like "*mCurrentFocus*$packageName*" -or $windowDump -like "*mFocusedApp*$packageName*")
}

function Wait-ForLaunchablePackage {
    param(
        [string]$DeviceSerial,
        [int]$TimeoutSeconds = 45
    )
    $logPath = Join-Path $EvidenceDir "adb-launchable-ready.log"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0
    do {
        $attempt++
        $resolve = (adb -s $DeviceSerial shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p $packageName 2>&1 | Out-String).Trim()
        $path = (adb -s $DeviceSerial shell pm path $packageName 2>&1 | Out-String).Trim()
        @(
            "attempt=$attempt"
            "time=$((Get-Date).ToString('o'))"
            "pm path: $path"
            "resolve-activity: $resolve"
            ""
        ) | Add-Content -Path $logPath

        if ($path -like "package:*" -and $resolve -like "*$packageName*" -and $resolve -notlike "*No activity found*") {
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    (adb -s $DeviceSerial shell dumpsys package $packageName 2>&1 | Out-String) |
        Set-Content -Path (Join-Path $EvidenceDir "adb-dumpsys-package-after-launchable-timeout.txt")
    throw "Package $packageName was installed, but no launchable activity became visible after $TimeoutSeconds seconds. See $logPath"
}

function Start-AppAndWait {
    param(
        [string]$DeviceSerial,
        [int]$MaxAttempts = 4
    )
    Wait-ForLaunchablePackage -DeviceSerial $DeviceSerial -TimeoutSeconds 45
    Invoke-ProcessLogged `
        -Name "adb-resolve-launcher" `
        -FilePath "adb" `
        -Arguments @(
            "-s", $DeviceSerial,
            "shell", "cmd", "package", "resolve-activity",
            "--brief",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER",
            "-p", $packageName
        ) `
        -AllowFailure

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Invoke-ProcessLogged `
            -Name "adb-start-app-$attempt" `
            -FilePath "adb" `
            -Arguments @("-s", $DeviceSerial, "shell", "am", "start", "-W", "-n", "$packageName/.MainActivity") `
            -AllowFailure
        if ($script:LastProcessExitCode -eq 0) {
            Start-Sleep -Seconds 5
            if (Test-AppForeground -DeviceSerial $DeviceSerial) {
                return
            }
        }
        adb -s $DeviceSerial shell input keyevent 224 | Out-Null
        adb -s $DeviceSerial shell wm dismiss-keyguard | Out-Null

        Invoke-ProcessLogged `
            -Name "adb-start-app-monkey-$attempt" `
            -FilePath "adb" `
            -Arguments @(
                "-s", $DeviceSerial,
                "shell", "monkey",
                "-p", $packageName,
                "-c", "android.intent.category.LAUNCHER",
                "1"
            ) `
            -AllowFailure
        Start-Sleep -Seconds 5
        if (Test-AppForeground -DeviceSerial $DeviceSerial) {
            return
        }
    }
    throw "Could not bring $packageName to foreground after $MaxAttempts attempts."
}

function Normalize-UiXml {
    param([string]$Raw)
    $xmlStart = $Raw.IndexOf("<?xml")
    if ($xmlStart -lt 0) {
        $xmlStart = $Raw.IndexOf("<hierarchy")
    }
    if ($xmlStart -ge 0) {
        return $Raw.Substring($xmlStart).Trim()
    }
    return $Raw.Trim()
}

function Get-UiXml {
    param(
        [string]$DeviceSerial,
        [int]$Attempts = 8,
        [int]$DelayMilliseconds = 500
    )
    $lastOutput = ""
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $lastOutput = (adb -s $DeviceSerial exec-out uiautomator dump /dev/tty 2>$null | Out-String)
        $normalized = Normalize-UiXml -Raw $lastOutput
        if ($normalized -like "*<hierarchy*") {
            return $normalized
        }
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
    throw "Could not dump UI hierarchy after $Attempts attempts. Last output: $lastOutput"
}

function Save-DeviceState {
    param(
        [string]$DeviceSerial,
        [string]$Name
    )
    $remote = "/sdcard/medtrack-$Name.png"
    $png = Join-Path $EvidenceDir "$Name.png"
    $xml = Join-Path $EvidenceDir "$Name.xml"
    Start-Sleep -Milliseconds 750
    adb -s $DeviceSerial shell screencap -p $remote | Out-Null
    adb -s $DeviceSerial pull $remote $png | Out-Null
    try {
        Get-UiXml -DeviceSerial $DeviceSerial | Set-Content -Path $xml
    }
    catch {
        $_.Exception.Message | Set-Content -Path $xml
    }
}

function Get-TextCenter {
    param(
        [string]$Xml,
        [string]$Text
    )
    $escaped = [regex]::Escape($Text)
    $pattern = "text=`"$escaped`"[^>]*bounds=`"\[(\d+),(\d+)\]\[(\d+),(\d+)\]`""
    $match = [regex]::Match($Xml, $pattern)
    if (-not $match.Success) {
        return $null
    }
    $x1 = [int]$match.Groups[1].Value
    $y1 = [int]$match.Groups[2].Value
    $x2 = [int]$match.Groups[3].Value
    $y2 = [int]$match.Groups[4].Value
    [pscustomobject]@{
        X = [int](($x1 + $x2) / 2)
        Y = [int](($y1 + $y2) / 2)
    }
}

function Get-TextCenters {
    param(
        [string]$Xml,
        [string]$Text
    )
    $escaped = [regex]::Escape($Text)
    $pattern = "text=`"$escaped`"[^>]*bounds=`"\[(\d+),(\d+)\]\[(\d+),(\d+)\]`""
    @(
        [regex]::Matches($Xml, $pattern) | ForEach-Object {
            $x1 = [int]$_.Groups[1].Value
            $y1 = [int]$_.Groups[2].Value
            $x2 = [int]$_.Groups[3].Value
            $y2 = [int]$_.Groups[4].Value
            [pscustomobject]@{
                X = [int](($x1 + $x2) / 2)
                Y = [int](($y1 + $y2) / 2)
            }
        }
    )
}

function Get-ContentDescriptionCenter {
    param(
        [string]$Xml,
        [string]$ContentDescription
    )
    $escaped = [regex]::Escape($ContentDescription)
    $pattern = "content-desc=`"$escaped`"[^>]*bounds=`"\[(\d+),(\d+)\]\[(\d+),(\d+)\]`""
    $match = [regex]::Match($Xml, $pattern)
    if (-not $match.Success) {
        return $null
    }
    $x1 = [int]$match.Groups[1].Value
    $y1 = [int]$match.Groups[2].Value
    $x2 = [int]$match.Groups[3].Value
    $y2 = [int]$match.Groups[4].Value
    [pscustomobject]@{
        X = [int](($x1 + $x2) / 2)
        Y = [int](($y1 + $y2) / 2)
    }
}

function Tap-Text {
    param(
        [string]$DeviceSerial,
        [string]$Text
    )
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    $center = Get-TextCenter -Xml $xml -Text $Text
    if ($null -eq $center) {
        throw "Could not find text '$Text' to tap."
    }
    adb -s $DeviceSerial shell input tap $center.X $center.Y | Out-Null
}

function Tap-ContentDescription {
    param(
        [string]$DeviceSerial,
        [string]$ContentDescription
    )
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    $center = Get-ContentDescriptionCenter -Xml $xml -ContentDescription $ContentDescription
    if ($null -eq $center) {
        throw "Could not find content description '$ContentDescription' to tap."
    }
    adb -s $DeviceSerial shell input tap $center.X $center.Y | Out-Null
}

function Try-TapContentDescription {
    param(
        [string]$DeviceSerial,
        [string]$ContentDescription
    )
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    $center = Get-ContentDescriptionCenter -Xml $xml -ContentDescription $ContentDescription
    if ($null -eq $center) {
        return $false
    }
    adb -s $DeviceSerial shell input tap $center.X $center.Y | Out-Null
    return $true
}

function Tap-TextOccurrence {
    param(
        [string]$DeviceSerial,
        [string]$Text,
        [ValidateSet("First", "Last")]
        [string]$Occurrence = "First"
    )
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    $centers = @(Get-TextCenters -Xml $xml -Text $Text)
    if ($centers.Count -eq 0) {
        throw "Could not find text '$Text' to tap."
    }
    $center = if ($Occurrence -eq "Last") { $centers[-1] } else { $centers[0] }
    adb -s $DeviceSerial shell input tap $center.X $center.Y | Out-Null
}

function Try-TapText {
    param(
        [string]$DeviceSerial,
        [string]$Text
    )
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    $center = Get-TextCenter -Xml $xml -Text $Text
    if ($null -eq $center) {
        return $false
    }
    adb -s $DeviceSerial shell input tap $center.X $center.Y | Out-Null
    return $true
}

function Reveal-TextWithHorizontalSwipe {
    param(
        [string]$DeviceSerial,
        [string]$Text,
        [string]$AnchorText,
        [int]$Attempts = 3
    )
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        $xml = Get-UiXml -DeviceSerial $DeviceSerial
        if ($null -ne (Get-TextCenter -Xml $xml -Text $Text)) {
            return $true
        }
        $anchor = Get-TextCenter -Xml $xml -Text $AnchorText
        $y = if ($null -ne $anchor) { $anchor.Y } else { 930 }
        adb -s $DeviceSerial shell input swipe 1130 $y 580 $y 350 | Out-Null
        Start-Sleep -Milliseconds 700
    }
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    return $null -ne (Get-TextCenter -Xml $xml -Text $Text)
}

function Get-FirstClickableCardBounds {
    param(
        [string]$DeviceSerial,
        [int]$MinY = 160,
        [int]$MaxY = 1600
    )
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    $pattern = "<node[^>]*clickable=`"true`"[^>]*bounds=`"\[(\d+),(\d+)\]\[(\d+),(\d+)\]`"[^>]*>"
    $matches = [regex]::Matches($xml, $pattern)
    foreach ($match in $matches) {
        $x1 = [int]$match.Groups[1].Value
        $y1 = [int]$match.Groups[2].Value
        $x2 = [int]$match.Groups[3].Value
        $y2 = [int]$match.Groups[4].Value
        $width = $x2 - $x1
        $height = $y2 - $y1
        if ($y1 -ge $MinY -and $y1 -le $MaxY -and $width -ge 260 -and $height -ge 60) {
            return [pscustomobject]@{
                X1 = $x1
                Y1 = $y1
                X2 = $x2
                Y2 = $y2
                CenterX = [int](($x1 + $x2) / 2)
                CenterY = [int](($y1 + $y2) / 2)
                Width = $width
                Height = $height
            }
        }
    }
    throw "Could not find a clickable card between y=$MinY and y=$MaxY."
}

function Get-PatientRowBounds {
    param(
        [string]$DeviceSerial,
        [int]$MinY = 650,
        [int]$MaxY = 2650
    )
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    $pattern = "<node[^>]*clickable=`"false`"[^>]*scrollable=`"false`"[^>]*bounds=`"\[(\d+),(\d+)\]\[(\d+),(\d+)\]`"[^>]*>"
    $matches = [regex]::Matches($xml, $pattern)
    $rows = @()
    foreach ($match in $matches) {
        $x1 = [int]$match.Groups[1].Value
        $y1 = [int]$match.Groups[2].Value
        $x2 = [int]$match.Groups[3].Value
        $y2 = [int]$match.Groups[4].Value
        $width = $x2 - $x1
        $height = $y2 - $y1
        if ($y1 -ge $MinY -and $y1 -le $MaxY -and $width -ge 900 -and $height -ge 150 -and $height -le 700) {
            $rows += [pscustomobject]@{
                X1 = $x1
                Y1 = $y1
                X2 = $x2
                Y2 = $y2
                CenterX = [int](($x1 + $x2) / 2)
                CenterY = [int](($y1 + $y2) / 2)
                Width = $width
                Height = $height
            }
        }
    }
    return @($rows | Sort-Object Y1, X1)
}

function Get-FirstPatientRowBounds {
    param(
        [string]$DeviceSerial,
        [int]$MinY = 650,
        [int]$MaxY = 2650
    )
    $rows = @(Get-PatientRowBounds -DeviceSerial $DeviceSerial -MinY $MinY -MaxY $MaxY)
    if ($rows.Count -gt 0) {
        return $rows[0]
    }
    throw "Could not find a patient row between y=$MinY and y=$MaxY."
}

function Tap-FirstPatientRow {
    param(
        [string]$DeviceSerial,
        [int]$MinY = 650,
        [int]$MaxY = 2650
    )
    $bounds = Get-FirstPatientRowBounds -DeviceSerial $DeviceSerial -MinY $MinY -MaxY $MaxY
    $tapX = [Math]::Min($bounds.X2 - 80, $bounds.X1 + 260)
    $tapY = [Math]::Min($bounds.Y2 - 80, $bounds.Y1 + 75)
    adb -s $DeviceSerial shell input tap $tapX $tapY | Out-Null
}

function Tap-FirstClickableCard {
    param(
        [string]$DeviceSerial,
        [int]$MinY = 160,
        [int]$MaxY = 1600
    )
    $bounds = Get-FirstClickableCardBounds -DeviceSerial $DeviceSerial -MinY $MinY -MaxY $MaxY
    adb -s $DeviceSerial shell input tap $bounds.CenterX $bounds.CenterY | Out-Null
}

function Swipe-FirstPatientCard {
    param(
        [string]$DeviceSerial,
        [ValidateSet("Left", "Right")]
        [string]$Direction,
        [int]$RowIndex = 0,
        [int]$MinY = 650,
        [int]$MaxY = 2650
    )
    $rows = @(Get-PatientRowBounds -DeviceSerial $DeviceSerial -MinY $MinY -MaxY $MaxY)
    if ($rows.Count -le $RowIndex) {
        throw "Could not find patient row index $RowIndex between y=$MinY and y=$MaxY."
    }
    $bounds = $rows[$RowIndex]
    $padding = [Math]::Max(32, [int]($bounds.Width * 0.16))
    $startX = if ($Direction -eq "Left") { $bounds.X2 - $padding } else { $bounds.X1 + $padding }
    $endX = if ($Direction -eq "Left") { $bounds.X1 + $padding } else { $bounds.X2 - $padding }
    adb -s $DeviceSerial shell input swipe $startX $bounds.CenterY $endX $bounds.CenterY 450 | Out-Null
    return $bounds
}

function Test-AppForegroundStateWithin {
    param(
        [string]$DeviceSerial,
        [bool]$ShouldBeForeground,
        [int]$TimeoutSeconds = 10
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Test-AppForeground -DeviceSerial $DeviceSerial) -eq $ShouldBeForeground) {
            return $true
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Test-DialerVisibleWithin {
    param(
        [string]$DeviceSerial,
        [int]$TimeoutSeconds = 10
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $xml = Get-UiXml -DeviceSerial $DeviceSerial -Attempts 2
            if ($xml -like "*com.google.android.dialer*") {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Wait-ForAppForegroundState {
    param(
        [string]$DeviceSerial,
        [bool]$ShouldBeForeground,
        [int]$TimeoutSeconds = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Test-AppForeground -DeviceSerial $DeviceSerial) -eq $ShouldBeForeground) {
            return
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for app foreground state '$ShouldBeForeground'."
}

function Wait-ForText {
    param(
        [string]$DeviceSerial,
        [string[]]$Texts,
        [int]$TimeoutSeconds = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $xml = Get-UiXml -DeviceSerial $DeviceSerial -Attempts 3
        }
        catch {
            Start-Sleep -Seconds 2
            continue
        }
        foreach ($text in $Texts) {
            if ($xml -like "*$text*") {
                return $xml
            }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for text: $($Texts -join ', ')"
}

function Wait-ForNonEmptyInbox {
    param(
        [string]$DeviceSerial,
        [int]$TimeoutSeconds = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $xml = Get-UiXml -DeviceSerial $DeviceSerial -Attempts 3
            if ($xml -notlike "*No patients in this view*" -and $xml -notlike "*Refreshing*") {
                return $xml
            }
        }
        catch {
            Start-Sleep -Seconds 2
            continue
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for a non-empty inbox."
}

function Return-ToHome {
    param(
        [string]$DeviceSerial,
        [int]$TimeoutSeconds = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $xml = Get-UiXml -DeviceSerial $DeviceSerial -Attempts 3
        if ($xml -like "*Search patient*") {
            return $xml
        }
        if (-not (Try-TapContentDescription -DeviceSerial $DeviceSerial -ContentDescription "Back")) {
            adb -s $DeviceSerial shell input keyevent 4 | Out-Null
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out returning to the home inbox."
}

function Invoke-AdbTextInput {
    param(
        [string]$DeviceSerial,
        [string]$Value
    )
    $keyCodeByChar = @{
        "0" = 7
        "1" = 8
        "2" = 9
        "3" = 10
        "4" = 11
        "5" = 12
        "6" = 13
        "7" = 14
        "8" = 15
        "9" = 16
        "a" = 29
        "b" = 30
        "c" = 31
        "d" = 32
        "e" = 33
        "f" = 34
        "g" = 35
        "h" = 36
        "i" = 37
        "j" = 38
        "k" = 39
        "l" = 40
        "m" = 41
        "n" = 42
        "o" = 43
        "p" = 44
        "q" = 45
        "r" = 46
        "s" = 47
        "t" = 48
        "u" = 49
        "v" = 50
        "w" = 51
        "x" = 52
        "y" = 53
        "z" = 54
    }
    if ($Value -match "^[A-Za-z0-9]+$") {
        foreach ($character in $Value.ToLowerInvariant().ToCharArray()) {
            $key = [string]$character
            adb -s $DeviceSerial shell input keyevent $keyCodeByChar[$key] | Out-Null
            Start-Sleep -Milliseconds 80
        }
        return
    }
    $escaped = $Value.Replace(" ", "%s")
    adb -s $DeviceSerial shell input text $escaped | Out-Null
}

function Get-SmokeCaseId {
    param(
        [string]$Username,
        [string]$Password
    )
    $tokenResponse = Invoke-RestMethod `
        -Method Post `
        -Uri "http://localhost:8000/api/auth/token/" `
        -ContentType "application/json" `
        -Body (@{ username = $Username; password = $Password } | ConvertTo-Json)

    $queries = @(
        "bucket=overdue&assigned_to=all&page_size=1",
        "bucket=today&assigned_to=all&page_size=1",
        "bucket=upcoming&assigned_to=all&page_size=1",
        "bucket=awaiting&assigned_to=all&page_size=1",
        "bucket=red&assigned_to=all&page_size=1",
        "assigned_to=all&page_size=1",
        "assigned_to=me&page_size=1"
    )
    foreach ($query in $queries) {
        try {
            $caseResponse = Invoke-RestMethod `
                -Uri "http://localhost:8000/api/cases/?$query" `
                -Headers @{ Authorization = "Bearer $($tokenResponse.access)" } `
                -TimeoutSec 20
            $results = @($caseResponse.results)
            if ($results.Count -gt 0) {
                return [string]$results[0].id
            }
        }
        catch {
            Write-Step "Case lookup failed for ${query}: $($_.Exception.Message)"
        }
    }

    throw "Could not find a case for notification deep-link smoke."
}

function Get-MobileApiToken {
    param(
        [string]$Username,
        [string]$Password
    )
    $tokenResponse = Invoke-RestMethod `
        -Method Post `
        -Uri "http://localhost:8000/api/auth/token/" `
        -ContentType "application/json" `
        -Body (@{ username = $Username; password = $Password } | ConvertTo-Json) `
        -TimeoutSec 20
    return $tokenResponse.access
}

function Get-MobileApiHeaders {
    param([string]$AccessToken)
    @{ Authorization = "Bearer $AccessToken" }
}

function Invoke-MobileApiGet {
    param(
        [string]$AccessToken,
        [string]$Path
    )
    Invoke-RestMethod `
        -Method Get `
        -Uri "http://localhost:8000$Path" `
        -Headers (Get-MobileApiHeaders -AccessToken $AccessToken) `
        -TimeoutSec 20
}

function Get-OfflineWriteTarget {
    param([string]$AccessToken)
    $queries = @(
        "bucket=overdue&assigned_to=all&page_size=50",
        "bucket=today&assigned_to=all&page_size=50",
        "bucket=upcoming&assigned_to=all&page_size=50",
        "assigned_to=all&page_size=50"
    )
    foreach ($query in $queries) {
        $response = Invoke-MobileApiGet -AccessToken $AccessToken -Path "/api/cases/?$query"
        foreach ($case in @($response.results)) {
            if (-not [string]::IsNullOrWhiteSpace([string]$case.phone_number) -and $case.next_task -and $case.next_task.id) {
                return [pscustomobject]@{
                    Id = [string]$case.id
                    Uhid = [string]$case.uhid
                    Name = [string]$case.name
                    TaskId = [string]$case.next_task.id
                    Bucket = if ($query -match "bucket=([^&]+)") { $Matches[1] } else { "" }
                    Query = $query
                }
            }
        }
    }
    throw "Could not find a mobile case with both phone_number and next_task for offline write smoke."
}

function Get-CaseDetailFromApi {
    param(
        [string]$AccessToken,
        [string]$CaseId
    )
    Invoke-MobileApiGet -AccessToken $AccessToken -Path "/api/cases/$CaseId/"
}

function Get-ObjectIds {
    param([object[]]$Items)
    @($Items | ForEach-Object { [string]$_.id })
}

function Set-EmulatorNetwork {
    param(
        [string]$DeviceSerial,
        [bool]$Enabled
    )
    if ($Enabled) {
        adb -s $DeviceSerial shell settings put global airplane_mode_on 0 | Out-Null
        adb -s $DeviceSerial shell svc wifi enable | Out-Null
        adb -s $DeviceSerial shell svc data enable | Out-Null
        $script:networkDisabled = $false
    }
    else {
        adb -s $DeviceSerial shell settings put global airplane_mode_on 1 | Out-Null
        adb -s $DeviceSerial shell svc wifi disable | Out-Null
        adb -s $DeviceSerial shell svc data disable | Out-Null
        $script:networkDisabled = $true
    }
    Start-Sleep -Seconds 5
}

function Invoke-WorkManagerJobs {
    param([string]$DeviceSerial)
    $dump = (adb -s $DeviceSerial shell dumpsys jobscheduler $packageName 2>$null | Out-String)
    $jobIds = @(
        [regex]::Matches($dump, "JOB #\S+/(\d+):.*?$([regex]::Escape($packageName))") |
            ForEach-Object { $_.Groups[1].Value } |
            Sort-Object -Unique
    )
    foreach ($jobId in $jobIds) {
        adb -s $DeviceSerial shell cmd jobscheduler run -f $packageName $jobId 2>$null | Out-Null
    }
}

function Wait-ForOfflineWritesSynced {
    param(
        [string]$AccessToken,
        [string]$CaseId,
        [string]$TaskId,
        [string[]]$BeforeCallLogIds,
        [string[]]$BeforeVitalIds,
        [int]$TimeoutSeconds = 150
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $detail = Get-CaseDetailFromApi -AccessToken $AccessToken -CaseId $CaseId
        $task = @($detail.tasks | Where-Object { [string]$_.id -eq $TaskId } | Select-Object -First 1)
        $taskSynced = $task.Count -gt 0 -and ([string]$task[0].status).ToUpperInvariant() -eq "COMPLETED"
        $newCallLog = @($detail.call_logs | Where-Object { $BeforeCallLogIds -notcontains [string]$_.id }).Count -gt 0
        $newVital = @($detail.vitals | Where-Object { $BeforeVitalIds -notcontains [string]$_.id }).Count -gt 0
        if ($taskSynced -and $newCallLog -and $newVital) {
            return $detail
        }
        if ($serial) {
            Invoke-WorkManagerJobs -DeviceSerial $serial
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for offline writes to sync for case $CaseId."
}

function Get-PatternDotCenters {
    param([string]$Xml)
    $pattern = "class=`"android\.(?:view\.View|widget\.Button)`"[^>]*clickable=`"true`"[^>]*bounds=`"\[(\d+),(\d+)\]\[(\d+),(\d+)\]`""
    $matches = [regex]::Matches($Xml, $pattern)
    $dots = @()
    foreach ($match in $matches) {
        $x1 = [int]$match.Groups[1].Value
        $y1 = [int]$match.Groups[2].Value
        $x2 = [int]$match.Groups[3].Value
        $y2 = [int]$match.Groups[4].Value
        $width = $x2 - $x1
        $height = $y2 - $y1
        if ($width -ge 100 -and $width -le 220 -and $height -ge 100 -and $height -le 220 -and $y1 -ge 500 -and $y2 -le 1400) {
            $dots += [pscustomobject]@{
                X = [int](($x1 + $x2) / 2)
                Y = [int](($y1 + $y2) / 2)
            }
        }
    }
    @($dots | Sort-Object Y, X | Select-Object -First 9)
}

function Set-PatternLock {
    param([string]$DeviceSerial)
    $xml = Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Set pattern") -TimeoutSeconds 60
    Enter-SmokePattern -DeviceSerial $DeviceSerial -Xml $xml
    Save-DeviceState -DeviceSerial $DeviceSerial -Name "03-pattern-selected"
    Tap-Text -DeviceSerial $DeviceSerial -Text "Save"
    Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Pattern saved") -TimeoutSeconds 20 | Out-Null
    Tap-Text -DeviceSerial $DeviceSerial -Text "Continue"
}

function Enter-SmokePattern {
    param(
        [string]$DeviceSerial,
        [string]$Xml
    )
    $dots = Get-PatternDotCenters -Xml $xml
    if ($dots.Count -lt 6) {
        throw "Could not locate pattern dots."
    }
    foreach ($index in @(0, 1, 2, 5)) {
        adb -s $DeviceSerial shell input tap $dots[$index].X $dots[$index].Y | Out-Null
        Start-Sleep -Milliseconds 250
    }
}

function Verify-PatternUnlockAfterRelaunch {
    param([string]$DeviceSerial)
    adb -s $DeviceSerial shell am force-stop $packageName | Out-Null
    Start-Sleep -Seconds 2
    Start-AppAndWait -DeviceSerial $DeviceSerial -MaxAttempts 3
    $lockXml = Wait-ForText -DeviceSerial $DeviceSerial -Texts @("MEDTRACK locked", "Pattern") -TimeoutSeconds 60
    Save-DeviceState -DeviceSerial $DeviceSerial -Name "05-lock-screen-after-relaunch"
    Enter-SmokePattern -DeviceSerial $DeviceSerial -Xml $lockXml
    Save-DeviceState -DeviceSerial $DeviceSerial -Name "05-pattern-unlock-selected"
    Tap-TextOccurrence -DeviceSerial $DeviceSerial -Text "Unlock" -Occurrence Last
    $unlockedXml = Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Search patient") -TimeoutSeconds 60
    Save-DeviceState -DeviceSerial $DeviceSerial -Name "05-pattern-unlocked-home"
    [pscustomobject]@{
        LockXml = $lockXml
        UnlockedXml = $unlockedXml
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
    $deepLinkCaseId = Get-SmokeCaseId -Username $Username -Password $Password
    Write-Step "Notification deep-link case id: $deepLinkCaseId"

    if ((Get-ListeningPortPids -Port 3899).Count -eq 0) {
        $dashboardCmd = "C:\Users\prave\Desktop\dashboard.cmd"
        if (Test-Path $dashboardCmd) {
            Write-Step "Starting Local Server Dashboard"
            $startedDashboard = $true
            Start-Process -FilePath $dashboardCmd -WindowStyle Hidden
        }
    }
    $snapshotPath = Join-Path $EvidenceDir "dashboard-snapshot.json"
    $deadline = (Get-Date).AddSeconds(45)
    do {
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:3899/api/snapshot" -TimeoutSec 10 |
                ConvertTo-Json -Depth 8 |
                Set-Content -Path $snapshotPath
            break
        }
        catch {
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $deadline)
    if (-not (Test-Path $snapshotPath)) {
        throw "Local Server Dashboard did not return a snapshot."
    }

    if (-not $NoBuild) {
        Write-Step "Building debug APK"
        Invoke-ProcessLogged `
            -Name "gradle-assemble-debug" `
            -WorkingDirectory $androidRoot `
            -FilePath (Join-Path $androidRoot "gradlew.bat") `
            -Arguments @("--no-daemon", ":app:assembleDebug", "-PMEDTRACK_API_BASE_URL=$ApiBaseUrl")
    }
    if (-not (Test-Path $apkPath)) {
        throw "APK not found at $apkPath"
    }

    $devices = @(Get-AdbDeviceSerials)
    if ($RequirePhysicalDevice) {
        $physicalDevices = @($devices | Where-Object { $_ -notlike "emulator-*" })
        if ($physicalDevices.Count -eq 0) {
            throw "No physical Android device is attached. Connect a phone with USB debugging enabled, then rerun without relying on an emulator."
        }
        $serial = $physicalDevices[0]
        Write-Step "Using physical Android device $serial"
    }
    elseif ($devices.Count -eq 0) {
        if (-not (Test-Path $emulatorExe)) {
            throw "emulator.exe not found at $emulatorExe"
        }
        Write-Step "Starting AVD $AvdName"
        $startedEmulator = $true
        $emulatorStdout = Join-Path $EvidenceDir "emulator.stdout.log"
        $emulatorStderr = Join-Path $EvidenceDir "emulator.stderr.log"
        Start-Process -FilePath $emulatorExe -ArgumentList @("-avd", $AvdName, "-no-window", "-no-snapshot-save", "-gpu", "swiftshader_indirect") -RedirectStandardOutput $emulatorStdout -RedirectStandardError $emulatorStderr -WindowStyle Hidden
        $serial = Wait-ForDevice -TimeoutSeconds 240
    }
    else {
        $serial = $devices[0]
        Write-Step "Reusing Android device $serial"
    }
    Wait-ForBoot -DeviceSerial $serial -TimeoutSeconds 240
    Unlock-DeviceIfNeeded -DeviceSerial $serial
    Wait-ForHomeReady -DeviceSerial $serial -TimeoutSeconds 120

    if ($UseAdbReverse) {
        Write-Step "Mapping device localhost:8000 to host Test NNH server with adb reverse"
        Invoke-ProcessLogged `
            -Name "adb-reverse-8000" `
            -FilePath "adb" `
            -Arguments @("-s", $serial, "reverse", "tcp:8000", "tcp:8000")
        $adbReverseEnabled = $true
    }

    Write-Step "Installing app on $serial"
    Invoke-ProcessLogged `
        -Name "adb-install" `
        -FilePath "adb" `
        -Arguments @("-s", $serial, "install", "-r", "-d", $apkPath)
    adb -s $serial shell pm clear $packageName | Out-Null
    Start-AppAndWait -DeviceSerial $serial -MaxAttempts 4

    Wait-ForText -DeviceSerial $serial -Texts @("Staff login", "Username") -TimeoutSeconds 60 | Out-Null
    Save-DeviceState -DeviceSerial $serial -Name "01-login"

    Tap-Text -DeviceSerial $serial -Text "Username"
    Start-Sleep -Milliseconds 600
    Invoke-AdbTextInput -DeviceSerial $serial -Value $Username
    Tap-Text -DeviceSerial $serial -Text "Password"
    Start-Sleep -Milliseconds 600
    Invoke-AdbTextInput -DeviceSerial $serial -Value $Password
    Tap-Text -DeviceSerial $serial -Text "Continue"

    $postLoginXml = Wait-ForText -DeviceSerial $serial -Texts @("Set pattern", "Search patient") -TimeoutSeconds 90
    Save-DeviceState -DeviceSerial $serial -Name "02-post-login"
    $biometricAvailabilityText = ""
    if ($postLoginXml -like "*Biometric unlock is not available on this device*") {
        $biometricAvailabilityText = "not_available"
    }
    elseif ($postLoginXml -like "*No biometric is enrolled on this device*") {
        $biometricAvailabilityText = "none_enrolled"
    }
    elseif ($postLoginXml -like "*Biometric hardware is currently unavailable*") {
        $biometricAvailabilityText = "hardware_unavailable"
    }
    elseif ($postLoginXml -like "*This device does not have biometric hardware*") {
        $biometricAvailabilityText = "no_hardware"
    }
    elseif ($postLoginXml -like "*Use device biometric unlock when available*") {
        $biometricAvailabilityText = "available"
    }
    elseif ($postLoginXml -like "*Biometric unlock is enabled*") {
        $biometricAvailabilityText = "enabled"
    }
    if ($postLoginXml -like "*Set pattern*") {
        Set-PatternLock -DeviceSerial $serial
    }

    Start-Sleep -Seconds 2
    if (Try-TapText -DeviceSerial $serial -Text "Allow") {
        Start-Sleep -Seconds 2
        Save-DeviceState -DeviceSerial $serial -Name "04-notification-allowed"
    }

    Wait-ForText -DeviceSerial $serial -Texts @("Search patient") -TimeoutSeconds 90 | Out-Null
    Save-DeviceState -DeviceSerial $serial -Name "05-home"
    $patternUnlock = Verify-PatternUnlockAfterRelaunch -DeviceSerial $serial

    Tap-ContentDescription -DeviceSerial $serial -ContentDescription "Filters"
    Wait-ForText -DeviceSerial $serial -Texts @("Scope") -TimeoutSeconds 30 | Out-Null
    Tap-Text -DeviceSerial $serial -Text "All visible"
    Tap-Text -DeviceSerial $serial -Text "Apply"
    Wait-ForText -DeviceSerial $serial -Texts @("Search patient") -TimeoutSeconds 60 | Out-Null
    Start-Sleep -Seconds 2
    Tap-Text -DeviceSerial $serial -Text "Overdue"
    $overdueXml = Wait-ForNonEmptyInbox -DeviceSerial $serial -TimeoutSeconds 90
    Save-DeviceState -DeviceSerial $serial -Name "06-overdue"

    $homeXml = Get-UiXml -DeviceSerial $serial
    $checks = [ordered]@{
        hasInbox = $homeXml -like "*Search patient*"
        hasSearch = $homeXml -like "*Search*"
        hasToday = $homeXml -like "*Today*"
        hasOverdue = $homeXml -like "*Overdue*"
        hasPatientRows = $overdueXml -notlike "*No patients in this view*"
        hasBottomNavigationOnHome = $homeXml -like "*Home*" -and $homeXml -like "*Cases*" -and $homeXml -like "*Calls*" -and $homeXml -like "*Me*"
        hasBiometricAvailabilityState = $postLoginXml -like "*Biometric*" -and $biometricAvailabilityText -ne ""
        hasPatternRelockScreen = $patternUnlock.LockXml -like "*MEDTRACK locked*" -and $patternUnlock.LockXml -like "*Pattern*"
        hasPatternUnlockRestoredSession = $patternUnlock.UnlockedXml -like "*Search patient*"
    }
    if (-not ($checks.hasInbox -and $checks.hasSearch -and $checks.hasToday -and $checks.hasOverdue -and $checks.hasPatientRows -and $checks.hasBottomNavigationOnHome -and $checks.hasBiometricAvailabilityState -and $checks.hasPatternRelockScreen -and $checks.hasPatternUnlockRestoredSession)) {
        throw "Home smoke checks failed: $($checks | ConvertTo-Json -Compress)"
    }

    Write-Step "Verifying red flag reasons sheet"
    if (-not (Reveal-TextWithHorizontalSwipe -DeviceSerial $serial -Text "Red" -AnchorText "Awaiting")) {
        throw "Could not reveal Red bucket chip."
    }
    Tap-Text -DeviceSerial $serial -Text "Red"
    $redXml = Wait-ForNonEmptyInbox -DeviceSerial $serial -TimeoutSeconds 90
    Save-DeviceState -DeviceSerial $serial -Name "06-red-flag-list"
    $checks["hasRedFlagIcon"] = $redXml -like "*Red flag*"
    if (-not $checks.hasRedFlagIcon) {
        throw "Red flag list check failed: $($checks | ConvertTo-Json -Compress)"
    }
    Tap-ContentDescription -DeviceSerial $serial -ContentDescription "Red flag"
    $riskReasonsXml = Wait-ForText -DeviceSerial $serial -Texts @("Risk reasons") -TimeoutSeconds 30
    Save-DeviceState -DeviceSerial $serial -Name "06-red-flag-sheet"
    Tap-Text -DeviceSerial $serial -Text "Close"
    Wait-ForText -DeviceSerial $serial -Texts @("Search patient") -TimeoutSeconds 30 | Out-Null
    $checks["hasRiskReasonsSheet"] = $riskReasonsXml -like "*Risk reasons*"

    Write-Step "Verifying category and sub-category filters"
    Tap-ContentDescription -DeviceSerial $serial -ContentDescription "Filters"
    Wait-ForText -DeviceSerial $serial -Texts @("Category") -TimeoutSeconds 30 | Out-Null
    Tap-ContentDescription -DeviceSerial $serial -ContentDescription "Category filter Medicine"
    $filterSheetXml = Wait-ForText -DeviceSerial $serial -Texts @("General Medicine") -TimeoutSeconds 30
    Tap-Text -DeviceSerial $serial -Text "Apply"
    $categoryFilterXml = Wait-ForNonEmptyInbox -DeviceSerial $serial -TimeoutSeconds 90
    Save-DeviceState -DeviceSerial $serial -Name "06-filter-medicine"
    $checks["hasCategoryFilterSheet"] = $categoryFilterXml -like "*Medicine*"
    $checks["hasSubcategoryFilterSheet"] = $filterSheetXml -like "*General Medicine*"
    if (-not ($checks.hasCategoryFilterSheet -and $checks.hasSubcategoryFilterSheet)) {
        throw "Category/sub-category filter checks failed: $($checks | ConvertTo-Json -Compress)"
    }

    Tap-ContentDescription -DeviceSerial $serial -ContentDescription "Filters"
    Wait-ForText -DeviceSerial $serial -Texts @("Category") -TimeoutSeconds 30 | Out-Null
    Tap-ContentDescription -DeviceSerial $serial -ContentDescription "Category filter Medicine"
    Tap-Text -DeviceSerial $serial -Text "Apply"
    $overdueXml = Wait-ForNonEmptyInbox -DeviceSerial $serial -TimeoutSeconds 90
    Save-DeviceState -DeviceSerial $serial -Name "06-filter-cleared"

    Write-Step "Verifying inline card expansion and Open case action"
    Tap-FirstPatientRow -DeviceSerial $serial -MinY 650
    $expandedCardXml = Wait-ForText -DeviceSerial $serial -Texts @("Open case") -TimeoutSeconds 30
    Save-DeviceState -DeviceSerial $serial -Name "06-card-expanded"
    $checks["hasInlineExpandedCard"] = $expandedCardXml -like "*Open case*"
    $checks["hasOpenCaseAction"] = $expandedCardXml -like "*Open case*"
    if (-not ($checks.hasInlineExpandedCard -and $checks.hasOpenCaseAction)) {
        throw "Inline expanded-card checks failed: $($checks | ConvertTo-Json -Compress)"
    }
    Tap-FirstPatientRow -DeviceSerial $serial -MinY 650
    Start-Sleep -Seconds 1
    Save-DeviceState -DeviceSerial $serial -Name "06-card-collapsed-after-expand"

    Write-Step "Verifying home card swipe-left Call"
    $callSwipeRow = $null
    for ($rowIndex = 0; $rowIndex -lt 4; $rowIndex++) {
        Write-Step "Trying swipe-left Call on visible row $($rowIndex + 1)"
        Swipe-FirstPatientCard -DeviceSerial $serial -Direction Left -RowIndex $rowIndex | Out-Null
        if (Test-DialerVisibleWithin -DeviceSerial $serial -TimeoutSeconds 8) {
            $callSwipeRow = $rowIndex
            break
        }
        Save-DeviceState -DeviceSerial $serial -Name ("07-swipe-call-row{0}-stayed-home" -f ($rowIndex + 1))
    }
    if ($null -eq $callSwipeRow) {
        throw "Swipe-left Call did not open the dialer for any visible patient row."
    }
    Save-DeviceState -DeviceSerial $serial -Name "07-swipe-call-dialer"
    Invoke-ProcessLogged `
        -Name "adb-return-from-dialer" `
        -FilePath "adb" `
        -Arguments @("-s", $serial, "shell", "am", "start", "-W", "--activity-reorder-to-front", "-n", "$packageName/.MainActivity")
    $callOutcomeXml = Wait-ForText -DeviceSerial $serial -Texts @("Call outcome") -TimeoutSeconds 45
    Save-DeviceState -DeviceSerial $serial -Name "08-swipe-call-outcome"
    Tap-Text -DeviceSerial $serial -Text "No outcome"
    Wait-ForText -DeviceSerial $serial -Texts @("Search patient") -TimeoutSeconds 60 | Out-Null
    Save-DeviceState -DeviceSerial $serial -Name "09-swipe-call-returned"

    Write-Step "Verifying home card swipe-right Done"
    Wait-ForNonEmptyInbox -DeviceSerial $serial -TimeoutSeconds 60 | Out-Null
    Swipe-FirstPatientCard -DeviceSerial $serial -Direction Right | Out-Null
    $doneSnackbarXml = Wait-ForText -DeviceSerial $serial -Texts @("Undo", "done?") -TimeoutSeconds 25
    Save-DeviceState -DeviceSerial $serial -Name "10-swipe-done-snackbar"
    $doneResultXml = Wait-ForText -DeviceSerial $serial -Texts @("Task marked as completed.", "Task completed.", "Task completion queued for sync.", "Server version kept.") -TimeoutSeconds 60
    Save-DeviceState -DeviceSerial $serial -Name "11-swipe-done-completed"

    $offlineSummary = $null
    if ($OfflineWrites) {
        Write-Step "Verifying offline queued writes"
        $offlineAccessToken = Get-MobileApiToken -Username $Username -Password $Password
        $offlineTarget = Get-OfflineWriteTarget -AccessToken $offlineAccessToken
        $offlineBefore = Get-CaseDetailFromApi -AccessToken $offlineAccessToken -CaseId $offlineTarget.Id
        $beforeCallLogIds = Get-ObjectIds -Items @($offlineBefore.call_logs)
        $beforeVitalIds = Get-ObjectIds -Items @($offlineBefore.vitals)
        Write-Step "Offline target case $($offlineTarget.Id), task $($offlineTarget.TaskId), query $($offlineTarget.Query)"

        Invoke-ProcessLogged `
            -Name "adb-offline-cache-detail" `
            -FilePath "adb" `
            -Arguments @(
                "-s", $serial,
                "shell", "am", "start", "-W",
                "-n", "$packageName/.MainActivity",
                "--ez", "from_notification", "true",
                "--es", "case_id", $offlineTarget.Id
        )
        Wait-ForText -DeviceSerial $serial -Texts @("Tasks", "Vitals history") -TimeoutSeconds 60 | Out-Null
        Save-DeviceState -DeviceSerial $serial -Name "12-offline-cache-detail"
        Return-ToHome -DeviceSerial $serial | Out-Null
        Tap-ContentDescription -DeviceSerial $serial -ContentDescription "Filters"
        Wait-ForText -DeviceSerial $serial -Texts @("Scope") -TimeoutSeconds 30 | Out-Null
        Tap-Text -DeviceSerial $serial -Text "All visible"
        Tap-Text -DeviceSerial $serial -Text "Apply"
        Wait-ForText -DeviceSerial $serial -Texts @("Search patient") -TimeoutSeconds 60 | Out-Null
        Start-Sleep -Seconds 1
        if ($offlineTarget.Bucket) {
            Start-Sleep -Seconds 1
            $bucketLabel = (Get-Culture).TextInfo.ToTitleCase($offlineTarget.Bucket)
            Tap-Text -DeviceSerial $serial -Text $bucketLabel
            Start-Sleep -Seconds 2
        }
        if (-not (Try-TapText -DeviceSerial $serial -Text "Search patient, UHID, phone")) {
            Tap-Text -DeviceSerial $serial -Text "Search"
        }
        Invoke-AdbTextInput -DeviceSerial $serial -Value $offlineTarget.Uhid
        Wait-ForNonEmptyInbox -DeviceSerial $serial -TimeoutSeconds 60 | Out-Null
        adb -s $serial shell input keyevent 4 | Out-Null
        Start-Sleep -Seconds 1
        Save-DeviceState -DeviceSerial $serial -Name "13-offline-target-home"

        Set-EmulatorNetwork -DeviceSerial $serial -Enabled $false
        Save-DeviceState -DeviceSerial $serial -Name "14-offline-network-disabled"

        Swipe-FirstPatientCard -DeviceSerial $serial -Direction Right | Out-Null
        $offlineTaskSnackbarXml = Wait-ForText -DeviceSerial $serial -Texts @("Undo", "done?") -TimeoutSeconds 25
        Save-DeviceState -DeviceSerial $serial -Name "15-offline-task-snackbar"
        $offlineTaskQueuedXml = Wait-ForText -DeviceSerial $serial -Texts @("Task completion queued for sync.") -TimeoutSeconds 75
        Save-DeviceState -DeviceSerial $serial -Name "16-offline-task-queued"

        Invoke-ProcessLogged `
            -Name "adb-offline-open-detail-for-call" `
            -FilePath "adb" `
            -Arguments @(
                "-s", $serial,
                "shell", "am", "start", "-W",
                "-n", "$packageName/.MainActivity",
                "--ez", "from_notification", "true",
                "--es", "case_id", $offlineTarget.Id
            )
        Wait-ForText -DeviceSerial $serial -Texts @("Tasks", "Vitals history") -TimeoutSeconds 60 | Out-Null
        Save-DeviceState -DeviceSerial $serial -Name "17-offline-detail-before-call"
        Tap-Text -DeviceSerial $serial -Text "Call"
        if (-not (Test-DialerVisibleWithin -DeviceSerial $serial -TimeoutSeconds 20)) {
            throw "Offline detail Call did not open the dialer for target case $($offlineTarget.Id)."
        }
        Save-DeviceState -DeviceSerial $serial -Name "18-offline-call-dialer"
        Invoke-ProcessLogged `
            -Name "adb-offline-return-from-dialer" `
            -FilePath "adb" `
            -Arguments @("-s", $serial, "shell", "am", "start", "-W", "--activity-reorder-to-front", "-n", "$packageName/.MainActivity")
        Wait-ForText -DeviceSerial $serial -Texts @("Call outcome") -TimeoutSeconds 45 | Out-Null
        Save-DeviceState -DeviceSerial $serial -Name "19-offline-call-outcome"
        Tap-Text -DeviceSerial $serial -Text "No outcome"
        $offlineCallQueuedXml = Wait-ForText -DeviceSerial $serial -Texts @("Call outcome queued for sync.") -TimeoutSeconds 45
        Save-DeviceState -DeviceSerial $serial -Name "20-offline-call-queued"

        Invoke-ProcessLogged `
            -Name "adb-offline-open-detail" `
            -FilePath "adb" `
            -Arguments @(
                "-s", $serial,
                "shell", "am", "start", "-W",
                "-n", "$packageName/.MainActivity",
                "--ez", "from_notification", "true",
                "--es", "case_id", $offlineTarget.Id
            )
        Wait-ForText -DeviceSerial $serial -Texts @("Tasks", "Vitals history") -TimeoutSeconds 60 | Out-Null
        Save-DeviceState -DeviceSerial $serial -Name "21-offline-detail"
        Tap-Text -DeviceSerial $serial -Text "Add"
        Wait-ForText -DeviceSerial $serial -Texts @("Add vitals") -TimeoutSeconds 30 | Out-Null
        Tap-Text -DeviceSerial $serial -Text "Pulse"
        Invoke-AdbTextInput -DeviceSerial $serial -Value "86"
        Tap-Text -DeviceSerial $serial -Text "SpO2"
        Invoke-AdbTextInput -DeviceSerial $serial -Value "98"
        Tap-Text -DeviceSerial $serial -Text "Save"
        $offlineVitalsQueuedXml = Wait-ForText -DeviceSerial $serial -Texts @("Vitals queued for sync.") -TimeoutSeconds 45
        Save-DeviceState -DeviceSerial $serial -Name "22-offline-vitals-queued"

        Set-EmulatorNetwork -DeviceSerial $serial -Enabled $true
        Start-AppAndWait -DeviceSerial $serial -MaxAttempts 2
        Invoke-WorkManagerJobs -DeviceSerial $serial
        $offlineSynced = Wait-ForOfflineWritesSynced `
            -AccessToken $offlineAccessToken `
            -CaseId $offlineTarget.Id `
            -TaskId $offlineTarget.TaskId `
            -BeforeCallLogIds $beforeCallLogIds `
            -BeforeVitalIds $beforeVitalIds
        Save-DeviceState -DeviceSerial $serial -Name "23-offline-synced"

        $checks["hasOfflineTaskSnackbar"] = $offlineTaskSnackbarXml -like "*Undo*" -or $offlineTaskSnackbarXml -like "*done?*"
        $checks["hasOfflineTaskQueued"] = $offlineTaskQueuedXml -like "*Task completion queued for sync.*"
        $checks["hasOfflineCallQueued"] = $offlineCallQueuedXml -like "*Call outcome queued for sync.*"
        $checks["hasOfflineVitalsQueued"] = $offlineVitalsQueuedXml -like "*Vitals queued for sync.*"
        $checks["hasOfflineWritesSynced"] = $true
        $offlineSummary = [ordered]@{
            caseId = $offlineTarget.Id
            taskId = $offlineTarget.TaskId
            uhid = $offlineTarget.Uhid
            targetQuery = $offlineTarget.Query
            beforeCallLogCount = @($offlineBefore.call_logs).Count
            afterCallLogCount = @($offlineSynced.call_logs).Count
            beforeVitalCount = @($offlineBefore.vitals).Count
            afterVitalCount = @($offlineSynced.vitals).Count
        }
    }

    Write-Step "Opening case detail and adding vitals"
    Invoke-ProcessLogged `
        -Name "adb-open-case-detail-for-vitals" `
        -FilePath "adb" `
        -Arguments @(
            "-s", $serial,
            "shell", "am", "start", "-W",
            "-n", "$packageName/.MainActivity",
            "--ez", "from_notification", "true",
            "--es", "case_id", $deepLinkCaseId
        )
    $caseDetailXml = Wait-ForText -DeviceSerial $serial -Texts @("Tasks", "Vitals history") -TimeoutSeconds 60
    Save-DeviceState -DeviceSerial $serial -Name "13-case-detail"

    Tap-Text -DeviceSerial $serial -Text "Add"
    Wait-ForText -DeviceSerial $serial -Texts @("Add vitals") -TimeoutSeconds 30 | Out-Null
    Save-DeviceState -DeviceSerial $serial -Name "14-add-vitals"
    Tap-Text -DeviceSerial $serial -Text "Pulse"
    Invoke-AdbTextInput -DeviceSerial $serial -Value "82"
    Tap-Text -DeviceSerial $serial -Text "SpO2"
    Invoke-AdbTextInput -DeviceSerial $serial -Value "97"
    Tap-Text -DeviceSerial $serial -Text "Save"
    $vitalsXml = Wait-ForText -DeviceSerial $serial -Texts @("Vitals recorded.", "PR 82", "SpO2 97") -TimeoutSeconds 60
    Save-DeviceState -DeviceSerial $serial -Name "15-vitals-recorded"

    Write-Step "Opening notifications"
    Return-ToHome -DeviceSerial $serial | Out-Null
    Tap-ContentDescription -DeviceSerial $serial -ContentDescription "Alerts"
    $notificationsXml = Wait-ForText -DeviceSerial $serial -Texts @("Notifications") -TimeoutSeconds 30
    Save-DeviceState -DeviceSerial $serial -Name "16-notifications"

    Write-Step "Simulating notification deep link"
    Invoke-ProcessLogged `
        -Name "adb-notification-deeplink" `
        -FilePath "adb" `
        -Arguments @(
            "-s", $serial,
            "shell", "am", "start", "-W",
            "-n", "$packageName/.MainActivity",
            "--ez", "from_notification", "true",
            "--es", "case_id", $deepLinkCaseId
    )
    $notificationDetailXml = Wait-ForText -DeviceSerial $serial -Texts @("Tasks", "Vitals history") -TimeoutSeconds 60
    Save-DeviceState -DeviceSerial $serial -Name "17-notification-deeplink"

    $checks["hasSwipeCallDialer"] = $true
    $checks["hasSwipeCallOutcomeSheet"] = $callOutcomeXml -like "*Call outcome*"
    $checks["hasSwipeDoneSnackbar"] = $doneSnackbarXml -like "*Undo*" -or $doneSnackbarXml -like "*done?*"
    $checks["hasSwipeDoneResult"] = $doneResultXml -like "*Task marked as completed.*" -or $doneResultXml -like "*Task completed.*" -or $doneResultXml -like "*Task completion queued for sync.*" -or $doneResultXml -like "*Server version kept.*"
    $checks["hasCaseDetail"] = $caseDetailXml -like "*Tasks*" -and $caseDetailXml -like "*Vitals history*"
    $checks["hasVitalsRecorded"] = $vitalsXml -like "*Vitals recorded.*" -or $vitalsXml -like "*PR 82*" -or $vitalsXml -like "*SpO2 97*"
    $checks["hasNotificationsScreen"] = $notificationsXml -like "*Notifications*"
    $checks["hasNotificationDeepLink"] = $notificationDetailXml -like "*Tasks*" -and $notificationDetailXml -like "*Vitals history*"
    $offlineChecksPass = (-not $OfflineWrites) -or (
        $checks.hasOfflineTaskSnackbar -and
        $checks.hasOfflineTaskQueued -and
        $checks.hasOfflineCallQueued -and
        $checks.hasOfflineVitalsQueued -and
        $checks.hasOfflineWritesSynced
    )
    if (-not ($checks.hasPatternRelockScreen -and $checks.hasPatternUnlockRestoredSession -and $checks.hasBottomNavigationOnHome -and $checks.hasCategoryFilterSheet -and $checks.hasSubcategoryFilterSheet -and $checks.hasInlineExpandedCard -and $checks.hasOpenCaseAction -and $checks.hasRiskReasonsSheet -and $checks.hasSwipeCallDialer -and $checks.hasSwipeCallOutcomeSheet -and $checks.hasSwipeDoneSnackbar -and $checks.hasSwipeDoneResult -and $checks.hasCaseDetail -and $checks.hasVitalsRecorded -and $checks.hasNotificationsScreen -and $checks.hasNotificationDeepLink -and $offlineChecksPass)) {
        throw "Workflow smoke checks failed: $($checks | ConvertTo-Json -Compress)"
    }

    $summary = [ordered]@{
        passed = $true
        avdName = $AvdName
        serial = $serial
        requirePhysicalDevice = [bool]$RequirePhysicalDevice
        packageName = $packageName
        apiBaseUrl = $ApiBaseUrl
        adbReverse = [bool]$UseAdbReverse
        apk = $apkPath
        apkSha256 = (Get-FileHash -Path $apkPath -Algorithm SHA256).Hash
        notificationDeepLinkCaseId = $deepLinkCaseId
        biometricAvailability = $biometricAvailabilityText
        offlineWrites = $offlineSummary
        checks = $checks
        evidenceDir = $EvidenceDir
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $EvidenceDir "summary.json")
    Write-Step "PASS"
}
finally {
    $cleanup = [ordered]@{}
    if ($networkDisabled -and $serial) {
        try {
            Write-Step "Restoring emulator network"
            Set-EmulatorNetwork -DeviceSerial $serial -Enabled $true
        }
        catch {
            $cleanup["networkRestoreError"] = $_.Exception.Message
        }
    }
    if ($serial) {
        try {
            Save-DeviceState -DeviceSerial $serial -Name "final-state"
        }
        catch {
            $_.Exception.Message | Set-Content -Path (Join-Path $EvidenceDir "final-state-error.txt")
        }
        try {
            adb -s $serial logcat -d -t 4000 2>$null | Set-Content -Path (Join-Path $EvidenceDir "final-logcat.txt")
        }
        catch {
            $_.Exception.Message | Set-Content -Path (Join-Path $EvidenceDir "final-logcat-error.txt")
        }
    }
    if ($adbReverseEnabled -and $serial) {
        try {
            Write-Step "Removing adb reverse tcp:8000"
            adb -s $serial reverse --remove tcp:8000 2>$null | Out-Null
        }
        catch {
            $cleanup["adbReverseRemoveError"] = $_.Exception.Message
        }
    }
    if ($startedEmulator -and -not $KeepEmulator -and $serial) {
        Write-Step "Stopping emulator $serial"
        adb -s $serial emu kill 2>$null | Out-Null
        Start-Sleep -Seconds 5
    }
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
    if ($startedDashboard) {
        $dashboardPids = Get-ListeningPortPids -Port 3899
        foreach ($dashboardPid in $dashboardPids) {
            Stop-Process -Id $dashboardPid -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
    $cleanup["adbDevices"] = (adb devices | Out-String).Trim()
    $cleanup["port8000"] = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)
    $cleanup["port3899"] = @(Get-NetTCPConnection -State Listen -LocalPort 3899 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)
    $cleanup | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $EvidenceDir "cleanup-status.json")
}
