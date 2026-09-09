# Required `main` protection

`main` is protected. The seven-check SoloSafe policy was applied and read back
on 2026-09-09 at `a8e528b1da16467c11124f10d68d80676c7845b4`. The active
legacy protection object has strict, Actions-app-bound required checks,
administrator enforcement, linear history and conversation resolution, and
`[]` for both `rulesets` and effective `rules/branches/main`. This supersedes
both the stale 2026-08-29 "unprotected" record and the earlier 2026-09-09
ten-check read-back.

The live required set and both tracked payloads now contain exactly **seven**
checks: Django tests, Migration integrity, Strict OpenAPI, Supply-chain scans,
Compose and shell, Container integrity, and Frontend no-overflow. All seven are
bound to the GitHub Actions app ID `15368`; no `Android (...)` context remains.

The installer is read-only by default. Every invocation re-audits repository
identity, administrator access, collaborators, global CODEOWNERS, current
protection, signed-commit state, rulesets, and effective rules. It writes:

- the exact proposed REST payload;
- a `medtrack.branch-protection-rollback/v1` snapshot of the pre-change state;
- a REST-compatible rollback payload when protection already exists.

All seven checks use the GitHub Actions app ID `15368`; legacy unbound status
contexts are not accepted. Apply also requires every check to be completed and
successful on the exact supplied `main` SHA before any mutation.

## Android deprecation and completed apply ordering

Issue #120 makes this a web-only project. Android source and history are
retained, but `Android (unit)`, `Android (lint)` and `Android (release)` are no
longer acceptance gates for web work.

The reduction from ten to seven required checks and the retirement of the
Android CI job were completed in this order:

1. The seven-check payload was applied to live `main` and read back.
2. Only after that proof was recorded was the `android` job removed from
   `.github/workflows/ci.yml`.

This ordering remains an operational invariant: retiring a workflow context
before removing it from live protection leaves every open and future pull
request waiting on a check that can never report. The pre-retirement PR head
`6665909f720c7bdf66940bb7a07d7cc17dca81a3` passed all ten former contexts,
including the restored full-tree supply-chain scan.

Read-only verification of the current live state, safe to run at any time:

```bash
gh api repos/nmpraveen/patient-registry/branches/main/protection \
  --jq '.required_status_checks.checks[].context'
gh api repos/nmpraveen/patient-registry/rulesets --jq 'length'
```

The first command must list exactly the seven web/security contexts and no
`Android (...)` context. A tracked payload is not proof of live state; always
use this read-back after a future apply.

The sanctioned installer is `scripts/apply-branch-protection.ps1` and requires
PowerShell. Its `$expectedContexts` list is kept in the same order as the
tracked payloads, so the two must be updated together.

## Reviewer policies

### SoloSafe (current feasible mode)

`.github/branch-protection.json` requires pull requests, all immutable
exact-head checks, conversation resolution, linear history, and administrator
enforcement, while blocking direct/force/delete paths. Approval count is zero
because `nmpraveen` is currently the only trusted collaborator/administrator;
requiring the author's own approval would deadlock.

Read-only plan:

```powershell
.\scripts\apply-branch-protection.ps1 `
  -ReviewerPolicy SoloSafe `
  -SignedCommits NotRequired
```

After merge, exact-main green CI, and the coordinator's explicit signed-commit
choice, an administrator may apply:

```powershell
.\scripts\apply-branch-protection.ps1 `
  -Apply `
  -ReviewerPolicy SoloSafe `
  -SignedCommits <Required-or-NotRequired> `
  -ExpectedMainSha <40-character-main-sha>
```

### OneApproval (intentionally infeasible today)

`.github/branch-protection.one-approval.json` additionally requires one global
CODEOWNER approval, stale-review dismissal, and approval by someone other than
the last pusher. Before using it, add a second specifically trusted collaborator
with push/maintain/admin access to the global `*` rule in `.github/CODEOWNERS`
through a reviewed PR. The installer refuses `-Apply` unless at least two global
CODEOWNERS are also trusted collaborators, preventing the current solo-owner
deadlock.

Read-only feasibility plan:

```powershell
.\scripts\apply-branch-protection.ps1 `
  -ReviewerPolicy OneApproval `
  -SignedCommits Required
```

Conditional apply after the second reviewer and exact-main green proof:

```powershell
.\scripts\apply-branch-protection.ps1 `
  -Apply `
  -ReviewerPolicy OneApproval `
  -SignedCommits <Required-or-NotRequired> `
  -ExpectedMainSha <40-character-main-sha>
```

Both `-ReviewerPolicy` and `-SignedCommits` must be explicitly supplied for
apply. Signed commits are deliberately a coordinator choice, not an implicit
default.

## Fields verified after apply

The readback must exactly preserve:

- strict Actions-app-bound required checks and successful exact-SHA check runs;
- pull-request requirement and the selected review policy;
- no review-bypass actors and no push-restriction bypass actors;
- administrator enforcement, linear history, and conversation resolution;
- force-push/deletion/branch-lock/creation/fork-sync fields; fork syncing is
  disabled because GitHub only enables it for a locked branch and this policy
  deliberately leaves `lock_branch` disabled;
- the explicit signed-commit choice.

Apply refuses when rulesets cannot be audited or any ruleset exists, rather
than layering unknown bypass behavior. If readback fails after mutation, the
script attempts automatic restoration from its snapshot. Preserve the snapshot
until a second read-only audit confirms the desired policy.

Repository Actions settings should remain read-only by default. Pull-request
CI has no OIDC or attestation permission. The separate push-to-`main` trusted
workflow builds and verifies the reviewed exact SHA without signing authority;
only its downstream signing job receives `id-token: write` and
`attestations: write`, bound to the verified OCI manifest digest.
