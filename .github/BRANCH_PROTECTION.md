# Required `main` branch protection

Apply this configuration only after the CI workflow has merged to `main`. The
tracked JSON requires the exact job names emitted by `MEDTRACK exact-head CI`,
one approving review, approval of the last push, stale-review dismissal,
conversation resolution, an up-to-date PR head, linear history, and protection
for administrators. Direct pushes, force pushes, and branch deletion remain
blocked.

## Preflight (read-only)

From the repository root on an authenticated administrator workstation:

```powershell
.\scripts\apply-branch-protection.ps1
```

The preflight checks the repository identity, default branch, administrator
permission, JSON shape, and exact required-check list without changing GitHub.

## Apply after merge

Wait for the merged `main` workflow run to create all ten check names, record
the full merged `main` commit, then run:

```powershell
.\scripts\apply-branch-protection.ps1 -Apply -ExpectedMainSha <40-character-merged-main-sha>
```

The apply path fails closed unless GitHub `main` equals the supplied commit and
the workflow file is present on `main`. It then applies
`.github/branch-protection.json`, reads the setting back, and verifies the
required contexts. Do not weaken or bypass a failing gate merely to merge a PR;
fix the owning remediation lane or update the gate in a separately reviewed PR.

GitHub Actions settings should also remain:

- Actions enabled for this repository.
- Workflow permissions set to read repository contents by default.
- Fork pull requests require approval before workflows that use repository
  resources; this workflow does not use production secrets.
- Artifact attestations enabled so the post-merge container job can publish the
  image archive and SBOM attestations.
