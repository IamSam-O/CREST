# CREST

CREST is a self-hosted exam practice app. Admins build exams from CSV question banks, users (or anonymous guests) take them solo with scoring and timed-bonus points, and hosts can run live multiplayer quiz sessions over WebSockets.

## Features

- **Exam practice** — single-choice and checkbox (multi-answer) questions, per-question points, optional images and answer explanations, and a configurable time-bonus window.
- **CSV import/export** — build or update an exam by uploading a CSV (template at [`public/template.csv`](public/template.csv)); re-uploading replaces an exam's question set wholesale. Question/option text is sanitized on import (`exams/sanitize.py`).
- **Access control** — exams are public by default, or restricted to specific groups; exam owners and admins can always manage their own exams.
- **Multiplayer** — a host starts a room for an exam, shares a room code/passcode, and guests join and play live without needing an account (`multiplayer/`, Django Channels + Redis).
- **Accounts & invites** — Django auth with email-based invites, forced password change on first login, and a personal API token for authenticated REST access.
- **Admin UI** — a `/manage/` console for managing exams, users, groups, invites, and SMTP settings (stored encrypted at rest, editable without a redeploy).
- **REST API** — documented via OpenAPI/Swagger at `/api/docs/`; gameplay endpoints (start/check/submit/progress, multiplayer host control) are session-only and intentionally excluded from token auth and the published spec.

## Tech stack

- **Backend**: Django 5 + Django REST Framework, Django Channels (ASGI, via Daphne) for WebSockets
- **Realtime**: Redis (Channels layer for multiplayer)
- **Database**: SQLite (file-based, stored under `data/`)
- **Frontend**: static single-page app served from `public/` (vanilla JS)
- **Docs**: drf-spectacular (OpenAPI schema + Swagger UI)

## Running locally (Docker)

The published image is the supported way to run CREST.

```bash
cp .env.example .env   # optional - defaults work for local use
docker compose up
```

This starts Redis and the app (`ghcr.io/iamsam-o/crest:latest`) on **http://localhost:3000**, persisting data to `./data`. On first boot the container generates a Django secret key, runs migrations, and collects static files.

See [`.env.example`](.env.example) for available environment variables, notably `DJANGO_CSRF_TRUSTED_ORIGINS` if you're putting CREST behind a reverse proxy on a public domain.

## Running from source

```bash
pip install -r requirements.txt
redis-server &          # required for multiplayer (Channels layer)
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
daphne -b 0.0.0.0 -p 3000 config.asgi:application
```

Useful environment variables (see [`config/settings.py`](config/settings.py)):

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev key | Django secret key |
| `DJANGO_DEBUG` | `0` | Set to `1` for debug mode |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | _(empty)_ | Comma-separated trusted origins behind a TLS-terminating proxy |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` | Channels layer connection |

SMTP credentials for invite/notification emails are configured from the admin UI (`/manage/` → Email Settings), not via environment variables.

## Project layout

```
accounts/      auth, invites, encrypted email settings, password-change middleware
exams/         exam/question/option models, CSV import/export, attempt scoring
multiplayer/   room lobby/host/play views + Channels consumer for live quizzes
adminui/       /manage/ console (DRF viewsets + API routes backing it)
config/        Django settings, URL root, ASGI/WSGI entrypoints
public/        static SPA frontend (served at /)
templates/     server-rendered pages (login, invites, multiplayer lobby/room)
```

## API docs

With the app running, interactive API docs are available at `/api/docs/` (schema at `/api/schema/`). Generate a personal token from the account page to authenticate requests; gameplay endpoints are intentionally session-only and not part of the published API.
