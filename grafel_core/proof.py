import json
import os
import time


PROOF_LOG_NAME = "grafel-graph-usage.jsonl"


def proof_log_path(repo_path):
    return os.path.join(repo_path, "graphify-out", PROOF_LOG_NAME)


def append_graph_use_event(
    repo_path,
    source,
    command,
    argv,
    cwd=None,
    tokens=0,
    success=True,
    session_hint=None,
):
    os.makedirs(os.path.join(repo_path, "graphify-out"), exist_ok=True)
    path = proof_log_path(repo_path)
    event = {
        "ts": time.time(),
        "source": source,
        "command": command,
        "argv": list(argv or []),
        "cwd": cwd or repo_path,
        "tokens": int(tokens or 0),
        "success": bool(success),
        "session_hint": session_hint or "",
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return event


def read_graph_use_events(repo_path, limit=None):
    path = proof_log_path(repo_path)
    if not os.path.exists(path):
        return []
    events = []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    if limit:
        return events[-limit:]
    return events


def graph_use_summary(repo_path, now=None, recent_window_seconds=86400):
    now = time.time() if now is None else now
    events = read_graph_use_events(repo_path)
    successes = [e for e in events if e.get("success")]
    recent = [
        e for e in successes
        if now - float(e.get("ts", 0) or 0) <= recent_window_seconds
    ]
    latest = successes[-1] if successes else None
    return {
        "total_events": len(events),
        "successful_events": len(successes),
        "recent_successful_events": len(recent),
        "latest_event": latest,
        "proof_log": proof_log_path(repo_path),
    }


def command_for_helper(helper_name):
    mapping = {
        "grafel-query.cmd": "query",
        "grafel-path.cmd": "path",
        "grafel-explain.cmd": "explain",
        "grafel-save-result.cmd": "save-result",
    }
    return mapping.get(helper_name)
