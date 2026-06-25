# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CREST (Collaborative Rich-text Exam Self-hosted Tool) — a self-hosted exam practice web app. Users import a CSV question bank, take randomized practice exams in a Kahoot/Quizizz-style UI (colored answer tiles, bonus-point timing, streak multiplier), review past attempts, edit questions, and resume in-progress exams. There is also a real-time multiplayer mode where a host runs a room and participants join via room code + passcode.

Backend: **Django 5 + Django REST Framework**. Frontend (`public/`): single-page vanilla JS app — no framework, no bundler — served as static files. Multiplayer views are Django HTML templates in `templates/multiplayer/`.

## Commands

```bash
# Primary: Docker (requires ./data/ to persist the SQLite DB; Redis runs as a sidecar)
cp .env.example .env          # fill in DJANGO_SECRET_KEY at minimum
docker compose up --build

# Local dev (single-player works without Redis; multiplayer WebSocket won't)
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver    # serves on http://localhost:8000

# Schema changes always go through migrations — no manual column-add helpers
python manage.py makemigrations
python manage.py migrate

# Syntax check (no test framework configured)
python -m py_compile <file>.py
node --check public/app.js
```

The Dockerfile CMD runs `migrate --noinput && collectstatic --noinput && daphne -b 0.0.0.0 -p 3000 config.asgi:application`. Daphne handles both HTTP and WebSocket. Port 3000 is kept for backwards compatibility with existing proxy configs.

## Architecture

### Backend apps

**`config/`** — Project settings and URL routing. `config/urls.py` is the single URL file: admin, accounts, multiplayer, DRF API routes, and a `_serve_frontend` catch-all that gates the SPA on authentication and serves `public/` via `django.views.static.serve`. `SECURE_PROXY_SSL_HEADER` is set for reverse-proxy deployments (Nginx Proxy Manager). `config/schema_hooks.py` is a drf-spectacular postprocessing hook that injects standard error responses (400/401/403/404) into every operation.

**Authentication**: `DEFAULT_AUTHENTICATION_CLASSES` is `TokenAuthentication` only. `CsrfExemptSessionAuthentication` (in `accounts/authentication.py`) is applied explicitly only to the four gameplay views (`exam_start`, `exam_progress`, `question_check`, `exam_submit`) and to `my_token` — nowhere else. The API docs (`/api/docs/`) are publicly accessible; the token is required to actually execute methods. `SESSION_COOKIE_SAMESITE = 'Lax'` is the CSRF mitigation for same-origin SPA calls.

**Role model**: Two tiers, backed entirely by Django's built-in user/group/permission models — no custom role model. **Staff** (`is_staff=True`) get the full `/manage/` sidebar (Users, Groups, Invites, Email Settings, Attempts, Sessions, App Settings) and can edit any exam regardless of ownership. **Editors** (Django `Group` with `add_exam` + `view_exam` permissions) can create and own exams. **Users** (`view_exam` only) can take exams that are public or assigned to their group. All `/api/admin/manage/` viewsets use DRF's built-in `IsAdminUser` permission class (checks `is_staff`).

**`accounts/`** — Custom `User` (extends `AbstractUser`), group-based role system, invite flow, SMTP `EmailSettings` singleton (DB-backed with `EncryptedCharField` password, keyed by `SECRET_KEY`), `RequirePasswordChangeMiddleware`. `accounts/permissions.py` contains only `NoTokenAuthOnGameplay` — hardcoded block on token auth for start/check/submit/progress endpoints ("API can do everything except take tests").

**`exams/`** — All single-player exam API. Every endpoint is a `@api_view` function; no ViewSets. `exams/csv_io.py` has `parse_rows()` / `import_csv()` / `replace_exam_questions()` / `export_exam_to_csv()` — `OPTION_COLUMNS` is the single source of truth for the 6-option limit. `exams/sanitize.py` wraps `bleach` for server-side HTML sanitization. The key invariant: `/api/exams/<id>/start` **never sends `isCorrect`** — only `/check` and `/submit` reveal correctness, and both recompute server-side.

**Exam ownership and visibility**: `Exam.owner` (nullable FK, `SET_NULL`) set at import time; `Exam.allowed_groups` (M2M to `auth.Group`) is the access allowlist. Two gate functions in `exams/views.py`: `_require_exam_owner` (owner or `is_staff` — gates delete/settings/CSV-reupload/question CRUD) and `_require_exam_access` (owner, staff, member of any `allowed_groups`, or anyone if `allowed_groups` is empty — gates start/progress/check/submit). `exam_list` GET resolves visible exam IDs first, then annotates — joining `allowed_groups` M2M and annotating in one queryset inflates `question_count`. Each list item carries `can_edit`.

**`multiplayer/`** — `MultiplayerConsumer(JsonWebsocketConsumer)` at `ws/multiplayer/<room_code>/`. One consumer class handles both host and guest roles, set in memory on `handle_host_join` / `handle_guest_join`. `_maybe_auto_advance` fires after each guest answer and on disconnect, advancing when all `connected=True` participants have answered — race-guarded via `session.refresh_from_db()`. `self.session_obj` is cached once at join and never updated by subsequent handlers; anything needing current session state must call `self._get_session()`. `_finish()` deletes the `MultiplayerSession` row entirely (room code freed immediately), race-guarded via atomic `filter(pk=...).delete()`. A host disconnect flips the session to `PAUSED`; reconnection calls `handle_resume`.

