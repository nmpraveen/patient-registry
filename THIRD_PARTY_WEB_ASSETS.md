# Third-party web assets

MEDTRACK serves these pinned assets locally so authenticated clinical pages do not execute code or load fonts from third-party origins.

| Asset | Version | Upstream package | License copy |
|---|---:|---|---|
| Bootstrap | 5.3.3 | `bootstrap` | `patients/static/patients/vendor/bootstrap/5.3.3/LICENSE` |
| Freshworks Crayons | 4.1.0 | `@freshworks/crayons` | `patients/static/patients/vendor/crayons/4.1.0/LICENSE.md` |
| Freshworks Crayons icons | 4.2.0-beta.0 | `@freshworks/crayons-icon` | `patients/static/patients/vendor/crayons-icons/4.2.0-beta.0/LICENSE.md` |
| htmx | 1.9.12 | `htmx.org` | `patients/static/patients/vendor/htmx/1.9.12/LICENSE` |
| Chart.js | 4.4.4 | `chart.js` | `patients/static/patients/vendor/chartjs/4.4.4/LICENSE.md` |
| Inter | 5.2.8 | `@fontsource/inter` | `patients/static/patients/vendor/inter/5.2.8/LICENSE` |

Only the Inter Latin normal fonts at weights 400, 500, 600, and 700 are shipped. The Crayons loader and its local lazy-loaded chunks are retained because MEDTRACK uses the `fw-datepicker` component. Crayons' two built-in icon resolver URLs are rewritten to the pinned local icon directory so the datepicker does not call jsDelivr at runtime.

## Integrity gate

`WEB_VENDOR_INTEGRITY.json` records the SHA-256 of every file below `patients/static/patients/vendor`, plus each package archive URL, npm SHA-512 integrity value, version, and license path. CI exercises `patients.test_frontend_a11y.ThirdPartyAssetPinningTests`; the same byte and file-set check can be run directly:

```powershell
py -3 scripts\verify_web_vendor_integrity.py
```

Never regenerate the manifest merely to make a failing check green. Review the upstream archive, selected files, license, local changes, CSP behavior, and browser suite first; then regenerate it deliberately with `--write` in the same reviewed change.

## Reproducible extraction and local changes

1. In an empty temporary directory, fetch the exact archives with `npm pack bootstrap@5.3.3`, `npm pack @freshworks/crayons@4.1.0`, `npm pack @freshworks/crayons-icon@4.2.0-beta.0`, `npm pack htmx.org@1.9.12`, `npm pack chart.js@4.4.4`, and `npm pack @fontsource/inter@5.2.8`. Verify each downloaded archive with the npm SHA-512 value in `WEB_VENDOR_INTEGRITY.json` before extraction.
2. Extract each archive with `tar -xzf <archive>`. Copy Bootstrap `dist/css/bootstrap.min.css`, `dist/js/bootstrap.bundle.min.js`, and `LICENSE`; Crayons `dist/crayons`, `css/crayons-min.css`, and its license; all Crayons icon `dist/icons` SVGs and its license; htmx `dist/htmx.min.js` and `LICENSE`; Chart.js `dist/chart.umd.js` and `LICENSE.md`; and Inter's Latin normal WOFF2 files at weights 400, 500, 600, and 700 plus `LICENSE`.
3. Recreate `inter/5.2.8/inter.css` with one local `@font-face` per retained weight and no remote URL.
4. Apply the two intentional Crayons rewrites:
   - In `crayons/4.1.0/dist/crayons/p-2e817ac9.js`, replace the ESM `@freshworks/crayons-icon@next` jsDelivr resolver with `/static/patients/vendor/crayons-icons/4.2.0-beta.0/icons/${name}.svg`.
   - In `crayons/4.1.0/dist/crayons/p-92bb9b78.system.js`, replace the SystemJS icon base URL with `/static/patients/vendor/crayons-icons/4.2.0-beta.0/icons`.
5. Retain the MEDTRACK-authored `crayons-csp-loader.js`. It supplies native `import()` while the pinned Stencil bootstrap initializes, preventing its CSP-blocked `new Function` path from falling back to a blob module. The upstream `crayons.esm.js` remains byte-for-byte from the package.
6. Run `py -3 scripts\verify_web_vendor_integrity.py --write`, inspect the manifest diff, then run the verifier, Django tests, and the full Playwright matrix with console/CSP assertions.
