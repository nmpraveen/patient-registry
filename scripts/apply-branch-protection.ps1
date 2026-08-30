[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateSet("SoloSafe", "OneApproval")]
    [string]$ReviewerPolicy = "SoloSafe",
    [ValidateSet("Required", "NotRequired")]
    [string]$SignedCommits = "NotRequired",
    [string]$ExpectedMainSha,
    [string]$OutputDirectory = "output\branch-protection"
)

$ErrorActionPreference = "Stop"
$repository = "nmpraveen/patient-registry"
$branchName = "main"
$actionsAppId = 15368
$expectedContexts = @(
    "Django tests", "Migration integrity", "Strict OpenAPI",
    "Supply-chain scans", "Compose and shell", "Container integrity",
    "Android (unit)", "Android (lint)", "Android (release)",
    "Frontend no-overflow"
)
$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = if ($ReviewerPolicy -eq "SoloSafe") {
    Join-Path $repoRoot ".github\branch-protection.json"
} else {
    Join-Path $repoRoot ".github\branch-protection.one-approval.json"
}
$codeownersPath = Join-Path $repoRoot ".github\CODEOWNERS"
$outputPath = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
}

function Invoke-GhJson {
    param([Parameter(Mandatory)] [string[]]$Arguments, [switch]$AllowFailure)
    $result = & gh @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        if ($AllowFailure) { return [pscustomobject]@{ Success = $false; Value = $null } }
        throw "GitHub CLI request failed: gh $($Arguments -join ' ')"
    }
    $text = ($result -join "`n").Trim()
    $value = if ($text) { $text | ConvertFrom-Json } else { $null }
    return [pscustomobject]@{ Success = $true; Value = $value }
}

function Invoke-GhMutation {
    param([Parameter(Mandatory)] [string[]]$Arguments)
    & gh @Arguments --silent
    if ($LASTEXITCODE -ne 0) { throw "GitHub rejected mutation: gh $($Arguments -join ' ')" }
}

function Get-EnabledValue {
    param($Value)
    if ($null -eq $Value) { return $false }
    if ($Value -is [bool]) { return [bool]$Value }
    if ($null -ne $Value.PSObject.Properties["enabled"]) { return [bool]$Value.enabled }
    return [bool]$Value
}

function Get-Logins {
    param($Values, [string]$Property = "login")
    if ($null -eq $Values) { return @() }
    return @($Values | ForEach-Object { [string]$_.$Property } | Where-Object { $_ } | Sort-Object -Unique)
}

function Assert-TrackedPayload {
    param($Payload, [string]$Policy)
    $checks = @($Payload.required_status_checks.checks)
    if ($checks.Count -ne $expectedContexts.Count) {
        throw "Tracked payload must contain exactly $($expectedContexts.Count) required checks."
    }
    for ($index = 0; $index -lt $expectedContexts.Count; $index++) {
        if ($checks[$index].context -ne $expectedContexts[$index] -or
            [int]$checks[$index].app_id -ne $actionsAppId) {
            throw "Tracked required check mismatch at index $index."
        }
    }
    if (-not [bool]$Payload.required_status_checks.strict -or -not [bool]$Payload.enforce_admins) {
        throw "Strict checks and administrator enforcement must be enabled."
    }
    if ($null -eq $Payload.required_pull_request_reviews) { throw "Pull requests must be required." }
    $reviews = $Payload.required_pull_request_reviews
    if ($Policy -eq "SoloSafe") {
        if ([int]$reviews.required_approving_review_count -ne 0 -or
            [bool]$reviews.dismiss_stale_reviews -or
            [bool]$reviews.require_last_push_approval -or
            [bool]$reviews.require_code_owner_reviews) {
            throw "SoloSafe payload review fields are unsafe."
        }
    } elseif ([int]$reviews.required_approving_review_count -ne 1 -or
        -not [bool]$reviews.dismiss_stale_reviews -or
        -not [bool]$reviews.require_last_push_approval -or
        -not [bool]$reviews.require_code_owner_reviews) {
        throw "OneApproval payload review fields are unsafe."
    }
    $expected = @{
        required_linear_history = $true; allow_force_pushes = $false
        allow_deletions = $false; block_creations = $false
        required_conversation_resolution = $true; lock_branch = $false
        allow_fork_syncing = $false
    }
    foreach ($field in $expected.Keys) {
        if ([bool]$Payload.$field -ne $expected[$field]) {
            throw "Tracked payload field $field does not match the reviewed policy."
        }
    }
    if ($null -ne $Payload.restrictions) { throw "Tracked payload must not grant push bypass restrictions." }
}

