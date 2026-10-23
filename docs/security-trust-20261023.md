# October 23 certificate trust remediation

This release refreshes trust stores without changing application behavior or database schema. Preserve the existing deployment, independent-restore, patient-identity, audit-chain and authenticated-smoke gates in [RUNBOOK.md](../RUNBOOK.md).

Reviewed upstream targets:

- [Certifi advisory GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2): pin 2026.10.19, which removes the affected emSign ECC G3 root and retains unaffected roots.
- [Python security guidance](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576): pip has an independent vendored bundle. Pin 26.2.2 in both lock environments, and bootstrap it using the official wheel URL and SHA256 before dependency resolution/installation in CI, lock generation and the web image.
- [Alpine CA packages](https://pkgs.alpinelinux.org/package/v3.23/main/x86_64/ca-certificates): 20261020-r0, also verified in the signed v3.24 package index. Pin both ca-certificates and ca-certificates-bundle in web, PostgreSQL and Caddy. The refreshed Alpine 3.24 runtime resolves to 3.24.3. Other reviewed base digests are unchanged.
- [Go release history](https://go.dev/doc/devel/release): build Caddy using Go 1.26.10 for the October 19 crypto/x509 security fix.
- [Node October security release](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases): pin browser CI to 22.23.4.

Regenerate the production and CI locks with `python scripts/update-python-locks.py`; do not hand-edit hashes. Rebuild and scan all three service images. Verify actual CA bundle contents, pip's vendored bundle and the shipped Go build information, in addition to package versions. Keep UID/GID hardening, immutable image pins, runtime copy allowlists and empty vulnerability-exception policies intact.

Local evidence: `output/security-remediation-20261023/`. Production acceptance remains a separate deployment receipt tied to the merged commit; a locally tested image or public version page does not establish privileged runtime or recovery verification.
