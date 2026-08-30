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