function Assert-AppliedProtection {
    param($Protection, [string]$Policy)
    if ($null -eq $Protection) { throw "Branch protection readback is empty." }
    $checks = @($Protection.required_status_checks.checks)
    if ($checks.Count -ne $expectedContexts.Count) { throw "Applied required-check count mismatch." }
    foreach ($context in $expectedContexts) {
        $matches = @($checks | Where-Object {
            $_.context -eq $context -and [int]$_.app_id -eq $actionsAppId
        })
        if ($matches.Count -ne 1) { throw "Applied check is not Actions-app-bound: $context" }
    }
    if (-not [bool]$Protection.required_status_checks.strict) { throw "Strict checks are disabled." }
    if (-not (Get-EnabledValue $Protection.enforce_admins)) { throw "Administrator enforcement is disabled." }
    if ($null -eq $Protection.required_pull_request_reviews) { throw "Pull requests are not required." }
    $reviews = $Protection.required_pull_request_reviews
    $bypassCount = (Get-Logins $reviews.bypass_pull_request_allowances.users).Count +
        (Get-Logins $reviews.bypass_pull_request_allowances.teams "slug").Count +
        (Get-Logins $reviews.bypass_pull_request_allowances.apps "slug").Count
    if ($bypassCount -ne 0) { throw "Pull-request bypass allowances are present." }
    if ($Policy -eq "SoloSafe") {
        if ([int]$reviews.required_approving_review_count -ne 0 -or
            [bool]$reviews.dismiss_stale_reviews -or
            [bool]$reviews.require_last_push_approval -or
            [bool]$reviews.require_code_owner_reviews) { throw "Applied SoloSafe review settings mismatch." }
    } elseif ([int]$reviews.required_approving_review_count -ne 1 -or
        -not [bool]$reviews.dismiss_stale_reviews -or
        -not [bool]$reviews.require_last_push_approval -or
        -not [bool]$reviews.require_code_owner_reviews) {
        throw "Applied OneApproval review settings mismatch."
    }
    $actual = @{
        required_linear_history = Get-EnabledValue $Protection.required_linear_history
        allow_force_pushes = Get-EnabledValue $Protection.allow_force_pushes
        allow_deletions = Get-EnabledValue $Protection.allow_deletions
        block_creations = Get-EnabledValue $Protection.block_creations
        required_conversation_resolution = Get-EnabledValue $Protection.required_conversation_resolution
        lock_branch = Get-EnabledValue $Protection.lock_branch
        allow_fork_syncing = Get-EnabledValue $Protection.allow_fork_syncing
    }
    $expected = @{
        required_linear_history = $true; allow_force_pushes = $false
        allow_deletions = $false; block_creations = $false
        required_conversation_resolution = $true; lock_branch = $false
        allow_fork_syncing = $false
    }
    foreach ($field in $expected.Keys) {
        if ($actual[$field] -ne $expected[$field]) { throw "Applied field $field mismatch." }
    }
    if ($null -ne $Protection.restrictions) { throw "Applied protection contains push bypass actors." }
}

