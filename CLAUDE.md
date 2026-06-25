# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local-first exam practice web app. Users import a CSV question bank, take randomized practice exams in a Kahoot/Quizizz-style UI (colored answer tiles, bonus-point timing, streak multiplier), review past attempts, edit questions, and resume in-progress exams. There is also a real-time multiplayer mode where a host runs a room and participants join via room code + passcode.

The backend was rewritten from Node/Express to **Django 5 + Django REST Framework**. The frontend (`public/`) is still a single-page vanilla JS app — no framework, no bundler — served as static files. Multiplayer views are Django HTML templates in `templates/multiplayer/`.

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

The Dockerfile CMD runs `migrate --noinput && collectstatic --noinput && daphne -b 0.0.0.0 -p 3000 config.asgi:application`. Daphne is the ASGI server that handles both HTTP and WebSocket. Port 3000 is kept for backwards compatibility with existing proxy configs.

## Architecture

### Backend apps

**`config/`** — Project-level settings and URL routing. `config/urls.py` is the single URL file: admin, accounts, multiplayer, and the DRF API routes are declared here, and a `_serve_frontend` catch-all at the bottom gates the SPA on authentication and serves `public/` via `django.views.static.serve`. `SECURE_PROXY_SSL_HEADER` is set for reverse-proxy deployments (Nginx Proxy Manager).

**Role model**: Three tiers, all backed by Django's built-in user/group/permission models — no custom role model. **Admins** (`is_staff=True` on `User`) get the full `/manage/` sidebar (Users, Groups, Invites, Email Settings, Attempts, Sessions, App Settings) and can edit any exam regardless of ownership. **Editors** (Django `Group` with `add_exam` + `view_exam` permissions) can create and own exams; the "Create Exam" card is hidden for non-editors. **Users** (Django `Group` with `view_exam` only) can take exams that are public or assigned to their group. Set this up via `/manage/` → Groups. The "Create Exam" card visibility in `app.js` is driven by `canCreateExam` from `GET /api/admin/manage/whoami/`. The backend gate is `_require_perm(request, 'exams.add_exam')` in `exams/views.py:exam_list`. Admin bypass of exam ownership uses `user.is_staff` directly (no helper function).

**`accounts/`** — Custom `User` (extends `AbstractUser`), group-based role system, invite flow, SMTP `EmailSettings` singleton (DB-backed with encrypted password field), `RequirePasswordChangeMiddleware`. Any authenticated user can call the API with a personal token (self-service via `my_token` at `/api/account/token/`, surfaced in Manage's "My Account" section) — token auth is not gated by a separate flag; every endpoint enforces the same ownership/permission rules regardless of auth method. `accounts/permissions.py` contains only:
- `NoTokenAuthOnGameplay` — hardcoded block on token auth for start/check/submit/progress and multiplayer host control endpoints.

`CsrfExemptSessionAuthentication` (also in `accounts/`) skips DRF's CSRF enforcement for the same-origin SPA — `SESSION_COOKIE_SAMESITE = 'Lax'` is the actual mitigation. Every PUT/POST from `app.js` is a plain same-origin `fetch()` with no `X-CSRFToken` header.

**`exams/`** — All single-player exam API. Every endpoint is a `@api_view` function in `exams/views.py`; no ViewSets. `exams/csv_io.py` has `parse_rows()` / `import_csv()` / `replace_exam_questions()` / `export_exam_to_csv()` — `OPTION_COLUMNS` in that file is the single source of truth for the max option count (6). `exams/sanitize.py` wraps `bleach` for server-side HTML sanitization of rich-text fields before DB writes. The key invariant: `/api/exams/<id>/start` **never sends `isCorrect`** to the client — only `/check` and `/submit` reveal correctness, and both recompute server-side.

**Exam ownership and visibility**: `Exam.owner` (nullable FK, `SET_NULL`) is set to the importing user at creation (`import_csv(..., owner=request.user)`); `Exam.allowed_groups` (M2M to `auth.Group`) is an access allowlist set at creation or from the exam's settings panel. `exams/views.py` has the two gate functions everything routes through: `_require_exam_owner` (owner or `user.is_staff` — gates delete/settings/CSV-reupload/question CRUD) and `_require_exam_access` (owner, staff, or member of any `allowed_groups`, or **anyone** if `allowed_groups` is empty — gates start/progress/check/submit/export/questions-GET, since those are reachable directly by id and would otherwise be an IDOR). `exam_list` GET resolves the visible exam-id set first, *then* annotates/queries — filtering and annotating in one queryset would join the `allowed_groups` M2M and inflate `question_count`. Each list item carries `can_edit` so `app.js` knows whether to render the pencil/delete controls; legacy exams with `owner=None` are still publicly visible (empty `allowed_groups`) but only staff can edit them until claimed.

**`multiplayer/`** — `MultiplayerConsumer(JsonWebsocketConsumer)` at `ws/multiplayer/<room_code>/`. A single consumer class handles both host and guest roles: role is set in memory on `handle_host_join` / `handle_guest_join`. The host must authenticate with `hostSecret` (URL token, also gates the Django view via `@login_required`). Guests only need the session `passcode`. `_maybe_auto_advance` fires after each guest answer **and** on guest disconnect and advances when all currently-`connected=True` participants have answered the current question — race-guarded via `session.refresh_from_db()` + index check. `_broadcast_question` strips `correctOptionIds` before broadcasting; `correctCount` is safe to send and drives the select-hint UI. `MultiplayerSession.time_limit_seconds` (0 = no limit) is set by the host at `handle_start` time and broadcast with every question as `timeLimit`; `play_room.html` runs a client-side countdown appended to the select-hint text and auto-submits via `submitBtn.click()` when it hits zero.

A host disconnecting mid-game flips the session to `PAUSED` (not ended) — guests get dropped to a waiting screen, and a reconnected host sees a "Resume" button that calls `handle_resume` to re-broadcast the current question fresh. Important gotcha: `self.session_obj` on the consumer is cached once at join time and **never** updated by `handle_start`/`handle_next`/`handle_resume` (they each fetch their own local copy) — anything that needs the session's real current state (like `disconnect()`'s pause check) must re-query via `self._get_session()` rather than trusting `self.session_obj`. `_finish()` (called on `handle_end` and the natural last-question advance) deletes the `MultiplayerSession` row entirely rather than just marking it `FINISHED` — ended sessions aren't reviewed later, so the room code is freed immediately; it's race-guarded via an atomic `filter(pk=...).delete()` so a simultaneous final answer from two participants can't double-broadcast an empty leaderboard.

