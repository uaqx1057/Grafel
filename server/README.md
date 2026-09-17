# Grafel Backend (starter)

A small FastAPI service that powers the paid/cloud tier of Grafel:

- **License validation** — free vs Pro/Team, per-seat activation.
- **Cloud graph sync** — upload/download a project's `graph.json` so a team shares one map.
- **Auto-update** — a manifest endpoint the desktop app checks for new versions.
- **Anonymous analytics** — aggregate "tokens saved" for a marketing headline.

> This is **starter code**. Before production: put it behind HTTPS, add real auth,
> rate-limiting, and move from SQLite to Postgres if you expect load.

## Run locally

```bash
cd server
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
# open http://127.0.0.1:8000/docs  (interactive API)
```

## Run with Docker

```bash
cd server
docker build -t grafel-backend .
docker run -p 8000:8000 -v grafel_data:/data \
  -e GRAFEL_ADMIN_TOKEN=your-secret \
  -e GRAFEL_DOWNLOAD_URL=https://downloads.yourdomain.com/GrafelSetup.exe \
  grafel-backend
```

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET  | `/health` | — | liveness |
| POST | `/license/issue` | `X-Admin-Token` | create a license key (admin) |
| POST | `/license/validate` | — | check a key + activate a machine (seat) |
| PUT  | `/graph/{project_key}` | `X-License-Key` | upload a project graph (Pro) |
| GET  | `/graph/{project_key}` | `X-License-Key` | download a project graph (Pro) |
| GET  | `/update/manifest` | — | latest version/url for the auto-updater |
| POST | `/analytics/ingest` | — | submit anonymized tokens-saved |
| GET  | `/analytics/summary` | `X-Admin-Token` | total tokens saved across users |

## Environment

| Var | Default | Meaning |
|---|---|---|
| `GRAFEL_DB` | `grafel.db` | SQLite path |
| `GRAFEL_ENV` | `development` | runtime mode; `production` enables stricter startup validation |
| `GRAFEL_ALLOW_INSECURE_DEFAULTS` | auto | allow starter defaults outside production, or override validation intentionally |
| `GRAFEL_ADMIN_TOKEN` | `change-me-admin` | admin endpoints token |
| `GRAFEL_LATEST` | `1.0.0` | version returned by `/update/manifest` |
| `GRAFEL_DOWNLOAD_URL` | example | installer URL for updates |
| `GRAFEL_RELEASE_NOTES` | — | notes shown in the app |

In `production`, the backend now fails fast if you leave the default admin token in
place or keep the placeholder download URL.

## Wiring the desktop app

Set `server_url` in `~/.grafel.json` to your deployed base URL, e.g.:

```json
{ "server_url": "https://api.getgrafel.com", "license_key": "GRAFEL-..." }
```

The app then enables **Help → Check for updates** and (future) cloud sync.
