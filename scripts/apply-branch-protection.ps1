[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$ExpectedMainSha
)

$ErrorActionPreference = "Stop"
$repository = "nmpraveen/patient-registry"
$expectedContexts = @(
    "Django tests",
    "Migration integrity",
    "Strict OpenAPI",
    "Supply-chain scans",
    "Compose and shell",
    "Container integrity",
    "Android (unit)",
    "Android (lint)",
    "Android (release)",
    "Frontend no-overflow"
)
$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $repoRoot ".github\branch-protection.json"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required."
}

& gh auth status 1>$null
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated."
}

$repo = (& gh api "repos/$repository" | ConvertFrom-Json)
if ($repo.full_name -ne $repository -or $repo.default_branch -ne "main") {
    throw "Repository identity/default branch did not match $repository main."
}
if (-not $repo.permissions.admin) {
    throw "The authenticated GitHub account lacks repository administrator permission."
}

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$configuredContexts = @($config.required_status_checks.contexts)
if (($configuredContexts -join "`n") -ne ($expectedContexts -join "`n")) {
    throw "The tracked branch-protection required contexts do not match the reviewed list."
}
if (-not $config.required_status_checks.strict -or -not $config.enforce_admins) {
    throw "Strict status checks and administrator enforcement must both be enabled."
}

if (-not $Apply) {
    Write-Output "BRANCH_PROTECTION_PREFLIGHT_OK repository=$repository admin=true mutation=false"
    exit 0
}

if ($ExpectedMainSha -notmatch "^[0-9a-f]{40}$") {
    throw "-ExpectedMainSha must be the full 40-character merged main commit."
}

$actualMainSha = (& gh api "repos/$repository/commits/main" --jq ".sha").Trim()
if ($actualMainSha -ne $ExpectedMainSha) {
    throw "Refusing to apply: GitHub main is $actualMainSha, expected $ExpectedMainSha."
}

& gh api "repos/$repository/contents/.github/workflows/ci.yml?ref=main" --silent
if ($LASTEXITCODE -ne 0) {
    throw "The exact-head CI workflow is not present on GitHub main."
}

& gh api --method PUT "repos/$repository/branches/main/protection" --input $configPath --silent
if ($LASTEXITCODE -ne 0) {
    throw "GitHub rejected the branch-protection update."
}

$applied = (& gh api "repos/$repository/branches/main/protection" | ConvertFrom-Json)
$appliedContexts = @($applied.required_status_checks.contexts)
$missingContexts = @($expectedContexts | Where-Object { $_ -notin $appliedContexts })
if ($missingContexts.Count -gt 0) {
    throw "Branch protection was applied but required contexts are missing: $($missingContexts -join ', ')"
}

Write-Output "BRANCH_PROTECTION_APPLIED_OK repository=$repository main=$actualMainSha contexts=$($expectedContexts.Count)"
