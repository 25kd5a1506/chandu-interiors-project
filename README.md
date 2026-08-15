# Chandu Interiors — Full Project

This is the complete project: the website (frontend) and the Flask backend
(quote form API, email/WhatsApp alerts, admin dashboard), set up as a
VS Code workspace.

```
chandu-interiors-project/
├── frontend/
│   └── index.html          ← the website
├── backend/
│   ├── app.py               ← Flask app (routes)
│   ├── config.py            ← settings, loaded from .env
│   ├── models.py            ← Lead database model
│   ├── notifications.py     ← email + WhatsApp alert logic
│   ├── requirements.txt
│   ├── .env.example         ← copy to .env and fill in
│   ├── templates/           ← admin login + dashboard pages
│   └── static/uploads/      ← uploaded quote-request photos land here
├── .vscode/                 ← editor config (debugger, recommended extensions)
└── .gitignore
```

## Open the project

1. Open VS Code → **File → Open Folder** → select `chandu-interiors-project`.
2. When prompted, install the recommended extensions (Python, Live Server).
   Or open the Extensions panel and search `@recommended`.

## Set up the backend

Open a terminal in VS Code (`` Ctrl+` ``) and run:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Then open `backend/.env` and fill in your real values (admin login, SMTP
email credentials, Twilio WhatsApp credentials). Both email and WhatsApp
are optional — leave them blank and the app still saves leads, it just
skips the notification.

In VS Code, select the interpreter: `Ctrl+Shift+P` → **Python: Select
Interpreter** → choose `backend/venv/bin/python`.

## Run the backend

Two ways:

- **Debugger (recommended):** press `F5`, or open the "Run and Debug"
  panel and hit ▶ on **"Flask: Run Backend"**. This uses the config
  already set up in `.vscode/launch.json` — you get breakpoints, variable
  inspection, and auto-reload.
- **Terminal:**
  ```bash
  cd backend
  source venv/bin/activate
  python app.py
  ```

Either way, the API runs at `http://localhost:5000`. Visit
`http://localhost:5000/admin` to log into the leads dashboard.

## Run the frontend

The site is a static HTML file — no build step. Two easy options:

- **Live Server extension:** right-click `frontend/index.html` →
  **"Open with Live Server"**. It opens in your browser and auto-refreshes
  when you save.
- **Just open it:** double-click `frontend/index.html`, or drag it into
  a browser tab.

The quote form on the page is already wired to call the backend:

```js
// near the bottom of frontend/index.html
const API_BASE = "http://localhost:5000";
```

Leave this as-is for local development. When you deploy the backend
somewhere real, change this to that URL (e.g.
`https://api.chanduinteriors.com`) and update `CORS_ORIGINS` in
`backend/.env` to match your live site's domain.

## Everyday workflow in VS Code

1. Start the backend with `F5` (Run and Debug).
2. Open `frontend/index.html` with Live Server.
3. Fill out the "Get a Free Quote" form on the site — it should hit your
   local backend, save to `backend/leads.db`, and show up at
   `http://localhost:5000/admin`.
4. Edit `frontend/index.html` for design/copy changes — Live Server
   refreshes automatically.
5. Edit backend files under `backend/` — the Flask debugger reloads on
   save when `FLASK_DEBUG=1` is set (already configured in
   `.vscode/launch.json`).

See `backend/README.md` for backend-specific details (deployment,
Twilio/Gmail setup, database notes).
