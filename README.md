# CREST

CREST is a self-hosted exam practice app. Editors/admins import question banks from CSV and configure exams (draw size, optional category-weighted sampling, grade scales) on top of them; registered users take exams solo with scoring, timed-bonus points, and letter grades; and hosts can run live multiplayer quiz sessions that anonymous guests can join over WebSockets.

## About this project

This is a personal project, and generative AI was used extensively in its development. Every effort has been made to keep the implementation simple and to apply reasonable security measures, but it is provided **as-is, with no warranty of any kind**. Issues and feature requests will not be resolved or supported. The project is open source under [MIT + Commons Clause](LICENSE) — free to clone, modify, and self-host with attribution, but not for commercial use (selling the software or services substantially derived from it).

## Features

### Question banks & exams
- A **question bank** is a pool of single-choice and checkbox (multi-answer) questions with per-question points, optional categories, images, and rich-text answer explanations (edited with Quill, rendered safely via DOMPurify). Banks are imported/exported as CSV (template at [`frontend/public/template.csv`](frontend/public/template.csv)); re-importing replaces a bank's questions wholesale. Question/option text is sanitized server-side on import (`exams/sanitize.py`, `bleach`).
- An **exam** is a reusable, named configuration drawn from a bank: how many questions to draw, an optional per-category weighting for sampling (the remainder is filled proportionally from the rest of the pool), a time-bonus window for fast correct answers, and an optional grade scale.
- An **exam instance** is one completed attempt at an exam — score, points (base + time-bonus), percent correct, and (if a grade scale applies) a letter grade. In-progress attempts are persisted so a user can resume later, and each instance can be drilled into question-by-question, exported as a CSV of just the missed questions, or used to spin up a brand-new bank + exam containing only the questions that were missed.

### Grading & review
- **Grade scales** are admin-defined ordered thresholds (e.g. `>= 90 → A`, `>= 80 → B`, …) evaluated against an instance's percent-correct to produce a letter grade at submission time.
- A staff **re-evaluate** action lets an admin recompute (or clear) a past instance's grade — e.g. after editing a scale — and requires a note; every change is appended to a per-instance grade-change log rather than overwriting history.

### Access control
- Exams are visible to everyone by default, or can be restricted to specific Django groups. Owners (the user who created a bank/exam) and staff/admins can always manage their own, independent of group restrictions.
- A dedicated `exams.add_exam` permission (assignable per-group from the admin UI) is what makes a regular user an "editor" able to create/manage banks and exams, separate from full Django staff/admin status.

### Multiplayer
- A host starts a room for any exam and shares a room code + passcode; guests join live **without needing an account** — the passcode is the only gate (`multiplayer/`, Django Channels + Redis).
- Host-paced lockstep protocol over a WebSocket: the host explicitly starts/advances/ends the round, but a question also auto-advances once every connected guest has answered. The session auto-pauses if the host disconnects, and the host can resume. A live leaderboard is broadcast to all participants.

### Accounts & invites
- Django auth with email-based invites (admin sends an invite to an email + optional group; the recipient sets their own password to accept it), forced password change on first login for invited accounts, and a personal API token for authenticated REST access.
- SMTP credentials for invite/notification emails are stored in the database (not env vars) and the password is encrypted at rest using a key derived from `SECRET_KEY` (`accounts/crypto.py`, Fernet) — editable from the admin UI without a redeploy.

### Admin UI
- A `/manage/` console (separate from Django's built-in `/admin/`) for managing question banks, exams, grade scales, users, groups/permissions, invites, multiplayer sessions, and SMTP settings.

### REST API
- Documented via OpenAPI/Swagger at `/api/docs/`. Most endpoints work with a personal token; gameplay endpoints (start/check/submit/progress, multiplayer host control) are deliberately session-only — token auth is hard-rejected on them regardless of permissions (`accounts/permissions.NoTokenAuthOnGameplay`) — and excluded from the published spec.

## Tech stack

**Backend**
- [Django 5](https://www.djangoproject.com/) + [Django REST Framework](https://www.django-rest-framework.org/) for the HTTP API and admin console
- [Django Channels](https://channels.readthedocs.io/) (ASGI, served by [Daphne](https://github.com/django/daphne)) for the multiplayer WebSocket protocol
- [Redis](https://redis.io/) as the Channels layer backing multiplayer pub/sub
- [SQLite](https://www.sqlite.org/) as the database (file-based, stored under `data/`)
- [`bleach`](https://github.com/mozilla/bleach) for server-side HTML sanitization of question/answer content; [`cryptography`](https://cryptography.io/) (Fernet) for at-rest encryption of SMTP credentials
- [`whitenoise`](https://whitenoise.readthedocs.io/) for serving the built frontend's static assets

**Frontend** (`frontend/`)
- [Vue 3](https://vuejs.org/) SPA built with [Vite](https://vitejs.dev/), [Vue Router](https://router.vuejs.org/), and [Pinia](https://pinia.vuejs.org/) for state
- [Bootstrap 5](https://getbootstrap.com/) for UI components/layout
- [Quill](https://quilljs.com/) for rich-text editing of questions/explanations, sanitized for display with [DOMPurify](https://github.com/cure53/DOMPurify)
- Built to `public/` and served by Django as static files — no separate frontend server in production

**Docs**
- [drf-spectacular](https://drf-spectacular.readthedocs.io/) generates the OpenAPI schema and Swagger UI

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