**`adminui/`** — Custom `/manage/` UI backed by DRF `ModelViewSet`s under `/api/admin/manage/`. The `manage/` path is registered directly in `config/urls.py` (no `adminui/urls.py`). The page is `login_required` — every user reaches it for the "My Account" API Token section. `GET /api/admin/manage/whoami/` returns `{isStaff, canCreateExam}`: `admin.js` uses `isStaff` to reveal `#manage-group-staff` (the staff-only sidebar group) and `canCreateExam` to show the Library's "Create Exam" card.

### Frontend

**`public/`** — `index.html` is the SPA shell; every screen is a `<section id="view-...">` toggled with `d-none`. `app.js` is one file: `showView(name)` is the entire router; `takeState` holds all in-exam state. `styles.css` drives dark/light theme via CSS custom properties — always prefer an existing `--var` over a hardcoded color. DOMPurify (CDN) sanitizes all rich-text before `innerHTML` assignment.

**`templates/`** — Django templates for multiplayer pages and `/manage/`. `_head.html` is the shared `<head>` include (Bootstrap CSS, Nunito, DOMPurify CDNs — **not** Bootstrap JS; templates that open modals must load `bootstrap.bundle.min.js` themselves). `_navbar.html` is the one shared navbar; include it with `{% include "_navbar.html" %}`. `_quiz_base.html` is the multiplayer game base template — its game-screen element IDs (`take-points`, `take-multiplier`, etc.) are intentionally identical to single-player's `#view-take` so all CSS applies without overrides.

### camelCase API convention

`djangorestframework-camel-case` is the default renderer/parser. All JSON keys are auto-converted: `question_text` in Python → `questionText` in JSON. Applies to both requests and responses. `app.js` and multiplayer templates expect camelCase.

### Scoring model

Each question has a base `points` value. Each exam has `bonus_window_seconds` (default 30, per-exam not global). Correct answer inside the bonus window adds a time-scaled bonus; a streak multiplies points, capped at `MULTIPLIER_MAX` (30×). Computed client-side in `app.js` (`computeAwardedPoints`) and sent as `pointsAwarded` — the server trusts this value, clamped to ≥ 0. Same formula runs in `play_room.html` for multiplayer.

Active-time tracking: the bonus window counts down only while the tab is visible. `takeState.elapsedSeconds` (Map of committed seconds, persisted server-side) + `takeState.activeSince` (in-memory burst timestamp). `pauseBonusTracking()` / `resumeBonusTracking()` fire on `visibilitychange` and view transitions.

### Resume-in-progress

`InProgressAttempt` has a unique constraint on `(exam, user)` — one row per exam per user, upserted on every interaction. `saveProgress()` PUTs to `/api/exams/<id>/progress` after every tile select, check, and navigation. Cleared on `/submit`, exam delete (CASCADE), or CSV re-upload (stale question IDs). The Library derives the in-progress score from `InProgressAttempt.checked_json`, not from `Attempt`.

### CSV import

Three paths into the questions table: the question editor (validated via `validateQuestionPayload`), `import_csv()` for new exams (unvalidated), and `replace_exam_questions()` for CSV re-upload (same unvalidated path, cascade-deletes historical `AttemptAnswer` rows). `OPTION_COLUMNS` in `exams/csv_io.py` is the single source of truth for the 6-option limit.

### Rich text and sanitization

`question_text`, `option_text`, and `explanation` store Quill-authored HTML. Server-side: `exams/sanitize.py` (bleach). Client-side: DOMPurify before every `innerHTML` assignment. The Quill "empty" state (`<p><br></p>`) is normalized to `''` via `quillValue(quill)` in `app.js` before sending.

### Global settings vs. per-exam settings

`AppSettings` singleton (in `exams/models.py`, same `get_solo()` pattern as `EmailSettings`) covers `theme`, `soundEffectsEnabled`, `maxInProgressInstances`. Every PUT to `/api/settings` must send all three fields — partial updates aren't supported. `bonus_window_seconds` is per-exam only — intentionally not in `AppSettings`.

### Design / style guidelines

**Theming**: every color is a CSS custom property on `:root` in `public/styles.css`, re-declared on `body.theme-light`. Never hardcode a color. Palette: navy/teal (`--accent-primary: #1f7a8c`), amber secondary (`--accent-secondary: #f5a623`). Theme toggle: `body.classList.toggle('theme-light')` on `#nav-theme-toggle`.

**Navbar**: `templates/_navbar.html` for all Django-templated pages; `public/index.html` has its own inline navbar — keep them in sync by eye when one changes.

**Buttons**: `btn-primary` / `btn-danger` / `btn-warning` for primary actions and edit/delete icon buttons (pencil = `btn-primary`, trash = `btn-danger`). `btn-outline-secondary` for secondary/navigational actions. Bootstrap Icons (`bi-*`); icon-only buttons always get a `title` attribute.

**Manage (`/manage/`) layout**: grouped sidebar — "My Account" (everyone) and "Manage" (`#manage-group-staff`, revealed for `is_staff` users). The active section uses `.list-group-item.active` styled via `--accent-primary`. Exam content/ownership is managed from the Library, not Manage.

**Modals**: `bootstrap.Modal.getOrCreateInstance(modalEl)`, never `new bootstrap.Modal(...)` — avoids duplicate instances on repeated opens.
