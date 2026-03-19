$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeArgs = @("-f", "docker-compose.yml", "-f", "docker-compose.dev.yml")
$overridePath = Join-Path $repoRoot "docker-compose.override.yml"
if (Test-Path $overridePath) {
    $composeArgs += @("-f", "docker-compose.override.yml")
}
Push-Location $repoRoot
try {
    docker compose @composeArgs ps
}
finally {
    Pop-Location
}
