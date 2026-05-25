[CmdletBinding()]
param(
    [string]$AvdName = "MarkUS_Latest_API37",
    [string]$Username = "admin",
    [string]$Password = "pass",
    [string]$EvidenceDir = "",
    [string]$EnrollPin = "1234",
    [switch]$NoBuild,
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
    $EvidenceDir = Join-Path $repoRoot "output\android-biometric-smoke-$timestamp"
}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$startedServer = $false
$startedDashboard = $false
$startedEmulator = $false
$serial = $null

function Write-Step {
    param([string]$Message)
    Write-Host "[biometric] $Message"
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
    $stdoutPath = Join-Path $EvidenceDir "$Name.stdout.log"
    $stderrPath = Join-Path $EvidenceDir "$Name.stderr.log"
    $logPath = Join-Path $EvidenceDir "$Name.log"
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
    $script:LastExitCode = $process.ExitCode
}

function Get-ListeningPortPids {
    param([int]$Port)
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 90
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
    param([int]$TimeoutSeconds = 240)
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
        [int]$TimeoutSeconds = 240
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $booted = (adb -s $DeviceSerial shell getprop sys.boot_completed 2>$null).Trim()
        if ($booted -eq "1") {
            adb -s $DeviceSerial shell input keyevent 224 | Out-Null
            adb -s $DeviceSerial shell wm dismiss-keyguard | Out-Null
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
    $lockDisabled = (adb -s $DeviceSerial shell locksettings get-disabled 2>$null | Out-String).Trim()
    if ($lockDisabled -notmatch "true") {
        Invoke-AdbTextInput -DeviceSerial $DeviceSerial -Value $EnrollPin
        adb -s $DeviceSerial shell input keyevent 66 | Out-Null
        Start-Sleep -Seconds 2
        adb -s $DeviceSerial shell wm dismiss-keyguard | Out-Null
    }
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
        [int]$Attempts = 8
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $raw = (adb -s $DeviceSerial exec-out uiautomator dump /dev/tty 2>$null | Out-String)
        $xml = Normalize-UiXml -Raw $raw
        if ($xml -like "*<hierarchy*") {
            return $xml
        }
        Start-Sleep -Milliseconds 600
    }
    throw "Could not dump UI hierarchy."
}

function Save-DeviceState {
    param(
        [string]$DeviceSerial,
        [string]$Name
    )
    $xml = Get-UiXml -DeviceSerial $DeviceSerial
    Set-Content -Path (Join-Path $EvidenceDir "$Name.xml") -Value $xml
    return $xml
}

function Find-TextCenter {
    param(
        [string]$Xml,
        [string]$Text
    )
    $escaped = [regex]::Escape($Text)
    $patterns = @(
        "text=`"$escaped`"[^>]*bounds=`"\[(\d+),(\d+)\]\[(\d+),(\d+)\]`"",
        "content-desc=`"$escaped`"[^>]*bounds=`"\[(\d+),(\d+)\]\[(\d+),(\d+)\]`""
    )
    foreach ($pattern in $patterns) {
        $match = [regex]::Match($Xml, $pattern)
        if ($match.Success) {
            return [pscustomobject]@{
                X = [int](([int]$match.Groups[1].Value + [int]$match.Groups[3].Value) / 2)
                Y = [int](([int]$match.Groups[2].Value + [int]$match.Groups[4].Value) / 2)
            }
        }
    }
    return $null
}

