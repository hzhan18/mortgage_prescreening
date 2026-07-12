# Mortgage Pre-Qualification (MVP)

A guided, bilingual (English/Chinese) mortgage pre-screening flow that realtors and
mortgage brokers can send to clients as a personal link. The client answers a short,
conversational set of questions, optionally uploads an income document (read
automatically), enters a property address (looked up automatically where possible),
and gets an instant GDS/TDS-based pre-qualification estimate. A summary is saved for
the broker.

## How it's organized

```
app.py              Flask routes (pages + API endpoints + admin list)
config.py            Reads settings from environment variables / .env
extensions.py         Shared SQLAlchemy instance
models.py             Broker and Lead database tables
calculations.py       GDS/TDS mortgage qualification math (pure Python, unit-testable)
ai_service.py         All calls to the Anthropic API (income doc reading, property lookup)
templates/
  assessment.html      The client-facing conversational flow
  admin.html           Simple broker list / link lookup page
static/
  css/style.css
  js/assessment.js      All the front-end flow logic; calls our own backend, never Anthropic directly
  i18n/en.json, zh.json  All UI strings — add more languages by adding another file + a button
```

## Setup (first time)

1. **Install Python 3.10+** if you don't have it, and open this folder in VS Code.

2. **Create a virtual environment** (VS Code will usually offer to do this for you —
   accept it, or run manually in the VS Code terminal):
   ```
   python -m venv venv
   ```
   Activate it:
   - macOS/Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`

3. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

4. **Configure secrets**: copy `.env.example` to `.env` and fill in:
   - `ANTHROPIC_API_KEY` — from https://console.anthropic.com/
   - `FLASK_SECRET_KEY` — any random string
   - `ADMIN_TOKEN` — any random string (protects the `/admin` broker list)

5. **Create the database** (SQLite file, created automatically on first run — nothing
   to do here, `app.py` calls `db.create_all()` at startup).

6. **Run it**:
   ```
   flask run
   ```
   or, using the built-in runner:
   ```
   python app.py
   ```
   Visit `http://127.0.0.1:5000/` — it'll redirect to `/admin` (use `?token=...` from
   your `.env`).

## Creating a broker's link

Each realtor/broker gets their own unique link. Create one from the terminal:

```
flask create-broker
```

It'll prompt for a name and (optional) email, then print a link like:

```
http://127.0.0.1:5000/b/john-smith-a1b2c3
```

That's the exact URL to send to that broker's clients. The landing page will greet
clients with "**John Smith** invited you to a quick mortgage readiness check" (or the
Chinese equivalent, depending on the language they pick).

You can see all brokers and how many leads each has at `/admin?token=YOUR_ADMIN_TOKEN`.

## Notes on the AI features

- **Income document reading** sends the uploaded file to Claude (vision) and asks for
  annualized gross income, employer, and a confidence rating. The client always sees
  and can edit the extracted number before continuing — nothing is auto-submitted
  without a chance to correct it.
- **Property lookup** uses Claude's web search tool to try to find a list price,
  property tax, and condo fees for a given address. This is a best-effort general web
  search, **not** a licensed MLS/CREA data feed — expect it to miss some addresses,
  especially off-market ones or awkward unit-number formats. For a production version
  with reliable coverage, look at CREA's DDF (requires brokerage membership) or a
  paid provider like Repliers/RESO Web API, and swap that in as another function in
  `ai_service.py`.
- Both API calls happen **server-side only** — the browser never sees your
  `ANTHROPIC_API_KEY`.

## Deploying to Vercel

This repo is configured for Vercel with `api/index.py` and `vercel.json`.

For a production deployment, do not use the default local SQLite database. Set a
managed database URL in Vercel and point `DATABASE_URL` to it, for example:

```text
postgresql://user:password@host:5432/dbname
```

Also configure these environment variables in Vercel:

- `ANTHROPIC_API_KEY`
- `FLASK_SECRET_KEY`
- `ADMIN_TOKEN`
- `DATABASE_URL`

If you want your app to work correctly on Vercel, use a Postgres or MySQL database
rather than SQLite. The code already reads `DATABASE_URL` from environment variables
via `config.py`, so Vercel will use the production database when that variable is set.

## Known gaps / good next steps

- **No real authentication** on `/admin` — it's a single shared token in the URL, fine
  for internal use by one team, not for a public multi-tenant product. Add real login
  (Flask-Login, or an actual auth provider) before broker access matters.
- **No automatic emailing.** The broker summary is saved to the database and shown to
  the client with a "copy" and "open in mail" (mailto:) button. To actually email the
  broker automatically, add an SMTP integration (e.g. Flask-Mail) in the
  `/api/submit` route in `app.py`, right after `db.session.commit()`.
- **No file storage for the uploaded document itself** — only the extracted numbers
  are kept; the original image/PDF is read once and discarded. If brokers need the
  original file for compliance, add an upload to disk or S3 in the
  `/api/extract-income` route.
- **SQLite is fine for an MVP demo**, but for real traffic switch `DATABASE_URL` in
  `.env` to Postgres (e.g. on Railway, Render, or Supabase) before deploying.
- **Deploying**: this is a standard Flask app — it runs on Render, Railway, Fly.io,
  or a VPS behind gunicorn (`gunicorn app:app`) with minimal changes. Just make sure
  the environment variables from `.env` are set in whatever platform you use.
