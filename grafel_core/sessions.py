import glob
import json
import os
import re
import time
from urllib.parse import unquote, urlparse


UNIVERSAL_DETECTOR_SPECS = [
    {"tool": "claude", "label": "Claude Code", "implemented": True},
    {"tool": "copilot", "label": "VS Code Copilot Chat", "implemented": True},
    {"tool": "codex", "label": "Codex", "implemented": True},
    {"tool": "cursor", "label": "Cursor", "implemented": False},
    {"tool": "gemini", "label": "Gemini CLI", "implemented": False},
    {"tool": "aider", "label": "Aider", "implemented": False},
    {"tool": "windsurf", "label": "Windsurf", "implemented": False},
    {"tool": "cline", "label": "Cline", "implemented": False},
    {"tool": "continue", "label": "Continue", "implemented": False},
]


def claude_log_dir(repo_path):
    base = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not (repo_path and os.path.isdir(base)):
        return None
    want = re.sub(r"[^a-zA-Z0-9]", "-", repo_path).lower()
    try:
        for name in os.listdir(base):
            if name.lower() == want:
                full = os.path.join(base, name)
                if os.path.isdir(full):
                    return full
    except OSError:
        pass
    return None


def claude_dir_newest_mtime(proj_dir):
    js = glob.glob(os.path.join(proj_dir, "*.jsonl"))
    return max((os.path.getmtime(p) for p in js), default=0)


def friendly_project_name(encoded):
    for marker in ("-GitHub-", "-Desktop-", "-Documents-", "-repos-", "-projects-"):
        i = encoded.rfind(marker)
        if i != -1:
            return encoded[i + len(marker):]
    return encoded


def fmt_tokens(n):
    n = int(n)
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 10_000:
        return f"{n / 1e3:.1f}k"
    return f"{n:,}"


def human_ago(seconds):
    s = int(seconds)
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def session_presence(age_seconds):
    if age_seconds < 300:
        return "open", "ok"
    if age_seconds < 3600:
        return "idle", "dim"
    return "closed", "dim"


def normalize_path(path):
    if not path:
        return None
    try:
        return os.path.normcase(os.path.normpath(os.path.realpath(path)))
    except OSError:
        return os.path.normcase(os.path.normpath(path))


def enrich_session(session, tool, detector_label, now=None):
    now = time.time() if now is None else now
    data = dict(session)
    data["kind"] = data.get("kind") or tool
    data["tool"] = data.get("tool") or tool
    data["detector"] = data.get("detector") or detector_label
    data["monitor_kind"] = data.get("monitor_kind") or data["kind"]
    data["cwd"] = normalize_path(data.get("cwd"))
    data["repo_root"] = normalize_path(data.get("repo_root")) or data["cwd"]
    data["workspace"] = [normalize_path(p) for p in (data.get("workspace") or []) if normalize_path(p)]
    data["dir"] = data.get("dir") or data.get("file") or ""
    data["file"] = data.get("file") or data.get("dir") or ""
    mt = data.get("mtime", 0) or 0
    data["age"] = data.get("age", max(0, now - mt))
    return data


def list_claude_sessions(base=None, now=None):
    base = base or os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(base):
        return []
    now = time.time() if now is None else now
    out = []
    try:
        names = os.listdir(base)
    except OSError:
        return []
    for name in names:
        full = os.path.join(base, name)
        if not os.path.isdir(full):
            continue
        js = glob.glob(os.path.join(full, "*.jsonl"))
        if not js:
            continue
        newest = max(js, key=os.path.getmtime)
        mt = os.path.getmtime(newest)
        age = now - mt
        status, tag = session_presence(age)
        out.append({
            "dir": full,
            "file": newest,
            "name": friendly_project_name(name),
            "mtime": mt,
            "age": age,
            "status": status,
            "tag": tag,
            "cwd": None,
            "workspace": [],
        })
    out.sort(key=lambda d: -d["mtime"])
    return out


def vscode_storage_roots():
    appdata = os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming")
    for prod in ("Code", "Code - Insiders", "VSCodium"):
        root = os.path.join(appdata, prod, "User", "workspaceStorage")
        if os.path.isdir(root):
            yield root


