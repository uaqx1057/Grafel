"""Grafel backend - license validation, cloud graph sync, auto-update, analytics.

Self-contained FastAPI service backed by SQLite. Deploy anywhere (see README).
This is STARTER code: add real auth/rate-limiting/HTTPS before production use.

Run:  uvicorn app:app --host 0.0.0.0 --port 8000
"""
import os
import secrets
import sqlite3
import time
from contextlib import closing

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

DB = os.environ.get("GRAFEL_DB", "grafel.db")
ADMIN_TOKEN = os.environ.get("GRAFEL_ADMIN_TOKEN", "change-me-admin")
APP_ENV = os.environ.get("GRAFEL_ENV", "development").strip().lower()
ALLOW_INSECURE_DEFAULTS = os.environ.get(
    "GRAFEL_ALLOW_INSECURE_DEFAULTS",
    "1" if APP_ENV in {"development", "dev", "local", "test"} else "0",
).strip().lower() in {"1", "true", "yes", "on"}
# Max serialized graph upload size in bytes (25MB default).
MAX_GRAPH_BYTES = int(os.environ.get("GRAFEL_MAX_GRAPH_BYTES", "25000000"))
# Latest client build the auto-updater should point at.
LATEST = {
    "version": os.environ.get("GRAFEL_LATEST", "1.0.0"),
    "url": os.environ.get("GRAFEL_DOWNLOAD_URL",
                          "https://downloads.example.com/GrafelSetup.exe"),
    "notes": os.environ.get("GRAFEL_RELEASE_NOTES", "Latest Grafel release."),
}

app = FastAPI(title="Grafel Backend", version="1.0.0")


def validate_runtime_config(
    *,
    env=None,
    admin_token=None,
    latest=None,
    allow_insecure_defaults=None,
):
    """Fail fast on obviously unsafe production defaults."""
    env = (env or APP_ENV).strip().lower()
    admin_token = admin_token or ADMIN_TOKEN
    latest = latest or LATEST
    if allow_insecure_defaults is None:
        allow_insecure_defaults = ALLOW_INSECURE_DEFAULTS
    if env not in {"production", "prod"} or allow_insecure_defaults:
        return
    if admin_token == "change-me-admin":
        raise RuntimeError("Refusing to start with the default admin token in production.")
    update_url = (latest.get("url") or "").strip().lower()
    if (not update_url or "downloads.example.com" in update_url
            or update_url.startswith("https://example.com")):
        raise RuntimeError("Refusing to start with a placeholder download URL in production.")


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # Wait briefly on lock contention instead of raising "database is locked".
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init():
    with closing(db()) as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS licenses (
                key TEXT PRIMARY KEY, plan TEXT, expires INTEGER,
                seats INTEGER DEFAULT 1, created INTEGER
            );
            CREATE TABLE IF NOT EXISTS activations (
                key TEXT, machine_id TEXT, last_seen INTEGER,
                PRIMARY KEY (key, machine_id)
            );
            CREATE TABLE IF NOT EXISTS graphs (
                project_key TEXT PRIMARY KEY, owner_key TEXT,
                data TEXT, updated INTEGER
            );
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT, license_key TEXT,
                tokens_saved INTEGER, model TEXT, ts INTEGER
            );
            """
        )
        c.commit()


validate_runtime_config()
init()


def require_admin(token):
    # Timing-safe comparison; token is None when the header wasn't sent.
    if not isinstance(token, str) or not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(401, "admin token required")


def valid_license(key):
    with closing(db()) as c:
        row = c.execute("SELECT * FROM licenses WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    if row["expires"] and row["expires"] < int(time.time()):
        return None
    return row


# ---------- health ----------

@app.get("/health")
def health():
    return {"ok": True, "service": "grafel-backend"}


# ---------- licensing ----------

@app.post("/license/issue")
def issue(plan: str = Body("pro"), days: int = Body(365), seats: int = Body(1),
          x_admin_token: str = Header(None)):
    require_admin(x_admin_token)
    key = "GRAFEL-" + secrets.token_hex(12).upper()
    expires = int(time.time()) + days * 86400 if days else 0
    with closing(db()) as c:
        c.execute("INSERT INTO licenses(key,plan,expires,seats,created) "
                  "VALUES(?,?,?,?,?)", (key, plan, expires, seats, int(time.time())))
        c.commit()
    return {"key": key, "plan": plan, "expires": expires, "seats": seats}


@app.post("/license/validate")
def validate(key: str = Body(...), machine_id: str = Body("")):
    row = valid_license(key)
    if not row:
        return {"valid": False, "plan": "free"}
    with closing(db()) as c:
        # Take the write lock up front so the seat check + insert are atomic;
        # concurrent activations serialize instead of both passing the check.
        c.execute("BEGIN IMMEDIATE")
        seats = c.execute("SELECT COUNT(*) n FROM activations WHERE key=?",
                          (key,)).fetchone()["n"]
        exists = c.execute("SELECT 1 FROM activations WHERE key=? AND machine_id=?",
                           (key, machine_id)).fetchone()
        if machine_id and not exists and seats >= row["seats"]:
            # No writes happened; closing the connection rolls back the lock.
            return {"valid": False, "plan": "free", "reason": "seat limit reached"}
        if machine_id:
            c.execute("INSERT OR REPLACE INTO activations(key,machine_id,last_seen) "
                      "VALUES(?,?,?)", (key, machine_id, int(time.time())))
        c.commit()
    return {"valid": True, "plan": row["plan"], "expires": row["expires"]}


# ---------- cloud graph sync ----------

def reject_oversized_upload(request: Request):
    """Reject an oversized upload via Content-Length BEFORE FastAPI reads and
    JSON-parses the body (Body(...) binding buffers the whole payload first, so
    a post-parse size check alone never prevents the memory hit). Absent or
    non-numeric Content-Length (chunked encoding, lying clients) falls through
    to put_graph's post-parse check, kept as defense in depth."""
    raw = request.headers.get("content-length")
    if raw is None:
        return
    try:
        length = int(raw)
    except ValueError:
        return
    if length > MAX_GRAPH_BYTES:
        raise HTTPException(413, "graph too large (limit %d bytes)" % MAX_GRAPH_BYTES)


