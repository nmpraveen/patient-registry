# patient-registry

A minimal Django + PostgreSQL MVP for authenticated patient entry and lookup, built to run entirely in Docker and reachable on your local network.

## Features

- Django built-in auth (`/login/`, `/logout/`)
- Patient CRUD pages (list, create, detail, edit)
- Search patients by name or phone from the list page
- PostgreSQL-backed persistence
- Admin registration for Patient records
- Bootstrap UI via CDN (no frontend build step)

## Stack

- Backend: Django (templates)
- Database: PostgreSQL
- Runtime: Docker + Docker Compose
- Config: environment variables via `django-environ`

## Quick start

1. Copy environment template:

```bash
cp .env.example .env
```

2. Build and run:

```bash
docker compose up --build
```

3. Apply migrations (if needed manually):

```bash
docker compose exec web python manage.py migrate
```

4. Create an admin user:

```bash
docker compose exec web python manage.py createsuperuser
```

5. Open:
- `http://localhost:8000`
- `http://<host-ip>:8000` (for LAN devices)

## Authentication

- Login page: `/login/`
- Logout endpoint: `/logout/`
- All patient pages require authentication.

## Patient routes

- List + search: `/patients/?q=<name-or-phone>`
- Create: `/patients/new/`
- Detail: `/patients/<id>/`
- Edit: `/patients/<id>/edit/`

## Admin

- Django admin: `/admin/`
- `Patient` is registered with list/search support.

## Environment variables

Required/important:

- `SECRET_KEY`: Django secret key (must be set)
- `DEBUG`: defaults to `False`
- `ALLOWED_HOSTS`: comma-separated hosts/IPs
- DB vars: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`

For LAN access, include your machine IP in `ALLOWED_HOSTS`, e.g.:

```env
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,192.168.1.42
```

If you hit CSRF origin checks while using a LAN IP, add:

```env
CSRF_TRUSTED_ORIGINS=http://192.168.1.42:8000
```

## Testing

Run tests in Docker:

```bash
docker compose exec web python manage.py test
```

## Notes

- Passwords are managed by Django auth and stored hashed.
- The database uses a named Docker volume: `postgres_data`.
- `web` binds to `0.0.0.0:8000` for LAN reachability.
