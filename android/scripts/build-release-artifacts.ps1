[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$androidRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $androidRoot
$gradle = Join-Path $androidRoot 'gradlew.bat'
$versionPropertiesPath = Join-Path $androidRoot 'version.properties'
$buildRoot = Join-Path $androidRoot '.build\app\outputs'

$versionProperties = @{}
foreach ($line in Get-Content -LiteralPath $versionPropertiesPath) {
    if ($line -match '^([^#=]+)=(.*)$') {
        $versionProperties[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$versionName = $versionProperties['VERSION_NAME']
$versionCode = [int64]$versionProperties['VERSION_CODE']
$gitSha = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitShortSha = (& git -C $repoRoot rev-parse --short=12 HEAD).Trim()
$gitStatus = (& git -C $repoRoot status --porcelain --untracked-files=no | Out-String)
$gitDirty = -not [string]::IsNullOrWhiteSpace($gitStatus)

if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $androidRoot "release-artifacts\$versionName\$gitShortSha"
}
$resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $resolvedOutput.StartsWith([IO.Path]::GetFullPath($androidRoot), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Release artifact output must remain inside this Android worktree.'
}
New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null

if (-not $SkipBuild) {
    Push-Location $androidRoot
    try {
        & $gradle --no-daemon --max-workers=1 ':app:unsignedReleaseArtifacts'
        if ($LASTEXITCODE -ne 0) {
            throw "Unsigned release build failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

$sourceArtifacts = @()
$sourceArtifacts += Get-ChildItem -LiteralPath (Join-Path $buildRoot 'apk\prod\release') -File -Filter '*.apk'
$sourceArtifacts += Get-ChildItem -LiteralPath (Join-Path $buildRoot 'bundle\prodRelease') -File -Filter '*.aab'
if (@($sourceArtifacts).Count -lt 2) {
    throw 'Expected both a production release APK and AAB.'
}

$copiedArtifacts = @()
foreach ($artifact in $sourceArtifacts) {
    $destinationName = "medtrack-$versionName-$gitShortSha-$($artifact.Name)"
    $destination = Join-Path $resolvedOutput $destinationName
    Copy-Item -LiteralPath $artifact.FullName -Destination $destination -Force
    $copiedArtifacts += Get-Item -LiteralPath $destination
}

$hashLines = foreach ($artifact in $copiedArtifacts) {
    $hash = (Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($artifact.Name)"
}
$hashLines | Set-Content -LiteralPath (Join-Path $resolvedOutput 'SHA256SUMS.txt') -Encoding utf8NoBOM

$components = @{}
$lockFiles = @(Get-ChildItem -LiteralPath $androidRoot -Recurse -Filter 'gradle.lockfile' -File |
    Where-Object { $_.FullName -notlike "*$([IO.Path]::DirectorySeparatorChar).build$([IO.Path]::DirectorySeparatorChar)*" })
foreach ($lockFile in $lockFiles) {
    foreach ($line in Get-Content -LiteralPath $lockFile.FullName) {
        if ($line -notmatch '^([^#=]+):([^:=]+):([^=]+)=') { continue }
        $group = $matches[1]
        $name = $matches[2]
        $componentVersion = $matches[3]
        $key = "$group`:$name`:$componentVersion"
        if (-not $components.ContainsKey($key)) {
            $purlGroup = [Uri]::EscapeDataString($group).Replace('%2F', '/')
            $purlName = [Uri]::EscapeDataString($name)
            $purlVersion = [Uri]::EscapeDataString($componentVersion)
            $components[$key] = [ordered]@{
                type = 'library'
                group = $group
                name = $name
                version = $componentVersion
                purl = "pkg:maven/$purlGroup/$purlName@$purlVersion"
            }
        }
    }
}
$sbom = [ordered]@{
    bomFormat = 'CycloneDX'
    specVersion = '1.5'
    serialNumber = "urn:uuid:$([guid]::NewGuid())"
    version = 1
    metadata = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString('o')
        component = [ordered]@{
            type = 'application'
            name = 'MEDTRACK Android'
            version = $versionName
        }
        properties = @(
            [ordered]@{ name = 'medtrack:git-sha'; value = $gitSha },
            [ordered]@{ name = 'medtrack:dependency-source'; value = 'committed Gradle lockfiles' }
        )
    }
    components = @($components.GetEnumerator() | Sort-Object Name | ForEach-Object { $_.Value })
}
$sbom | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'sbom.cdx.json') -Encoding utf8NoBOM

$forbiddenEntryPattern = '(?i)(^|/)(google-services\.json|\.env($|\.)|[^/]*\.(pem|key|p12|jks|keystore)|local_credentials[^/]*|[^/]*service-account[^/]*|[^/]*firebase-adminsdk[^/]*)$'
$auditArtifacts = @()
$auditPassed = $true
foreach ($artifact in $copiedArtifacts) {
    $entries = @(& jar tf $artifact.FullName)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect archive $($artifact.Name)."
    }
    $forbiddenEntries = @($entries | Where-Object { $_ -match $forbiddenEntryPattern })
    $signatureOutput = (& jarsigner -verify $artifact.FullName 2>&1 | Out-String)
    $isSigned = $signatureOutput -notmatch '(?i)jar is unsigned'
    if ($forbiddenEntries.Count -gt 0) { $auditPassed = $false }
    $auditArtifacts += [ordered]@{
        file = $artifact.Name
        sha256 = (Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        bytes = $artifact.Length
        signed = $isSigned
        forbiddenEntries = $forbiddenEntries
    }
}
$audit = [ordered]@{
    status = if ($auditPassed) { 'PASS' } else { 'FAIL' }
    forbiddenPattern = $forbiddenEntryPattern
    artifacts = $auditArtifacts
}
$audit | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'artifact-audit.json') -Encoding utf8NoBOM
if (-not $auditPassed) {
    throw 'Artifact audit found a forbidden credential or secret-like entry.'
}

$wrapperHash = (Get-FileHash -LiteralPath (Join-Path $androidRoot 'gradle\wrapper\gradle-wrapper.jar') -Algorithm SHA256).Hash.ToLowerInvariant()
$provenance = [ordered]@{
    schemaVersion = 1
    generatedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    source = [ordered]@{
        repository = (& git -C $repoRoot remote get-url origin).Trim()
        commit = $gitSha
        dirty = $gitDirty
    }
    build = [ordered]@{
        variant = 'prodRelease'
        versionName = $versionName
        versionCode = $versionCode
        compileSdk = 36
        targetSdk = 36
        gradle = '8.11.1'
        androidGradlePlugin = '8.9.1'
        wrapperSha256 = $wrapperHash
        requestedSigning = 'unsigned review artifacts'
        worktreeBuildRoot = $buildRoot
    }
    materials = [ordered]@{
        dependencyLockFiles = @($lockFiles | ForEach-Object { [IO.Path]::GetRelativePath($androidRoot, $_.FullName) })
        thirdPartyNotice = 'THIRD_PARTY_NOTICES.md'
    }
    subjects = $auditArtifacts
}
$provenance | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'provenance.json') -Encoding utf8NoBOM

[pscustomobject]@{
    status = 'PASS'
    outputDirectory = $resolvedOutput
    sourceCommit = $gitSha
    sourceDirty = $gitDirty
    artifactCount = $copiedArtifacts.Count
    componentCount = $components.Count
} | ConvertTo-Json