function Try-TapText {
    param(
        [string]$DeviceSerial,
        [string]$Text,
        [int]$Attempts = 4
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $xml = Get-UiXml -DeviceSerial $DeviceSerial
        $center = Find-TextCenter -Xml $xml -Text $Text
        if ($center) {
            adb -s $DeviceSerial shell input tap $center.X $center.Y | Out-Null
            Start-Sleep -Seconds 2
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Tap-Text {
    param(
        [string]$DeviceSerial,
        [string]$Text
    )
    if (-not (Try-TapText -DeviceSerial $DeviceSerial -Text $Text)) {
        throw "Could not find text '$Text'."
    }
}

function Wait-ForText {
    param(
        [string]$DeviceSerial,
        [string[]]$Texts,
        [int]$TimeoutSeconds = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $xml = Get-UiXml -DeviceSerial $DeviceSerial
        foreach ($text in $Texts) {
            if ($xml -like "*$text*") {
                return $xml
            }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for one of: $($Texts -join ', ')"
}

function Invoke-AdbTextInput {
    param(
        [string]$DeviceSerial,
        [string]$Value
    )
    foreach ($char in $Value.ToCharArray()) {
        adb -s $DeviceSerial shell input text ([string]$char) | Out-Null
        Start-Sleep -Milliseconds 120
    }
}

function Test-FingerprintEnrolled {
    param([string]$DeviceSerial)
    $dump = (adb -s $DeviceSerial shell dumpsys fingerprint 2>$null | Out-String)
    Set-Content -Path (Join-Path $EvidenceDir "fingerprint-dumpsys.txt") -Value $dump
    return $dump -match '"count":\s*[1-9]'
}

function Complete-FingerprintEnrollment {
    param([string]$DeviceSerial)
    if (Test-FingerprintEnrolled -DeviceSerial $DeviceSerial) {
        return
    }

    Write-Step "Enrolling emulator fingerprint"
    adb -s $DeviceSerial shell am start -a android.settings.BIOMETRIC_ENROLL | Out-Null
    $xml = Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Choose a screen lock", "Set up Pixel Imprint", "Touch the sensor") -TimeoutSeconds 60
    Set-Content -Path (Join-Path $EvidenceDir "enroll-01-start.xml") -Value $xml

    if ($xml -like "*Choose a screen lock*") {
        Tap-Text -DeviceSerial $DeviceSerial -Text "Pixel Imprint + PIN"
        Wait-ForText -DeviceSerial $DeviceSerial -Texts @("PIN area") -TimeoutSeconds 30 | Out-Null
        Invoke-AdbTextInput -DeviceSerial $DeviceSerial -Value $EnrollPin
        Tap-Text -DeviceSerial $DeviceSerial -Text "NEXT"
        Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Re-enter your PIN") -TimeoutSeconds 30 | Out-Null
        Invoke-AdbTextInput -DeviceSerial $DeviceSerial -Value $EnrollPin
        Tap-Text -DeviceSerial $DeviceSerial -Text "CONFIRM"
        Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Lock screen") -TimeoutSeconds 30 | Out-Null
        Tap-Text -DeviceSerial $DeviceSerial -Text "Done"
    }

    $xml = Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Set up Pixel Imprint", "Touch the sensor") -TimeoutSeconds 60
    Set-Content -Path (Join-Path $EvidenceDir "enroll-02-pixel-imprint.xml") -Value $xml
    if ($xml -like "*Set up Pixel Imprint*") {
        if (Try-TapText -DeviceSerial $DeviceSerial -Text "MORE") {
            Start-Sleep -Seconds 1
        }
        if (Try-TapText -DeviceSerial $DeviceSerial -Text "I AGREE") {
            Start-Sleep -Seconds 2
        }
    }

    Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Touch the sensor") -TimeoutSeconds 60 | Out-Null
    1..10 | ForEach-Object {
        adb -s $DeviceSerial emu finger touch 1 | Out-Null
        Start-Sleep -Milliseconds 800
    }
    $doneXml = Wait-ForText -DeviceSerial $DeviceSerial -Texts @("Fingerprint added", "DONE") -TimeoutSeconds 60
    Set-Content -Path (Join-Path $EvidenceDir "enroll-03-added.xml") -Value $doneXml
    Try-TapText -DeviceSerial $DeviceSerial -Text "DONE" | Out-Null
    if (-not (Test-FingerprintEnrolled -DeviceSerial $DeviceSerial)) {
        throw "Fingerprint enrollment did not complete."
    }
}

function Start-AppAndWait {
    param([string]$DeviceSerial)
    adb -s $DeviceSerial shell am start -W -n "$packageName/.MainActivity" | Out-Null
    Start-Sleep -Seconds 5
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
            -Arguments @("--no-daemon", ":app:assembleDebug")
    }
    if (-not (Test-Path $apkPath)) {
        throw "APK not found at $apkPath"
    }

    $devices = @(Get-AdbDeviceSerials)
    if ($devices.Count -eq 0) {
        if (-not (Test-Path $emulatorExe)) {
            throw "emulator.exe not found at $emulatorExe"
        }
        Write-Step "Starting AVD $AvdName"
        $startedEmulator = $true
        Start-Process -FilePath $emulatorExe -ArgumentList @("-avd", $AvdName, "-no-window", "-no-snapshot-save", "-gpu", "swiftshader_indirect") -WindowStyle Hidden
        $serial = Wait-ForDevice -TimeoutSeconds 240
    }
    else {
        $serial = $devices[0]
        Write-Step "Reusing Android device $serial"
    }
    Wait-ForBoot -DeviceSerial $serial -TimeoutSeconds 240
    Unlock-DeviceIfNeeded -DeviceSerial $serial
    Complete-FingerprintEnrollment -DeviceSerial $serial

    Write-Step "Installing app"
    Invoke-ProcessLogged -Name "adb-uninstall" -FilePath "adb" -Arguments @("-s", $serial, "uninstall", $packageName) -AllowFailure
    Invoke-ProcessLogged -Name "adb-install" -FilePath "adb" -Arguments @("-s", $serial, "install", "-r", "-d", $apkPath)

    Start-AppAndWait -DeviceSerial $serial
    $loginXml = Wait-ForText -DeviceSerial $serial -Texts @("Username") -TimeoutSeconds 60
    Set-Content -Path (Join-Path $EvidenceDir "01-login.xml") -Value $loginXml
    Tap-Text -DeviceSerial $serial -Text "Username"
    Invoke-AdbTextInput -DeviceSerial $serial -Value $Username
    Tap-Text -DeviceSerial $serial -Text "Password"
    Invoke-AdbTextInput -DeviceSerial $serial -Value $Password
    Tap-Text -DeviceSerial $serial -Text "Continue"

    $setupXml = Wait-ForText -DeviceSerial $serial -Texts @("Set pattern", "Search patient") -TimeoutSeconds 90
    Set-Content -Path (Join-Path $EvidenceDir "02-lock-setup.xml") -Value $setupXml
    $biometricAvailable = $setupXml -like "*Use device biometric unlock when available*"
    if (-not $biometricAvailable) {
        throw "Biometric was not available on lock setup screen."
    }

    Tap-Text -DeviceSerial $serial -Text "Enable biometric"
    Start-Sleep -Seconds 2
    $promptXml = Save-DeviceState -DeviceSerial $serial -Name "03-enable-biometric-prompt"
    adb -s $serial emu finger touch 1 | Out-Null
    $enabledXml = Wait-ForText -DeviceSerial $serial -Texts @("Biometric unlock is enabled.") -TimeoutSeconds 60
    Set-Content -Path (Join-Path $EvidenceDir "04-biometric-enabled.xml") -Value $enabledXml
    Tap-Text -DeviceSerial $serial -Text "Continue"
    if (Try-TapText -DeviceSerial $serial -Text "Allow") {
        Start-Sleep -Seconds 1
    }
    Wait-ForText -DeviceSerial $serial -Texts @("Search patient") -TimeoutSeconds 90 | Out-Null

    adb -s $serial shell am force-stop $packageName | Out-Null
    Start-Sleep -Seconds 2
    Start-AppAndWait -DeviceSerial $serial
    $unlockXml = Wait-ForText -DeviceSerial $serial -Texts @("MEDTRACK locked", "Use biometric") -TimeoutSeconds 60
    Set-Content -Path (Join-Path $EvidenceDir "05-unlock-screen.xml") -Value $unlockXml
    Tap-Text -DeviceSerial $serial -Text "Use biometric"
    Start-Sleep -Seconds 2
    $unlockPromptXml = Save-DeviceState -DeviceSerial $serial -Name "06-unlock-biometric-prompt"
    adb -s $serial emu finger touch 1 | Out-Null
    $homeXml = Wait-ForText -DeviceSerial $serial -Texts @("Search patient") -TimeoutSeconds 60
    Set-Content -Path (Join-Path $EvidenceDir "07-biometric-unlocked-home.xml") -Value $homeXml

    $checks = [ordered]@{
        hasFingerprintEnrollment = Test-FingerprintEnrolled -DeviceSerial $serial
        hasBiometricAvailableOnSetup = $biometricAvailable
        hasEnablePrompt = $promptXml -like "*Unlock MEDTRACK*" -or $promptXml -like "*Use your device biometric*"
        hasBiometricEnabledMessage = $enabledXml -like "*Biometric unlock is enabled.*"
        hasUnlockScreenUseBiometric = $unlockXml -like "*Use biometric*"
        hasUnlockPrompt = $unlockPromptXml -like "*Unlock MEDTRACK*" -or $unlockPromptXml -like "*Use your device biometric*"
        hasBiometricUnlockRestoredHome = $homeXml -like "*Search patient*"
        hasDashboardDiscovery = Test-Path $snapshotPath
    }
    $passed = -not (@($checks.Values | Where-Object { $_ -ne $true }).Count -gt 0)
    $summary = [ordered]@{
        passed = $passed
        avdName = $AvdName
        deviceSerial = $serial
        apk = $apkPath
        apkSha256 = (Get-FileHash -Path $apkPath -Algorithm SHA256).Hash
        checks = $checks
        evidenceDir = $EvidenceDir
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $EvidenceDir "summary.json")
    if (-not $passed) {
        throw "Biometric smoke checks failed: $($checks | ConvertTo-Json -Compress)"
    }
    Write-Step "PASS"
    Write-Step "summary: $(Join-Path $EvidenceDir 'summary.json')"
}
finally {
    if ($startedServer -and -not $KeepServer) {
        Write-Step "Stopping Test NNH server"
        Invoke-ProcessLogged `
            -Name "test-nnh-stop" `
            -FilePath "powershell.exe" `
            -Arguments @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "local-dev\test-nnh-stop.ps1")) `
            -AllowFailure
    }
    if ($startedDashboard) {
        $dashboardPids = Get-ListeningPortPids -Port 3899
        foreach ($processId in $dashboardPids) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
    if ($startedEmulator -and -not $KeepEmulator -and $serial) {
        Write-Step "Stopping emulator"
        adb -s $serial emu kill 2>$null | Out-Null
    }
}
