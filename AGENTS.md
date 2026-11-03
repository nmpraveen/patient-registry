# MEDTRACK
- Django/PostgreSQL case follow-up tracker, not an EHR. Maintained target: web and responsive mobile web. Android is deprecated and is not a web acceptance gate.
- Preserve patient identity/aliases, stale-edit protection, role scope, audit and recovery guarantees. Enforce authorization server-side. Never put real patient data in fixtures, screenshots, logs or examples; never commit secrets.
- Keep case/task/permission changes explicit and scoped. New theme tokens must appear in Theme settings; patient-data workflows need seed_mock_data support.
- For a requested GitHub push, use a codex/ feature branch and PR unless the user explicitly directs a main-branch push. Preserve unrelated work and local helper files; use current Git membership instead of old local-only lists.
- When pushing user-visible/shipped-code changes, update VERSION to the current UTC year.month.day.hours.min and prepend matching CHANGELOG notes. Documentation-only housekeeping does not require a release version.
- Consult PROJECT_CONTEXT.md for current work; README.md for repository workflow, MAC_DEVELOPMENT.md for Mac execution, API_CONTRACT.md for API changes, RUNBOOK.md for production/backup/restore.
- Verify affected behavior: model changes need migrations and disposable-database validation; run relevant tests and smoke-check changed pages. Production migration is a separate operation.
- Do not add ingestion/uploads without storage, access, retention and audit design.
- Update the relevant state/runbook when meaningful facts change. Do not ask the user to remind Codex or rewrite every status document after each task.