@app.put("/graph/{project_key}", dependencies=[Depends(reject_oversized_upload)])
def put_graph(project_key: str, body: dict = Body(...),
              x_license_key: str = Header(None)):
    if not valid_license(x_license_key):
        raise HTTPException(402, "valid Pro/Team license required for cloud sync")
    import json
    data = json.dumps(body)
    if len(data.encode("utf-8")) > MAX_GRAPH_BYTES:
        raise HTTPException(413, "graph too large (limit %d bytes)" % MAX_GRAPH_BYTES)
    with closing(db()) as c:
        existing = c.execute("SELECT owner_key FROM graphs WHERE project_key=?",
                             (project_key,)).fetchone()
        if existing and existing["owner_key"] != x_license_key:
            raise HTTPException(409, "project_key already in use by another license")
        c.execute("INSERT OR REPLACE INTO graphs(project_key,owner_key,data,updated) "
                  "VALUES(?,?,?,?)",
                  (project_key, x_license_key, data, int(time.time())))
        c.commit()
    return {"ok": True, "project_key": project_key}


@app.get("/graph/{project_key}")
def get_graph(project_key: str, x_license_key: str = Header(None)):
    if not valid_license(x_license_key):
        raise HTTPException(402, "valid Pro/Team license required for cloud sync")
    import json
    with closing(db()) as c:
        row = c.execute("SELECT owner_key,data,updated FROM graphs WHERE project_key=?",
                        (project_key,)).fetchone()
    if not row:
        raise HTTPException(404, "no graph stored for this project")
    if row["owner_key"] != x_license_key:
        raise HTTPException(403, "this project belongs to a different license")
    return JSONResponse({"updated": row["updated"], "graph": json.loads(row["data"])})


# ---------- auto-update ----------

@app.get("/update/manifest")
def manifest(channel: str = "stable"):
    return LATEST


# ---------- anonymous analytics ----------

@app.post("/analytics/ingest")
def ingest(tokens_saved: int = Body(0), model: str = Body(""),
           license_key: str = Body("")):
    with closing(db()) as c:
        c.execute("INSERT INTO analytics(license_key,tokens_saved,model,ts) "
                  "VALUES(?,?,?,?)",
                  (license_key, int(tokens_saved), model, int(time.time())))
        c.commit()
    return {"ok": True}


@app.get("/analytics/summary")
def summary(x_admin_token: str = Header(None)):
    require_admin(x_admin_token)
    with closing(db()) as c:
        row = c.execute("SELECT COUNT(*) events, "
                        "COALESCE(SUM(tokens_saved),0) tokens FROM analytics").fetchone()
    return {"events": row["events"], "total_tokens_saved": row["tokens"]}
