[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$androidRoot = Split-Path -Parent $PSScriptRoot
$wrapperJar = Join-Path $androidRoot 'gradle\wrapper\gradle-wrapper.jar'
$wrapperHashFile = Join-Path $androidRoot 'gradle\wrapper\gradle-wrapper.jar.sha256'
$wrapperPropertiesFile = Join-Path $androidRoot 'gradle\wrapper\gradle-wrapper.properties'
$gradle = Join-Path $androidRoot 'gradlew.bat'
$verificationMetadataFile = Join-Path $androidRoot 'gradle\verification-metadata.xml'

$expectedHash = ((Get-Content -LiteralPath $wrapperHashFile -Raw).Trim() -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -LiteralPath $wrapperJar -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualHash -ne $expectedHash) {
    throw "Gradle wrapper hash mismatch. Expected $expectedHash but found $actualHash."
}
$wrapperProperties = Get-Content -LiteralPath $wrapperPropertiesFile -Raw
if ($wrapperProperties -notmatch '(?m)^distributionSha256Sum=([a-fA-F0-9]{64})\r?$') {
    throw 'Gradle distributionSha256Sum is missing or invalid.'
}
$distributionHash = $matches[1].ToUpperInvariant()

if (-not (Test-Path -LiteralPath $verificationMetadataFile -PathType Leaf)) {
    throw 'Missing gradle/verification-metadata.xml; dependency bytes are not pinned.'
}
$verificationMetadata = Get-Content -LiteralPath $verificationMetadataFile -Raw
if ($verificationMetadata -notmatch '<verify-metadata>true</verify-metadata>' -or
    $verificationMetadata -notmatch '<sha256 value="[a-fA-F0-9]{64}"') {
    throw 'Dependency verification metadata must verify artifact metadata and include SHA-256 checksums.'
}

$lockFiles = @(Get-ChildItem -LiteralPath $androidRoot -Recurse -Filter 'gradle.lockfile' -File |
    Where-Object { $_.FullName -notlike "*$([IO.Path]::DirectorySeparatorChar).build$([IO.Path]::DirectorySeparatorChar)*" })
$requiredLocks = @(
    'app\gradle.lockfile',
    'core\data\gradle.lockfile',
    'core\network\gradle.lockfile'
)
foreach ($relativeLock in $requiredLocks) {
    if (-not (Test-Path -LiteralPath (Join-Path $androidRoot $relativeLock))) {
        throw "Missing required dependency lock: $relativeLock"
    }
}

Push-Location $androidRoot
try {
    $dependencyChecks = @(
        @(':app:dependencies', 'prodReleaseRuntimeClasspath'),
        @(':core:data:dependencies', 'releaseRuntimeClasspath'),
        @(':core:network:dependencies', 'releaseRuntimeClasspath')
    )
    foreach ($check in $dependencyChecks) {
        & $gradle --no-daemon --max-workers=1 --offline '--dependency-verification' 'strict' $check[0] '--configuration' $check[1]
        if ($LASTEXITCODE -ne 0) {
            throw "Offline dependency resolution failed for $($check[0]) / $($check[1]) with exit code $LASTEXITCODE."
        }
    }
}
finally {
    Pop-Location
}

[pscustomobject]@{
    status = 'PASS'
    wrapperSha256 = $actualHash
    distributionSha256 = $distributionHash
    verificationMetadataSha256 = (Get-FileHash -LiteralPath $verificationMetadataFile -Algorithm SHA256).Hash.ToUpperInvariant()
    lockFileCount = $lockFiles.Count
    mode = 'strict locks, SHA-256 byte verification, and offline resolution'
} | ConvertTo-Json