function Convert-ProtectionToPutPayload {
    param($Protection)
    if ($null -eq $Protection) { return $null }
    $reviewPayload = $null
    $reviews = $Protection.required_pull_request_reviews
    if ($null -ne $reviews) {
        $reviewPayload = [ordered]@{
            dismiss_stale_reviews = [bool]$reviews.dismiss_stale_reviews
            require_code_owner_reviews = [bool]$reviews.require_code_owner_reviews
            required_approving_review_count = [int]$reviews.required_approving_review_count
            require_last_push_approval = [bool]$reviews.require_last_push_approval
        }
        $dismissalUsers = Get-Logins $reviews.dismissal_restrictions.users
        $dismissalTeams = Get-Logins $reviews.dismissal_restrictions.teams "slug"
        if (($dismissalUsers.Count + $dismissalTeams.Count) -gt 0) {
            $reviewPayload.dismissal_restrictions = [ordered]@{ users = $dismissalUsers; teams = $dismissalTeams }
        }
        $bypassUsers = Get-Logins $reviews.bypass_pull_request_allowances.users
        $bypassTeams = Get-Logins $reviews.bypass_pull_request_allowances.teams "slug"
        $bypassApps = Get-Logins $reviews.bypass_pull_request_allowances.apps "slug"
        if (($bypassUsers.Count + $bypassTeams.Count + $bypassApps.Count) -gt 0) {
            $reviewPayload.bypass_pull_request_allowances = [ordered]@{
                users = $bypassUsers; teams = $bypassTeams; apps = $bypassApps
            }
        }
    }
    $statusPayload = $null
    if ($null -ne $Protection.required_status_checks) {
        $statusPayload = [ordered]@{
            strict = [bool]$Protection.required_status_checks.strict
            checks = @($Protection.required_status_checks.checks | ForEach-Object {
                [ordered]@{ context = [string]$_.context; app_id = [int]$_.app_id }
            })
        }
    }
    $restrictionPayload = $null
    if ($null -ne $Protection.restrictions) {
        $restrictionPayload = [ordered]@{
            users = Get-Logins $Protection.restrictions.users
            teams = Get-Logins $Protection.restrictions.teams "slug"
            apps = Get-Logins $Protection.restrictions.apps "slug"
        }
    }
    return [ordered]@{
        required_status_checks = $statusPayload
        enforce_admins = Get-EnabledValue $Protection.enforce_admins
        required_pull_request_reviews = $reviewPayload
        restrictions = $restrictionPayload
        required_linear_history = Get-EnabledValue $Protection.required_linear_history
        allow_force_pushes = Get-EnabledValue $Protection.allow_force_pushes
        allow_deletions = Get-EnabledValue $Protection.allow_deletions
        block_creations = Get-EnabledValue $Protection.block_creations
        required_conversation_resolution = Get-EnabledValue $Protection.required_conversation_resolution
        lock_branch = Get-EnabledValue $Protection.lock_branch
        allow_fork_syncing = Get-EnabledValue $Protection.allow_fork_syncing
    }
}

function Set-SignaturePolicy {
    param([bool]$Required)
    $current = Invoke-GhJson @("api", "repos/$repository/branches/$branchName/protection/required_signatures") -AllowFailure
    $enabled = $current.Success -and (Get-EnabledValue $current.Value)
    if ($Required -and -not $enabled) {
        Invoke-GhMutation @("api", "--method", "POST", "repos/$repository/branches/$branchName/protection/required_signatures")
    } elseif (-not $Required -and $enabled) {
        Invoke-GhMutation @("api", "--method", "DELETE", "repos/$repository/branches/$branchName/protection/required_signatures")
    }
}

function Restore-Protection {
    param($Snapshot, [string]$RollbackPayloadPath)
    if (-not [bool]$Snapshot.protected) {
        Invoke-GhMutation @("api", "--method", "DELETE", "repos/$repository/branches/$branchName/protection")
        return
    }
    Invoke-GhMutation @("api", "--method", "PUT", "repos/$repository/branches/$branchName/protection", "--input", $RollbackPayloadPath)
    Set-SignaturePolicy ([bool]$Snapshot.signed_commits_required)
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "GitHub CLI (gh) is required." }
& gh auth status 1>$null 2>$null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated." }
$repo = (Invoke-GhJson @("api", "repos/$repository")).Value
if ($repo.full_name -ne $repository -or $repo.default_branch -ne $branchName) {
    throw "Repository identity/default branch did not match $repository $branchName."
}
if (-not [bool]$repo.permissions.admin) { throw "Authenticated account lacks repository administrator permission." }
$viewer = (Invoke-GhJson @("api", "user")).Value
$branch = (Invoke-GhJson @("api", "repos/$repository/branches/$branchName")).Value
$mainSha = [string]$branch.commit.sha
$payload = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
Assert-TrackedPayload $payload $ReviewerPolicy

