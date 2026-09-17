import os


def watch_event_kind(line):
    low = (line or "").strip().lower()
    if not low:
        return "empty"
    if "skill is from graphify" in low or low.startswith("run 'graphify"):
        return "noise"
    if "rebuilt" in low or "updated" in low:
        return "rebuild"
    if "error" in low or "traceback" in low:
        return "error"
    return "info"


def normalize_scope_path(path):
    if not path:
        return None
    try:
        return os.path.normcase(os.path.normpath(os.path.realpath(path)))
    except OSError:
        return os.path.normcase(os.path.normpath(path))


def path_is_related(base_path, other_path):
    base = normalize_scope_path(base_path)
    other = normalize_scope_path(other_path)
    if not (base and other):
        return False
    if other == base:
        return True
    if other.startswith(base + os.sep):
        return True
    return False


def find_git_root(path):
    cur = normalize_scope_path(path)
    while cur:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def scope_folders_for_mode(repo_path, scope_mode, find_workspace_for, parse_workspace_folders):
    if not repo_path:
        return []
    if scope_mode == "all":
        return []
    repo_only = [repo_path]
    if scope_mode == "repo":
        return repo_only
    _ws, folders = find_workspace_for(repo_path, parse_workspace_folders)
    return folders if folders else repo_only


def meter_scope_state(repo_path, scope_mode, find_workspace_for, parse_workspace_folders, claude_log_dir):
    scope_folders = scope_folders_for_mode(repo_path, scope_mode, find_workspace_for, parse_workspace_folders)
    repo_norm = normalize_scope_path(repo_path)
    scope_norm = [normalize_scope_path(f) for f in scope_folders if normalize_scope_path(f)]
    repo_git = find_git_root(repo_norm) if repo_norm else None
    return {
        "mode": scope_mode,
        "repo_path": repo_path,
        "repo_norm": repo_norm,
        "repo_git": repo_git,
        "folders": scope_folders,
        "scope": set(scope_norm),
        # normalized like session_dir in session_scope_details, so the
        # dir-name comparison is case-insensitive (Windows drive-letter and
        # home-path case varies)
        "dirs": {normalize_scope_path(d) for d in (claude_log_dir(f) for f in scope_folders) if d},
        "git_roots": {find_git_root(f) for f in scope_norm if find_git_root(f)},
    }


def session_scope_level(session, scope_state, session_cwd_fast):
    return session_scope_details(session, scope_state, session_cwd_fast)["level"]


def session_scope_details(session, scope_state, session_cwd_fast):
    if scope_state.get("mode") == "all":
        return {
            "level": "machine",
            "hard_link": False,
            "reasons": ["meter scope is set to all sessions"],
            "attribution": "unscoped",
        }
    repo_norm = scope_state.get("repo_norm")
    scope = scope_state.get("scope") or set()
    scope_dirs = scope_state.get("dirs") or set()
    git_roots = scope_state.get("git_roots") or set()
    session_dir = normalize_scope_path(session.get("dir"))
    cwd = normalize_scope_path(session.get("cwd") or session_cwd_fast(session.get("file") or ""))
    if repo_norm and cwd and path_is_related(repo_norm, cwd):
        return {
            "level": "repo",
            "hard_link": True,
            "reasons": ["session cwd is inside the target repo"],
            "attribution": "confirmed",
        }
    repo_git = scope_state.get("repo_git")
    session_git = find_git_root(cwd) if cwd else None
    if repo_git and session_git and repo_git == session_git:
        return {
            "level": "repo",
            "hard_link": True,
            "reasons": ["session git root matches the target repo"],
            "attribution": "confirmed",
        }
    # Only trust the encoded log-directory name when the session's real cwd is
    # unknown: claude_log_dir's encoding maps every non-alphanumeric char to
    # "-", so C:\repo-x and C:\repo_x collide to the same directory name. When
    # a cwd IS resolvable it is ground truth (see HANDOFF "always use
    # session_cwd()"), and a cwd that didn't match above means this session
    # belongs to a different, similarly-named repo.
    if session_dir and session_dir in scope_dirs and not cwd:
        return {
            "level": "workspace",
            "hard_link": True,
            "reasons": ["session log directory matches the current workspace"],
            "attribution": "confirmed",
        }
    if cwd:
        for folder in scope:
            if path_is_related(folder, cwd):
                return {
                    "level": "workspace",
                    "hard_link": True,
                    "reasons": ["session cwd is inside the current workspace"],
                    "attribution": "confirmed",
                }
        if session_git and session_git in git_roots:
            return {
                "level": "workspace",
                "hard_link": True,
                "reasons": ["session git root matches a workspace member repo"],
                "attribution": "confirmed",
            }
    return {
        "level": "machine",
        "hard_link": False,
        "reasons": ["no hard repo/workspace evidence matched this session"],
        "attribution": "outside",
    }


