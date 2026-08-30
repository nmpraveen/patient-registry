[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$androidRoot = Split-Path -Parent $PSScriptRoot
$wrapperJar = Join-Path $androidRoot 'gradle\wrapper\gradle-wrapper.jar'
$wrapperHashFile = Join-Path $androidRoot 'gradle\wrapper\gradle-wrapper.jar.sha256'
$wrapperPropertiesFile = Join-Path $androidRoot 'gradle\wrapper\gradle-wrapper.properties'
$gradle = Join-Path $androidRoot 'gradlew.bat'

$expectedHash = ((Get-Content -LiteralPath $wrapperHashFile -Raw).Trim() -split '\s+')[0].ToUpperInvariant()
$actualHash = (Get-FileHash -LiteralPath $wrapperJar -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualHash -ne $expectedHash) {
    throw "Gradle wrapper hash mismatch. Expected $expectedHash but found $actualHash."
}
$wrapperProperties = Get-Content -LiteralPath $wrapperPropertiesFile -Raw
if ($wrapperProperties -notmatch '(?m)^distributionSha256Sum=([a-fA-F0-9]{64})$') {
    throw 'Gradle distributionSha256Sum is missing or invalid.'
}
$distributionHash = $matches[1].ToUpperInvariant()

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
        & $gradle --no-daemon --max-workers=1 --offline $check[0] '--configuration' $check[1]
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
    lockFileCount = $lockFiles.Count
    mode = 'strict locks and offline resolution'
} | ConvertTo-Json
