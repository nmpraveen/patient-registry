[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$androidRoot = Split-Path -Parent $PSScriptRoot
$gradle = Join-Path $androidRoot 'gradlew.bat'

Push-Location $androidRoot
try {
    $taskGroups = @(
        @('test'),
        @(':app:lintProdRelease'),
        @(':app:assembleDevDebug'),
        @(':app:unsignedReleaseArtifacts')
    )
    foreach ($tasks in $taskGroups) {
        & $gradle --no-daemon --max-workers=1 @tasks
        if ($LASTEXITCODE -ne 0) {
            throw "Gradle task group failed: $($tasks -join ', ')"
        }
    }
}
finally {
    Pop-Location
}

& (Join-Path $PSScriptRoot 'verify-dependencies.ps1')
& (Join-Path $PSScriptRoot 'build-release-artifacts.ps1') -SkipBuild
