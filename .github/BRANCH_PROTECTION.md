# Required `main` protection

`main` was read-only audited on 2026-08-29 as unprotected: the legacy
protection endpoint returned 404 and no repository rulesets/effective rules
were present. This repository is **NO-GO for direct production use** until the
CI changes merge, every required check succeeds on that exact `main` SHA, and
an administrator applies one of the reviewed policies below. This lane must
not perform the live apply.

The installer is read-only by default. Every invocation re-audits repository
identity, administrator access, collaborators, global CODEOWNERS, current
protection, signed-commit state, rulesets, and effective rules. It writes:

- the exact proposed REST payload;
- a `medtrack.branch-protection-rollback/v1` snapshot of the pre-change state;
- a REST-compatible rollback payload when protection already exists.

All ten checks use the GitHub Actions app ID `15368`; legacy unbound status
contexts are not accepted. Apply also requires every check to be completed and
successful on the exact supplied `main` SHA before any mutation.

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
- force-push/deletion/branch-lock/creation/fork-sync fields;
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
