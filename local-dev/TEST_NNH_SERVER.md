# Test NNH server

- Name: `Test NNH server`
- URL: `http://localhost:8000`
- Login: `admin` / `pass`
- Demo DB: Docker volume `test_nnh_state` mounted at `/state/test-nnh.sqlite3`
- Start or reuse: `.\local-dev\test-nnh-up.ps1`
- Stop: `.\local-dev\test-nnh-stop.ps1`
- Status: `.\local-dev\test-nnh-status.ps1`

Notes:
- This workflow is local-only and must not be used for public or shared environments.
- The local scripts start Docker Compose with `docker-compose.yml` plus `docker-compose.dev.yml`, and they also include a private `docker-compose.override.yml` automatically if you have one locally.
- Every start runs migrations, recreates the local admin user, resets the demo database content, and reseeds mock data.
- The reset-and-reseed behavior applies only to the `test_nnh_state` demo database, not to `local-dev.sqlite3`.
