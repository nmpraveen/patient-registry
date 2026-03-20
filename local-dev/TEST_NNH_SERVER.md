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
- `.\local-dev\test-nnh-up.ps1` now auto-detects the machine's IPv4 LAN addresses and injects them into `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` for the local-only Test NNH server, so phones on the same network can open the app at `http://<your-lan-ip>:8000`.
- Every start runs migrations, recreates the local admin user, resets the demo database content, and reseeds mock data.
- The reset-and-reseed behavior applies only to the `test_nnh_state` demo database, not to `local-dev.sqlite3`.