**`adminui/`** — A custom-built replacement for Django admin's UI (`/manage/`), styled to match the app instead of Django's default chrome, with client-side section switching (`adminui/static/adminui/admin.js`, same `api()`/router pattern as `public/app.js`) backed by DRF `ModelViewSet`s under `/api/admin/manage/`. The page itself is just `login_required` — **every** authenticated user can reach `/manage/` for the "My Account" → API Token section — but the sidebar has three tiers, each gated separately both client-side (hidden sections) and server-side (real permission classes, since hiding a button is not access control):
- **My Account** (everyone): API Token only.
- **Manage** (`IsAdminUser` / `is_staff`): Attempts, Multiplayer Sessions, App Settings.
- **Admin** (`IsManageAdmin` / `is_admin_user` — see `accounts/permissions.py`): Users, Groups+`RoleSettings`+permissions, Invites, Email Settings, plus links to API Docs and Django Admin.

`GET /api/admin/manage/whoami/` (any authenticated user) reports `{isStaff, isAdmin}` so `admin.js` knows which sidebar groups to reveal and which section to default to. `InviteViewSet.perform_create` replicates the email-send side effect from the old `accounts/admin.py:InviteAdmin.save_model` exactly. There is **no Exams section** — exam content/ownership is managed entirely from the Library now (see "Exam ownership and visibility" above); Manage only keeps a read-only `exam_options_view` to resolve the Exam column/select on Attempts and Multiplayer Sessions. Django admin (`/admin/`) is left fully intact as the escape hatch for anything not covered here (e.g. editing a live `MultiplayerSession`'s `room_code`/`passcode`/`host_secret`, which this UI deliberately doesn't expose since it'd break an in-progress game).

### Frontend

**`public/`** — Unchanged from the Node era. `index.html` is the SPA shell; every screen is a `<section id="view-...">` toggled with Bootstrap's `d-none`. `app.js` is one file: `showView(name)` is the entire router; `takeState` holds all in-exam state. `styles.css` drives the dark/light theme via CSS custom properties — always prefer an existing variable over a hardcoded color. The palette is intentionally navy/teal (not purple/gold). DOMPurify (CDN) sanitizes all rich-text before `innerHTML` assignment.

**`templates/`** — Django templates used only by multiplayer pages. `_head.html` is the shared `<head>` include (Bootstrap, Nunito, DOMPurify CDNs). `_quiz_base.html` is a base template whose game-screen HTML is a verbatim copy of single-player's `#view-take` section — same element IDs (`take-points`, `take-multiplier`, `take-progress-bar`, `take-bonus-bar`, `take-progress`, `take-question-text`, `take-image`, `take-select-hint`, `take-options`, `take-feedback`) so all CSS rules apply without any multiplayer-specific overrides. `status_area` and `extra_game` template blocks render **outside** `#view-game` so they don't consume flex space from the tile grid. `multiplayer/play_room.html` extends `_quiz_base.html` and overrides `{% block actions %}` with a Submit button; the JS manages tile toggle-selection, points computation, and WebSocket communication.

### camelCase API convention

`djangorestframework-camel-case` is installed and set as the default renderer/parser. All JSON keys between DRF and the client are automatically converted: `question_text` in Python → `questionText` in JSON and vice versa. This applies to both request bodies and responses. `app.js` and the multiplayer templates were written expecting camelCase.

### Scoring model

Each question has a base `points` value. Each exam has `bonus_window_seconds` (default 30, per-exam not global — changing it mid-attempt would apply inconsistently). Answering correctly inside the bonus window adds a time-scaled bonus; a correct-answer streak multiplies points, capped at 30x (`MULTIPLIER_MAX`). Computed client-side in `app.js` (`computeAwardedPoints`) and sent as `pointsAwarded` — the server trusts this value, clamped to ≥ 0. In multiplayer, the same formula runs in `play_room.html` and is sent with the WebSocket `answer` message; `consumers.py` trusts the claim in `handle_answer`.

Active-time tracking (single-player): the bonus window counts down only while the user is looking at the question. `takeState.elapsedSeconds` (Map of committed seconds, persisted server-side) + `takeState.activeSince` (in-memory burst start timestamp) implement this. `pauseBonusTracking()` / `resumeBonusTracking()` are called on `visibilitychange` and view transitions.

### Resume-in-progress

`InProgressAttempt` has a unique constraint on `(exam, user)` — one row per exam per user, upserted on every interaction. `app.js`'s `saveProgress()` PUTs to `/api/exams/<id>/progress` after every tile select, check, and navigation. Cleared on `/submit`, exam delete (CASCADE), or CSV bulk-replace (stale question IDs). The Library view derives the displayed in-progress score from `InProgressAttempt.checked_json`, not from `Attempt` (which only has completed runs).

### CSV import

Three paths into the questions table: the question editor (validated via `validateQuestionPayload`), `import_csv()` for new exams (unvalidated — a blank `Correct Answer` imports as zero-correct), and `replace_exam_questions()` for CSV re-upload (same unvalidated path). Re-upload cascade-deletes historical `AttemptAnswer` rows — known accepted tradeoff. `OPTION_COLUMNS` in `exams/csv_io.py` is the single source of truth for the 6-option limit.

### Rich text and sanitization

`question_text`, `option_text`, and `explanation` store Quill-authored HTML. Server-side: `exams/sanitize.py` (bleach) sanitizes before DB writes. Client-side: DOMPurify sanitizes before every `innerHTML` assignment — applies in `app.js`, in multiplayer tile rendering, and anywhere else these columns render. The Quill "empty" state (`<p><br></p>`) is normalized to `''` before sending via `quillValue(quill)` in `app.js`.

### Global settings vs. per-exam settings

`AppSettings` singleton covers `theme`, `soundEffectsEnabled`, `maxInProgressInstances`. Every PUT to `/api/settings` must send all three fields — partial updates aren't supported. `bonus_window_seconds` is per-exam only (on the `Exam` model), not in `AppSettings` — this is intentional.

### Design / style guidelines

**Theming**: every color is a CSS custom property defined on `:root` in `public/styles.css` (shared by `public/` and all Django templates via `<link rel="stylesheet" href="/styles.css">` in `_head.html`), re-declared on `body.theme-light` for the light variant. Never hardcode a color — use an existing `--var` or add one to both blocks. The palette is navy/teal (`--accent-primary: #1f7a8c`) with amber as the secondary accent (`--accent-secondary: #f5a623`) — not purple/gold. Theme toggling is a single class swap (`body.classList.toggle('theme-light')`), wired to `#nav-theme-toggle` everywhere it appears.

**Navbar**: `templates/_navbar.html` is the one shared navbar for all Django-templated pages (multiplayer, email settings, Manage) — include it with `{% include "_navbar.html" %}` rather than hand-rolling another `<nav>`. The SPA (`public/index.html`) has its own near-identical inline navbar since it isn't a Django template; keep the two in sync by eye if one changes.

**Buttons**: solid colors (`btn-primary`, `btn-danger`, `btn-warning`) are reserved for the primary action in a given row/card and for edit/delete icon-only buttons (pencil = `btn-primary`, trash = `btn-danger`) — this convention must stay consistent across every table/list (Library exam list, in-progress attempts, Manage's resource tables, Groups table). `btn-outline-secondary` is for secondary/navigational actions (nav links, "Back", "Cancel", non-destructive utility buttons like history/export). Icons are Bootstrap Icons (`bi-*`); an icon-only button always gets a `title` attribute for accessibility.

**Manage (`/manage/`) layout**: a grouped sidebar (`templates/adminui/index.html`), not a flat row of buttons — the three groups are "My Account", "Manage" (`#manage-group-staff`), and "Admin" (`#manage-group-admin`), the latter two `d-none` by default and revealed by `initManage()` after it calls `whoami/`. New sections should join one of these existing groups by role tier rather than growing a new top-level row. The active section uses Bootstrap's `.list-group-item.active`, themed via the `--accent-primary` override in `styles.css` (Bootstrap's default active state is blue and clashes with the palette). Exam *content and ownership* are intentionally **not** managed from Manage at all — that's the Library's job (`public/app.js`'s Quill-based `openQuestionEditor` plus the owner/group controls on Create Exam and the exam-settings panel).

**Modals**: Bootstrap modals via `bootstrap.Modal.getOrCreateInstance(modalEl)`, never `new bootstrap.Modal(...)` directly (avoids creating duplicate instances on repeated opens). Any Django template that opens a Bootstrap modal must load `bootstrap.bundle.min.js` itself — `_head.html` only loads Bootstrap's CSS, not its JS bundle (a missing-bundle bug already cost a debugging session once in `adminui`).
