# Chandu Interiors — Backend

Flask backend for the "Get a Free Quote" form: saves every submission to a
SQLite database, emails and WhatsApps you when one comes in, and gives you
a simple admin page to see and manage all leads.

## What it does

- `POST /api/quote` — receives the website's quote form (name, phone,
  WhatsApp, location, service, details, photos), saves it to SQLite,
  and fires off an email + WhatsApp alert in the background.
- `GET /admin` — password-protected dashboard listing every lead, filterable
  by status (New / Contacted / Closed), with links to view uploaded photos.
- `GET /admin/login` — login page for the dashboard.
- `GET /api/health` — simple uptime check.

## 1. Install

```bash
cd chandu-backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure

```bash
cp .env.example .env
```

Open `.env` and fill in:

- `ADMIN_USERNAME` / `ADMIN_PASSWORD` — your login for `/admin`. Change
  these before going live.
- `SMTP_USER` / `SMTP_PASSWORD` / `NOTIFY_EMAIL` — for email alerts. If
  using Gmail, create an **App Password** (Google Account → Security →
  App Passwords) — your normal password won't work.
- `TWILIO_*` — for WhatsApp alerts. Sign up at twilio.com/whatsapp, get a
  sandbox (or approved production) WhatsApp sender, and copy the SID/token.
- `CORS_ORIGINS` — set to your live website's domain once deployed
  (e.g. `https://chanduinteriors.com`). Leave as `*` for local testing.

Both email and WhatsApp are **optional** — if you leave those variables
blank, the lead still saves to the database and shows up in `/admin`; the
app just skips the notification instead of failing.

## 3. Run it

```bash
python app.py
```

The API runs at `http://localhost:5000`. Visit `http://localhost:5000/admin`
and log in with the credentials from your `.env`.

## 4. Connect the website

In `chandu-interiors.html`, find this line near the bottom:

```js
const API_BASE = "http://localhost:5000";
```

Change it to wherever you deploy this backend (e.g.
`https://api.chanduinteriors.com`). The quote form on the site is already
wired to POST to `${API_BASE}/api/quote`.

## 5. Deploying

Any host that runs Python works (Render, Railway, PythonAnywhere, a VPS).
General steps:

1. Push this folder to a git repo.
2. Set the same environment variables from `.env` in your host's dashboard
   (don't upload `.env` itself).
3. Run with a production server instead of the Flask dev server, e.g.:
   ```bash
   pip install gunicorn
   gunicorn -w 2 -b 0.0.0.0:8000 app:app
   ```
4. Put the backend behind HTTPS (most hosts do this automatically) — the
   admin login sends a password, so it should never run on plain HTTP in
   production.
5. Update `CORS_ORIGINS` in your environment to your real website domain.
6. Update `API_BASE` in `chandu-interiors.html` to match the deployed URL.

## Notes

- Uploaded photos are saved to `static/uploads/` and are only viewable by
  logged-in admins (served through `/uploads/<filename>`, behind login).
- The SQLite file (`leads.db`) is created automatically on first run. For
  anything beyond a single small deployment, swap `DATABASE_URL` in `.env`
  for a hosted Postgres/MySQL URL — the code doesn't need to change,
  SQLAlchemy handles either.
- WhatsApp via Twilio's sandbox requires each recipient to first send a
  join code to the sandbox number. For a real customer-facing number, you
  need Twilio's (or Meta's) approved WhatsApp Business API — sandbox is
  fine for testing alerts to yourself.
