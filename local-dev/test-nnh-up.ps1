$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeArgs = @("-f", "docker-compose.yml", "-f", "docker-compose.dev.yml")
$overridePath = Join-Path $repoRoot "docker-compose.override.yml"
if (Test-Path $overridePath) {
    $composeArgs += @("-f", "docker-compose.override.yml")
}

$lanIps = @(
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254*" -and
            $_.IPAddress -ne "0.0.0.0"
        } |
        Select-Object -ExpandProperty IPAddress -Unique
)

$allowedHosts = @("localhost", "127.0.0.1", "0.0.0.0") + $lanIps
$csrfTrustedOrigins = @("http://localhost:8000", "http://127.0.0.1:8000") + ($lanIps | ForEach-Object { "http://${_}:8000" })

$env:ALLOWED_HOSTS = ($allowedHosts | Select-Object -Unique) -join ","
$env:CSRF_TRUSTED_ORIGINS = ($csrfTrustedOrigins | Select-Object -Unique) -join ","

Write-Host "Starting Test NNH server with ALLOWED_HOSTS=$env:ALLOWED_HOSTS"
if ($lanIps.Count -gt 0) {
    Write-Host "Same-LAN URLs:"
    $lanIps | ForEach-Object { Write-Host "  http://${_}:8000" }
}

Push-Location $repoRoot
try {
    docker compose @composeArgs up -d
}
finally {
    Pop-Location
}
