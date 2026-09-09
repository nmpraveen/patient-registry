# Required `main` protection

`main` is protected. A read-only audit on 2026-09-09 returned an active
legacy protection object with strict, Actions-app-bound required checks,
administrator enforcement, linear history and conversation resolution, and
`[]` for both `rulesets` and effective `rules/branches/main`. This supersedes
the 2026-08-29 audit that recorded `main` as unprotected; the SoloSafe policy
was applied between those two audits. This lane must not perform the live
apply.

The audited required set on 2026-09-09 was ten checks, still including
`Android (unit)`, `Android (lint)` and `Android (release)`. The tracked
payloads in this directory now request **seven** checks, because Android is a
deprecated target under issue #120. Applying that reduction is an
administrator action and has not been performed by the change that introduced
these payloads.

The installer is read-only by default. Every invocation re-audits repository
identity, administrator access, collaborators, global CODEOWNERS, current
protection, signed-commit state, rulesets, and effective rules. It writes:

- the exact proposed REST payload;
- a `medtrack.branch-protection-rollback/v1` snapshot of the pre-change state;
- a REST-compatible rollback payload when protection already exists.

All seven checks use the GitHub Actions app ID `15368`; legacy unbound status
contexts are not accepted. Apply also requires every check to be completed and
successful on the exact supplied `main` SHA before any mutation.

## Android deprecation and required apply ordering

Issue #120 makes this a web-only project. Android source and history are
retained, but `Android (unit)`, `Android (lint)` and `Android (release)` are no
longer acceptance gates for web work.

The reduction from ten to seven required checks and the retirement of the
Android CI jobs are **two changes that must happen in this order**:

1. An administrator applies the seven-check payload to live `main` and records
   a read-back.
2. Only then may `.github/workflows/ci.yml` stop producing the three Android
   check runs.

Doing step 2 first leaves every open and future pull request permanently
waiting on three required contexts that no workflow will ever report, which
cannot be cleared by re-running CI. The change that introduced the seven-check
payloads therefore left the `android` job in `ci.yml` untouched, so it remains
mergeable under the ten-check protection that is live today.

Read-only verification of the current live state, safe to run at any time:

```bash
gh api repos/nmpraveen/patient-registry/branches/main/protection \
  --jq '.required_status_checks.checks[].context'
gh api repos/nmpraveen/patient-registry/rulesets --jq 'length'
```

After the apply, that first command must list exactly the seven web/security
contexts and no `Android (...)` context. Record the output as the read-back
evidence; a merged source change to the tracked payload files is not by itself
proof that live protection changed.

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
