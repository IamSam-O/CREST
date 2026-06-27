# CREST

CREST is a self-hosted exam practice app. Editors/admins import question banks from CSV and configure exams (draw size, optional category-weighted sampling, grade scales) on top of them; registered users take exams solo with scoring, timed-bonus points, and letter grades; and hosts can run live multiplayer quiz sessions that anonymous guests can join over WebSockets.

## About this project

This is a personal project, and generative AI was used extensively in its development. Every effort has been made to keep the implementation simple and to apply reasonable security measures, but it is provided **as-is, with no warranty of any kind**. Issues and feature requests will not be resolved or supported. The project is open source under [MIT + Commons Clause](LICENSE) — free to clone, modify, and self-host with attribution, but not for commercial use (selling the software or services substantially derived from it).

## Features

- **Question banks** — single-choice and checkbox (multi-answer) questions with per-question points, optional categories, images, and answer explanations. Imported/exported as CSV (template at [`frontend/public/template.csv`](frontend/public/template.csv)); re-importing replaces a bank's question set wholesale. Question/option text is sanitized on import (`exams/sanitize.py`).
- **Exams** — a reusable, configurable draw on top of a question bank: draw size, an optional per-category weighting for sampling (remainder filled proportionally from the full pool), a time-bonus window, and an optional grade scale.
- **Grade scales** — admin-defined thresholds (e.g. `>= 90 → A`) that compute a letter grade on submission; an admin "re-evaluate" action recomputes a past attempt's grade (with an audit log) if the scale changes later.
- **Access control** — exams are public by default, or restricted to specific groups; exam/bank owners and admins can always manage their own.
- **Multiplayer** — a host starts a room for an exam, shares a room code/passcode, and guests join and play live without needing an account (`multiplayer/`, Django Channels + Redis).
- **Accounts & invites** — Django auth with email-based invites, forced password change on first login, and a personal API token for authenticated REST access.
- **Admin UI** — a `/manage/` console for managing banks, exams, grade scales, users, groups, invites, and SMTP settings (stored encrypted at rest, editable without a redeploy).
- **REST API** — documented via OpenAPI/Swagger at `/api/docs/`; gameplay endpoints (start/check/submit/progress, multiplayer host control) are session-only and intentionally excluded from token auth and the published spec.

## Tech stack

- **Backend**: Django 5 + Django REST Framework, Django Channels (ASGI, via Daphne) for WebSockets
- **Realtime**: Redis (Channels layer for multiplayer)
- **Database**: SQLite (file-based, stored under `data/`)
- **Frontend**: Vue 3 SPA (`frontend/`) — Vite, Vue Router, Pinia, Bootstrap 5, Quill (rich-text question/explanation editing), DOMPurify — built to `public/` and served by Django as static files
- **Docs**: drf-spectacular (OpenAPI schema + Swagger UI)

## Running locally (Docker)

The published image is the supported way to run CREST.

```bash
cp .env.example .env   # optional - defaults work for local use
docker compose up
```

This starts Redis and the app (`ghcr.io/iamsam-o/crest:latest`) on **http://localhost:3000**, persisting data to `./data`. The image is built in two stages — a Node 20 stage compiles the Vue frontend (`frontend/`) into `public/`, then the Python stage serves it — so nothing needs to be built locally to use the image. On first boot the container generates a Django secret key (saved to `data/.secret_key`, not configured via env), runs migrations, and collects static files.

See [`.env.example`](.env.example) for available environment variables, notably `DJANGO_CSRF_TRUSTED_ORIGINS` if you're putting CREST behind a reverse proxy on a public domain.

## Running from source

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..   # builds the Vue SPA into public/
redis-server &          # required for multiplayer (Channels layer)
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
daphne -b 0.0.0.0 -p 3000 config.asgi:application
```

For frontend development with hot reload, run `python manage.py runserver 8000` alongside `cd frontend && npm run dev` (Vite on `:5173`, proxying `/api`, `/accounts`, `/manage`, `/multiplayer`, and `/ws` to `:8000` — see `frontend/vite.config.js`).

Useful environment variables (see [`config/settings.py`](config/settings.py)):

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | `0` | Set to `1` for debug mode |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | _(empty)_ | Comma-separated trusted origins behind a TLS-terminating proxy |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` | Channels layer connection |

The Django secret key is not set via environment variable — it's generated on first run and persisted to `data/.secret_key`. SMTP credentials for invite/notification emails are configured from the admin UI (`/manage/` → Email Settings), not via environment variables.

## Project layout

```
accounts/      auth, invites, encrypted email settings, password-change middleware
exams/         bank/exam/instance models, sampling + grading logic, CSV import/export
multiplayer/   room lobby/host/play views + Channels consumer for live quizzes
adminui/       /manage/ console (DRF viewsets + API routes backing it)
config/        Django settings, URL root, ASGI/WSGI entrypoints
frontend/      Vue 3 SPA source (Vite project; builds into public/)
public/        built frontend output, served by Django at /
templates/     server-rendered pages (login, invites, multiplayer lobby/room)
```

## API docs

With the app running, interactive API docs are available at `/api/docs/` (schema at `/api/schema/`). Generate a personal token from the account page to authenticate requests; gameplay endpoints are intentionally session-only and not part of the published API.