$collaborators = @((Invoke-GhJson @("api", "repos/$repository/collaborators?affiliation=all&per_page=100")).Value)
$trustedCollaborators = @($collaborators | Where-Object {
    $_.type -eq "User" -and ($_.permissions.push -or $_.permissions.maintain -or $_.permissions.admin)
} | ForEach-Object { [string]$_.login } | Sort-Object -Unique)
$globalCodeownersLine = Get-Content -LiteralPath $codeownersPath | Where-Object { $_ -match '^\s*\*\s+' } | Select-Object -First 1
$globalCodeowners = @([regex]::Matches([string]$globalCodeownersLine, '@([A-Za-z0-9-]+)') | ForEach-Object {
    $_.Groups[1].Value
} | Sort-Object -Unique)
$trustedGlobalCodeowners = @($globalCodeowners | Where-Object { $_ -in $trustedCollaborators })
$reviewerFeasible = $trustedGlobalCodeowners.Count -ge 2

$protectionResult = Invoke-GhJson @("api", "repos/$repository/branches/$branchName/protection") -AllowFailure
$currentProtection = if ($protectionResult.Success) { $protectionResult.Value } else { $null }
if ([bool]$branch.protected -and -not $protectionResult.Success) {
    throw "GitHub reports main protected, but its full protection could not be read."
}
$signaturesResult = Invoke-GhJson @("api", "repos/$repository/branches/$branchName/protection/required_signatures") -AllowFailure
$currentSignedRequired = $signaturesResult.Success -and (Get-EnabledValue $signaturesResult.Value)
$rulesetsResult = Invoke-GhJson @("api", "repos/$repository/rulesets?includes_parents=true&per_page=100") -AllowFailure
$effectiveRulesResult = Invoke-GhJson @("api", "repos/$repository/rules/branches/$branchName") -AllowFailure

$rollbackPayload = Convert-ProtectionToPutPayload $currentProtection
[IO.Directory]::CreateDirectory($outputPath) | Out-Null
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$shortSha = $mainSha.Substring(0, 12)
$snapshotPath = Join-Path $outputPath "rollback-$timestamp-$shortSha.json"
$rollbackPayloadPath = Join-Path $outputPath "rollback-payload-$timestamp-$shortSha.json"
$proposedPayloadPath = Join-Path $outputPath "proposed-$($ReviewerPolicy.ToLowerInvariant())-$timestamp.json"
[IO.File]::WriteAllText($proposedPayloadPath, (($payload | ConvertTo-Json -Depth 20) + "`n"))
if ($null -ne $rollbackPayload) {
    [IO.File]::WriteAllText($rollbackPayloadPath, (($rollbackPayload | ConvertTo-Json -Depth 20) + "`n"))
}
$snapshot = [ordered]@{
    schema = "medtrack.branch-protection-rollback/v1"; repository = $repository
    branch = $branchName; captured_at = [DateTime]::UtcNow.ToString("o")
    captured_by = [string]$viewer.login; main_sha = $mainSha
    protected = [bool]$branch.protected; protection = $currentProtection
    signed_commits_required = [bool]$currentSignedRequired
    rulesets_query_succeeded = [bool]$rulesetsResult.Success; rulesets = $rulesetsResult.Value
    effective_rules_query_succeeded = [bool]$effectiveRulesResult.Success; effective_rules = $effectiveRulesResult.Value
    trusted_collaborators = $trustedCollaborators; global_codeowners = $globalCodeowners
    selected_reviewer_policy = $ReviewerPolicy; selected_signed_commit_policy = $SignedCommits
    proposed_payload = $payload
    rollback = [ordered]@{
        method = if ([bool]$branch.protected) { "PUT" } else { "DELETE" }
        endpoint = "repos/$repository/branches/$branchName/protection"
        payload_file = if ($null -ne $rollbackPayload) { $rollbackPayloadPath } else { $null }
        signed_commits_required = [bool]$currentSignedRequired
    }
}
[IO.File]::WriteAllText($snapshotPath, (($snapshot | ConvertTo-Json -Depth 30) + "`n"))

