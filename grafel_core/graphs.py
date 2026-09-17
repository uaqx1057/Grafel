import json
import os


def graph_wired_status(path, routing_start):
    """Return whether a repo has a built graph and routing instructions installed."""
    has_graph = os.path.exists(os.path.join(path, "graphify-out", "graph.json"))
    has_routing = False
    for rel in ("CLAUDE.md", "AGENTS.md", os.path.join(".github", "copilot-instructions.md")):
        fp = os.path.join(path, rel)
        try:
            if os.path.exists(fp):
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    if routing_start in f.read():
                        has_routing = True
                        break
        except OSError:
            continue
    return has_graph, has_routing


def repo_install_health(path, routing_start, brevity_start):
    """Return install/readiness flags for the current repo."""
    has_graph, has_routing = graph_wired_status(path, routing_start)
    has_brevity = False
    for rel in ("CLAUDE.md", "AGENTS.md", os.path.join(".github", "copilot-instructions.md")):
        fp = os.path.join(path, rel)
        try:
            if os.path.exists(fp):
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    if brevity_start in f.read():
                        has_brevity = True
                        break
        except OSError:
            continue
    return {
        "graph_built": has_graph,
        "routing_installed": has_routing,
        "brevity_installed": has_brevity,
    }


def workspace_wire_summary(folders, routing_start):
    wired = []
    unwired = []
    for folder in folders:
        has_graph, has_routing = graph_wired_status(folder, routing_start)
        (wired if has_graph and has_routing else unwired).append(os.path.basename(folder))
    return {"wired": wired, "unwired": unwired, "total": len(folders)}


def _iter_source_files(path, code_ext, skip_dirs):
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in names:
            if os.path.splitext(name)[1].lower() in code_ext:
                yield os.path.join(root, name)


def graph_artifact_state(path, code_ext, skip_dirs):
    """Return freshness information for graph artifacts versus source files."""
    out_dir = os.path.join(path, "graphify-out")
    graph_json = os.path.join(out_dir, "graph.json")
    report_md = os.path.join(out_dir, "GRAPH_REPORT.md")
    graph_exists = os.path.exists(graph_json)
    report_exists = os.path.exists(report_md)
    graph_mtime = os.path.getmtime(graph_json) if graph_exists else 0
    report_mtime = os.path.getmtime(report_md) if report_exists else 0
    newest_source = 0
    for fp in _iter_source_files(path, code_ext, skip_dirs):
        try:
            newest_source = max(newest_source, os.path.getmtime(fp))
        except OSError:
            continue
    graph_stale = graph_exists and newest_source > graph_mtime
    report_stale = report_exists and newest_source > report_mtime
    return {
        "graph_exists": graph_exists,
        "report_exists": report_exists,
        "graph_stale": graph_stale,
        "report_stale": report_stale,
        "graph_mtime": graph_mtime,
        "report_mtime": report_mtime,
        "newest_source_mtime": newest_source,
    }


def graph_report_text(path):
    rep = os.path.join(path, "graphify-out", "GRAPH_REPORT.md")
    try:
        if os.path.exists(rep):
            with open(rep, encoding="utf-8", errors="ignore") as f:
                return f.read()
    except OSError:
        return "(could not read GRAPH_REPORT.md)"
    return "(no GRAPH_REPORT.md yet - run a scan)"


def node_ids(graph):
    ids = set()
    for node in graph.get("nodes", []):
        ids.add(node.get("id") or node.get("name") or json.dumps(node, sort_keys=True)[:80])
    return ids


def diff_graph_snapshot(graph_path, snapshot_path):
    if not os.path.exists(graph_path):
        return {"error": "missing_graph"}
    try:
        with open(graph_path, encoding="utf-8", errors="ignore") as f:
            current = json.load(f)
    except (OSError, ValueError) as exc:
        return {"error": str(exc)}
    current_ids = node_ids(current)
    if not os.path.exists(snapshot_path):
        previous = {"nodes": []}
        baseline = True
    else:
        try:
            with open(snapshot_path, encoding="utf-8", errors="ignore") as f:
                previous = json.load(f)
        except (OSError, ValueError):
            previous = {"nodes": []}
        baseline = False
    previous_ids = node_ids(previous)
    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(current, f)
        snapshot_updated = True
    except OSError:
        snapshot_updated = False
    return {
        "baseline": baseline,
        "current_count": len(current_ids),
        "added": added,
        "removed": removed,
        "snapshot_updated": snapshot_updated,
    }