def uri_to_path(uri):
    if not uri or not uri.startswith("file:"):
        return None
    p = unquote(urlparse(uri).path)
    if re.match(r"^/[a-zA-Z]:", p):
        p = p[1:]
    return os.path.normpath(p)


def vscode_chat_dirs_for(folders, parse_workspace_folders):
    want = {os.path.normcase(os.path.normpath(f)) for f in folders if f}
    out = []
    for root in vscode_storage_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            meta = os.path.join(root, name, "workspace.json")
            chats = os.path.join(root, name, "chatSessions")
            if not (os.path.isfile(meta) and os.path.isdir(chats)):
                continue
            try:
                with open(meta, encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            paths = []
            fp = uri_to_path(data.get("folder"))
            if fp:
                paths.append(fp)
            wsf = data.get("workspace")
            wsp = uri_to_path(wsf) if isinstance(wsf, str) else None
            if wsp and os.path.isfile(wsp):
                paths.extend(parse_workspace_folders(wsp))
            if not want:
                label = os.path.basename(paths[0]) if paths else name[:8]
                out.append((chats, label, paths))
                continue
            for p in paths:
                if os.path.normcase(os.path.normpath(p)) in want:
                    out.append((chats, os.path.basename(p), paths))
                    break
    return out


def list_vscode_copilot_sessions(folders, parse_workspace_folders):
    now = time.time()
    out = []
    for chats_dir, label, paths in vscode_chat_dirs_for(folders, parse_workspace_folders):
        norm_paths = [normalize_path(p) for p in paths if normalize_path(p)]
        for fp in glob.glob(os.path.join(chats_dir, "*.jsonl")):
            try:
                mt = os.path.getmtime(fp)
            except OSError:
                continue
            age = now - mt
            status, tag = session_presence(age)
            sid = os.path.basename(fp).split(".")[0][:8]
            out.append({
                "dir": fp,
                "file": fp,
                "kind": "copilot",
                "name": f"Copilot | {label} | {sid}",
                "mtime": mt,
                "age": age,
                "status": status,
                "tag": tag,
                "cwd": norm_paths[0] if norm_paths else None,
                "workspace": norm_paths,
                "repo_root": norm_paths[0] if norm_paths else None,
            })
    out.sort(key=lambda d: -d["mtime"])
    return out


def codex_session_meta(jsonl_path):
    try:
        with open(jsonl_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"type":"session_meta"' not in line and '"type": "session_meta"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                payload = obj.get("payload") or {}
                cwd = payload.get("cwd")
                session_id = payload.get("session_id") or payload.get("id")
                if isinstance(cwd, str) and cwd:
                    return {
                        "cwd": os.path.normpath(cwd),
                        "session_id": session_id or "",
                        "originator": payload.get("originator") or "",
                        "source": payload.get("source") or "",
                    }
    except OSError:
        pass
    return {"cwd": None, "session_id": "", "originator": "", "source": ""}


def list_codex_sessions(base=None, now=None):
    base = base or os.path.join(os.path.expanduser("~"), ".codex", "sessions")
    if not os.path.isdir(base):
        return []
    now = time.time() if now is None else now
    out = []
    files = glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True)
    for fp in files:
        try:
            mt = os.path.getmtime(fp)
        except OSError:
            continue
        meta = codex_session_meta(fp)
        cwd = meta.get("cwd")
        age = now - mt
        status, tag = session_presence(age)
        sid = (meta.get("session_id") or os.path.basename(fp).split(".")[0])[:8]
        label = os.path.basename(cwd) if cwd else "Unknown"
        out.append({
            "dir": fp,
            "file": fp,
            "cwd": cwd,
            "kind": "codex",
            "name": f"Codex | {label} | {sid}",
            "mtime": mt,
            "age": age,
            "status": status,
            "tag": tag,
            "originator": meta.get("originator") or "",
            "source": meta.get("source") or "",
            "workspace": [cwd] if cwd else [],
            "repo_root": cwd,
        })
    out.sort(key=lambda d: -d["mtime"])
    return out


def session_detector_catalog():
    return [dict(spec) for spec in UNIVERSAL_DETECTOR_SPECS]


def list_ai_sessions(folders, parse_workspace_folders, now=None):
    now = time.time() if now is None else now
    sessions = []
    for item in list_claude_sessions(now=now):
        sessions.append(enrich_session(item, "claude", "Claude Code", now=now))
    for item in list_vscode_copilot_sessions(folders, parse_workspace_folders):
        sessions.append(enrich_session(item, "copilot", "VS Code Copilot Chat", now=now))
    for item in list_codex_sessions(now=now):
        sessions.append(enrich_session(item, "codex", "Codex", now=now))
    sessions.sort(key=lambda d: -d.get("mtime", 0))
    return sessions


def read_complete_lines(path, pos=0):
    """Read newly appended *complete* lines from a growing log file.

    Tail-safe read for the live-meter pollers: opens in binary and only
    consumes up to the last b"\\n" in the new data, so a line the writer is
    still mid-write stays unconsumed (pos does not advance past it) and is
    re-read whole on the next poll instead of being dropped in two unparsable
    halves. Cutting at a newline also means a multibyte UTF-8 char is never
    split at the decode boundary. If the file shrank (truncated/rewritten,
    e.g. VS Code rewriting chatSessions/*.jsonl on window reload), resets to
    the start instead of seeking past EOF and reading "" forever.

    Returns (text, new_pos): the decoded complete portion ("" when nothing
    complete is new) and the position to pass to the next call.
    """
    try:
        size = os.path.getsize(path)
        if size < pos:
            pos = 0
        if size <= pos:
            return "", pos
        with open(path, "rb") as f:
            f.seek(pos)
            chunk = f.read()
    except OSError:
        return "", pos
    cut = chunk.rfind(b"\n")
    if cut < 0:
        return "", pos
    return chunk[:cut + 1].decode("utf-8", errors="replace"), pos + cut + 1


def iter_vscode_chat_events(path, pos=0):
    events = []
    chunk, newpos = read_complete_lines(path, pos)
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        kind, k, v = obj.get("kind"), obj.get("k"), obj.get("v")
        if kind == 0 and isinstance(v, dict):
            for i, req in enumerate(v.get("requests") or []):
                txt = ((req.get("message") or {}).get("text") or "").strip()
                events.append(("request", i, txt))
                for fld in ("promptTokens", "completionTokens", "copilotCredits"):
                    if req.get(fld):
                        events.append(("usage", i, fld, req[fld]))
        elif kind == 2 and k == ["requests"] and isinstance(v, list):
            for req in v:
                txt = ((req.get("message") or {}).get("text") or "").strip()
                events.append(("request", None, txt))
        elif (kind == 1 and isinstance(k, list) and len(k) == 3
              and k[0] == "requests"
              and k[2] in ("promptTokens", "completionTokens", "copilotCredits")):
            events.append(("usage", k[1], k[2], v))
    return events, newpos


def session_cwd(jsonl_path):
    cwd = None
    try:
        with open(jsonl_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"cwd"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                c = obj.get("cwd")
                if isinstance(c, str) and c:
                    cwd = c
    except OSError:
        pass
    return cwd


def session_cwd_fast(jsonl_path, tail_bytes=65536, fallback=True):
    """Resolve a session's cwd from the file tail; optionally fall back to a
    full scan. A single huge tool-output line near EOF can push every "cwd"
    record out of the tail window — without the fallback the session gets
    misclassified as out-of-scope. The fallback only triggers when the tail
    was actually a partial read (file larger than tail_bytes) and found no
    cwd; pass fallback=False to keep the old fast-only, may-miss semantics."""
    try:
        size = os.path.getsize(jsonl_path)
        with open(jsonl_path, "rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()
            data = f.read().decode("utf-8", "ignore")
    except OSError:
        return None
    cwd = None
    for line in data.splitlines():
        if '"cwd"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        c = obj.get("cwd")
        if isinstance(c, str) and c:
            cwd = c
    if cwd is None and fallback and size > tail_bytes:
        return session_cwd(jsonl_path)
    return cwd


def codex_session_cwd_fast(jsonl_path):
    meta = codex_session_meta(jsonl_path)
    cwd = meta.get("cwd")
    return os.path.normpath(cwd) if isinstance(cwd, str) and cwd else None


GRAPH_USAGE_PATTERNS = (
    "graphify query",
    "grafel-query.cmd",
    "grafel-path.cmd",
    "grafel-explain.cmd",
    "grafel-save-result.cmd",
    "--proof-command",
    "--proof-query",
    "graphify path",
    "graphify explain",
    "graphify save-result",
    "graphify-out/graph.json",
    "graphify-out\\graph.json",
    "query the graph",
    "knowledge graph at graphify-out",
)

BYPASS_PATTERNS = (
    "get-childitem -recurse",
    "rg --files",
    "findstr /s",
    "select-string -path",
    "os.walk(",
    "glob.glob(",
    "read graph_report.md",
    "read graphify-out/graph_report.md",
    "read graphify-out\\graph_report.md",
    "grep -r",
)


def session_graph_usage(path, tail_bytes=131072):
    """Best-effort local evidence that a session has referenced graphify/graph output."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()
            data = f.read().decode("utf-8", "ignore").lower()
    except OSError:
        return {"detected": False, "matches": []}
    matches = [pattern for pattern in GRAPH_USAGE_PATTERNS if pattern in data]
    return {"detected": bool(matches), "matches": matches}


def session_bypass_risk(path, tail_bytes=131072):
    """Best-effort evidence of broad repo exploration without graph-first behavior."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()
            data = f.read().decode("utf-8", "ignore").lower()
    except OSError:
        return {"detected": False, "matches": []}
    matches = [pattern for pattern in BYPASS_PATTERNS if pattern in data]
    return {"detected": bool(matches), "matches": matches}


def iter_codex_token_counts(path, pos=0):
    events = []
    chunk, newpos = read_complete_lines(path, pos)
    for line in chunk.splitlines():
        if '"token_count"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        info = (obj.get("payload") or {}).get("info") or {}
        total = info.get("total_token_usage") or {}
        last = info.get("last_token_usage") or {}
        if total:
            events.append({
                "timestamp": obj.get("timestamp"),
                "total": {
                    "input": total.get("input_tokens", 0) or 0,
                    "cached": total.get("cached_input_tokens", 0) or 0,
                    "output": total.get("output_tokens", 0) or 0,
                    "reasoning": total.get("reasoning_output_tokens", 0) or 0,
                    "all": total.get("total_tokens", 0) or 0,
                },
                "last": {
                    "input": last.get("input_tokens", 0) or 0,
                    "cached": last.get("cached_input_tokens", 0) or 0,
                    "output": last.get("output_tokens", 0) or 0,
                    "reasoning": last.get("reasoning_output_tokens", 0) or 0,
                    "all": last.get("total_tokens", 0) or 0,
                },
            })
    return events, newpos


def is_text_user_content(content):
    return isinstance(content, str) or (
        isinstance(content, list)
        and content
        and isinstance(content[0], dict)
        and content[0].get("type") == "text"
    )


def parse_claude_jsonl_chunk(chunk, seen_ids=None):
    seen_ids = seen_ids if seen_ids is not None else set()
    events = []
    for line in chunk.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        msg = obj.get("message") or {}
        role = msg.get("role")
        if obj.get("type") == "user" and role == "user":
            if is_text_user_content(msg.get("content")):
                events.append(("user", None))
        elif role == "assistant":
            u = msg.get("usage") or {}
            mid = msg.get("id")
            if u and mid and mid not in seen_ids:
                seen_ids.add(mid)
                events.append(("assistant_usage", {
                    "id": mid,
                    "input_tokens": u.get("input_tokens", 0) or 0,
                    "cache_read_input_tokens": u.get("cache_read_input_tokens", 0) or 0,
                    "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0) or 0,
                    "output_tokens": u.get("output_tokens", 0) or 0,
                    "model": msg.get("model") or "",
                    "timestamp": obj.get("timestamp"),
                }))
    return events, seen_ids


def accumulate_usage_bucket(bucket, usage):
    bucket = bucket or {"in": 0, "cr": 0, "cw": 0, "out": 0, "msgs": 0}
    bucket["in"] += usage.get("input_tokens", 0) or 0
    bucket["cr"] += usage.get("cache_read_input_tokens", 0) or 0
    bucket["cw"] += usage.get("cache_creation_input_tokens", 0) or 0
    bucket["out"] += usage.get("output_tokens", 0) or 0
    bucket["msgs"] += 1
    return bucket


def iter_claude_usage_entries(path, seen=None):
    """Yield deduped assistant-usage entries from one session jsonl.

    Pass a shared `seen` set to dedupe across files: a resumed session's new
    .jsonl replays the prior transcript, so a per-file set double-counts the
    same message ids across the old + new files."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            seen = seen if seen is not None else set()
            for line in f:
                if '"usage"' not in line:
                    continue
                events, seen = parse_claude_jsonl_chunk(line, seen)
                for kind, payload in events:
                    if kind == "assistant_usage":
                        yield payload
    except OSError:
        return


def scan_claude_usage(base_dir=None):
    base_dir = base_dir or os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(base_dir):
        return None
    data = {
        "files": 0,
        "responses": 0,
        "totals": {"in": 0, "out": 0, "cr": 0, "cw": 0},
        "per_model": {},
        "per_project": {},
        "months": {},
    }
    files = glob.glob(os.path.join(base_dir, "**", "*.jsonl"), recursive=True)
    data["files"] = len(files)
    seen = set()  # one dedup set for the whole scan, not per file (resumed
    # sessions replay the prior transcript into a new .jsonl)
    for fp in files:
        proj = os.path.basename(os.path.dirname(fp))
        for entry in iter_claude_usage_entries(fp, seen):
            i = entry["input_tokens"]
            o = entry["output_tokens"]
            cr = entry["cache_read_input_tokens"]
            cw = entry["cache_creation_input_tokens"]
            data["responses"] += 1
            totals = data["totals"]
            totals["in"] += i
            totals["out"] += o
            totals["cr"] += cr
            totals["cw"] += cw
            model = (entry.get("model") or "").lower()
            cls = ("opus" if "opus" in model else
                   "sonnet" if "sonnet" in model else
                   "haiku" if "haiku" in model else "other")
            pm = data["per_model"].setdefault(
                cls, {"in": 0, "out": 0, "cr": 0, "cw": 0, "n": 0})
            pm["in"] += i
            pm["out"] += o
            pm["cr"] += cr
            pm["cw"] += cw
            pm["n"] += 1
            total = i + o + cr + cw
            data["per_project"][proj] = data["per_project"].get(proj, 0) + total
            ts = entry.get("timestamp")
            mk = ts[:7] if isinstance(ts, str) and len(ts) >= 7 else "unknown"
            data["months"][mk] = data["months"].get(mk, 0) + total
    return data


def claude_cost(per_model, rates):
    by, total = {}, 0.0
    for cls, pm in per_model.items():
        r = rates.get(cls, rates["other"])
        cost = (pm["in"] / 1e6 * r["in"] + pm["cw"] / 1e6 * r["cw"]
                + pm["cr"] / 1e6 * r["cr"] + pm["out"] / 1e6 * r["out"])
        by[cls] = cost
        total += cost
    return total, by


def scan_codex_usage(base_dir=None):
    base_dir = base_dir or os.path.join(os.path.expanduser("~"), ".codex", "sessions")
    if not os.path.isdir(base_dir):
        return None
    data = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "files": 0}
    files = glob.glob(os.path.join(base_dir, "**", "*.jsonl"), recursive=True)
    data["files"] = len(files)
    for fp in files:
        last = None
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if '"token_count"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    info = (obj.get("payload") or {}).get("info") or {}
                    tu = info.get("total_token_usage")
                    if tu:
                        last = tu
        except OSError:
            continue
        if last:
            data["input"] += last.get("input_tokens", 0) or 0
            data["cached"] += last.get("cached_input_tokens", 0) or 0
            data["output"] += last.get("output_tokens", 0) or 0
            data["reasoning"] += last.get("reasoning_output_tokens", 0) or 0
            data["total"] += last.get("total_tokens", 0) or 0
    return data


def scan_copilot_cli_usage(db_path=None):
    db_path = db_path or os.path.join(os.path.expanduser("~"), ".copilot", "session-store.db")
    if not os.path.exists(db_path):
        return None
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = con.cursor()
        sessions = cur.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        turns = cur.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        rows = cur.execute("SELECT timestamp FROM turns").fetchall()
        con.close()
    except Exception as exc:
        return {"error": str(exc), "path": db_path}
    months = {}
    for (ts,) in rows:
        mk = (ts or "")[:7]
        if len(mk) >= 7:
            months[mk] = months.get(mk, 0) + 1
    return {"sessions": sessions, "turns": turns, "months": months, "path": db_path}