if (-not $Apply) {
    Write-Output ("BRANCH_PROTECTION_PLAN_OK repository=$repository main=$mainSha mutation=false " +
        "reviewer_policy=$ReviewerPolicy reviewer_feasible=$($reviewerFeasible.ToString().ToLowerInvariant()) " +
        "trusted_collaborators=$($trustedCollaborators.Count) global_codeowners=$($trustedGlobalCodeowners.Count) " +
        "signed_commits=$SignedCommits protected=$([bool]$branch.protected)")
    Write-Output "BRANCH_PROTECTION_PROPOSED_PAYLOAD path=$proposedPayloadPath"
    Write-Output "BRANCH_PROTECTION_ROLLBACK_SNAPSHOT path=$snapshotPath"
    exit 0
}

if (-not $PSBoundParameters.ContainsKey("ReviewerPolicy") -or -not $PSBoundParameters.ContainsKey("SignedCommits")) {
    throw "Apply requires explicit -ReviewerPolicy and -SignedCommits choices."
}
if ($ExpectedMainSha -notmatch '^[0-9a-f]{40}$') { throw "-ExpectedMainSha must be the full lowercase merged main commit." }
if ($mainSha -ne $ExpectedMainSha) { throw "Refusing to apply: GitHub main is $mainSha, expected $ExpectedMainSha." }
if ($ReviewerPolicy -eq "OneApproval" -and -not $reviewerFeasible) {
    throw "OneApproval would deadlock: two trusted collaborators must both be global CODEOWNERS."
}
if (-not $rulesetsResult.Success -or -not $effectiveRulesResult.Success) {
    throw "Rulesets/effective rules could not be audited; refusing apply."
}
if (@($rulesetsResult.Value).Count -gt 0) {
    throw "Repository rulesets exist; refusing to layer unverified overlapping/bypass policy."
}
Invoke-GhJson @("api", "repos/$repository/contents/.github/workflows/ci.yml?ref=$mainSha") | Out-Null
$checkRuns = (Invoke-GhJson @("api", "repos/$repository/commits/$mainSha/check-runs?filter=latest&per_page=100")).Value
foreach ($context in $expectedContexts) {
    $successful = @($checkRuns.check_runs | Where-Object {
        $_.name -eq $context -and [int]$_.app.id -eq $actionsAppId -and
        $_.head_sha -eq $mainSha -and $_.status -eq "completed" -and $_.conclusion -eq "success"
    })
    if ($successful.Count -lt 1) { throw "Required Actions check is not successful on exact main SHA $mainSha`: $context" }
}

$mutationStarted = $false
try {
    Invoke-GhMutation @("api", "--method", "PUT", "repos/$repository/branches/$branchName/protection", "--input", $configPath)
    $mutationStarted = $true
    Set-SignaturePolicy ($SignedCommits -eq "Required")
    $applied = (Invoke-GhJson @("api", "repos/$repository/branches/$branchName/protection")).Value
    Assert-AppliedProtection $applied $ReviewerPolicy
    $appliedSignatures = Invoke-GhJson @("api", "repos/$repository/branches/$branchName/protection/required_signatures") -AllowFailure
    $actualSigned = $appliedSignatures.Success -and (Get-EnabledValue $appliedSignatures.Value)
    if ($actualSigned -ne ($SignedCommits -eq "Required")) { throw "Signed-commit readback does not match choice." }
} catch {
    $originalError = $_
    if ($mutationStarted) {
        try {
            Restore-Protection $snapshot $rollbackPayloadPath
            Write-Warning "Apply failed; prior protection was restored from $snapshotPath. Error: $($originalError.Exception.Message)"
        } catch {
            throw "Apply failed and rollback failed. Use snapshot $snapshotPath. Rollback error: $($_.Exception.Message)"
        }
    }
    throw $originalError
}
Write-Output ("BRANCH_PROTECTION_APPLIED_OK repository=$repository main=$mainSha reviewer_policy=$ReviewerPolicy " +
    "signed_commits=$SignedCommits contexts=$($expectedContexts.Count) actions_app_id=$actionsAppId " +
    "rollback_snapshot=$snapshotPath")