def session_in_scope(session, meter_scope, meter_scope_dirs, session_cwd_fast):
    scope_state = {"scope": meter_scope, "dirs": meter_scope_dirs, "mode": "workspace"}
    return session_scope_level(session, scope_state, session_cwd_fast) in ("repo", "workspace")


def session_dedupe_key(session):
    kind = session.get("kind") or "claude"
    file_path = session.get("file") or ""
    if kind == "copilot" and file_path:
        return kind, os.path.basename(file_path)
    return kind, file_path or session.get("dir")


def dedupe_sessions(sessions):
    chosen = {}
    for session in sessions:
        key = session_dedupe_key(session)
        prev = chosen.get(key)
        if prev is None or session.get("mtime", 0) > prev.get("mtime", 0):
            chosen[key] = session
    return sorted(chosen.values(), key=lambda d: -d["mtime"])


def session_kind_counts(sessions):
    counts = {"claude": 0, "copilot": 0, "codex": 0, "other": 0}
    for session in sessions:
        kind = session.get("kind") or "claude"
        if kind not in counts:
            kind = "other"
        counts[kind] += 1
    return counts


def split_meter_sessions(all_sessions, scope_state, session_cwd_fast):
    if scope_state.get("mode") == "all":
        machine = dedupe_sessions(all_sessions)
        for session in machine:
            session["scope_level"] = "machine"
            session["hard_link"] = False
            session["attribution"] = "unscoped"
            session["attribution_reasons"] = ["meter scope is set to all sessions"]
        return {
            "scoped": machine,
            "other": [],
            "scoped_count": len(machine),
            "other_count": 0,
            "scoped_counts": session_kind_counts(machine),
            "other_counts": session_kind_counts([]),
        }
    scoped = []
    other = []
    for session in all_sessions:
        session_copy = dict(session)
        detail = session_scope_details(session_copy, scope_state, session_cwd_fast)
        level = detail["level"]
        session_copy["scope_level"] = level
        session_copy["hard_link"] = detail["hard_link"]
        session_copy["attribution"] = detail["attribution"]
        session_copy["attribution_reasons"] = detail["reasons"]
        if level in ("repo", "workspace"):
            scoped.append(session_copy)
        else:
            other.append(session_copy)
    scoped = dedupe_sessions(scoped)
    other = dedupe_sessions(other)
    return {
        "scoped": scoped,
        "other": other,
        "scoped_count": len(scoped),
        "other_count": len(other),
        "scoped_counts": session_kind_counts(scoped),
        "other_counts": session_kind_counts(other),
    }


def initial_meter_sessions(
    repo_path,
    scope_mode,
    find_workspace_for,
    parse_workspace_folders,
    claude_log_dir,
    list_ai_sessions,
    session_cwd_fast,
):
    scope_state = meter_scope_state(
        repo_path, scope_mode, find_workspace_for, parse_workspace_folders, claude_log_dir
    )
    all_sessions = dedupe_sessions(list_ai_sessions([], parse_workspace_folders))
    split = split_meter_sessions(all_sessions, scope_state, session_cwd_fast)
    return {
        "scope_state": scope_state,
        "all_sessions": all_sessions,
        "sessions": split["scoped"][:12],
        "other_sessions": split["other"],
        "has_any": bool(all_sessions),
        "in_scope_count": split["scoped_count"],
        "out_of_scope_count": split["other_count"],
        "all_counts": session_kind_counts(all_sessions),
        "in_scope_counts": split["scoped_counts"],
        "out_of_scope_counts": split["other_counts"],
    }


def refresher_sessions(
    scope_state,
    parse_workspace_folders,
    list_ai_sessions,
    session_cwd_fast,
):
    all_sessions = dedupe_sessions(list_ai_sessions([], parse_workspace_folders))
    split = split_meter_sessions(all_sessions, scope_state, session_cwd_fast)
    return {
        "scoped": split["scoped"],
        "other": split["other"],
        "all": all_sessions,
        "other_count": split["other_count"],
    }


def repo_live_session_health(
    repo_path,
    find_workspace_for,
    parse_workspace_folders,
    claude_log_dir,
    list_ai_sessions,
    session_cwd_fast,
):
    """Summarize whether this machine currently has live AI sessions linked to a repo."""
    meter = initial_meter_sessions(
        repo_path,
        "repo",
        find_workspace_for,
        parse_workspace_folders,
        claude_log_dir,
        list_ai_sessions,
        session_cwd_fast,
    )
    return {
        "linked_count": meter["in_scope_count"],
        "linked_counts": meter["in_scope_counts"],
        "linked_sessions": meter["sessions"],
        "machine_count": len(meter["all_sessions"]),
        "other_count": meter["out_of_scope_count"],
        "has_any": meter["has_any"],
    }
