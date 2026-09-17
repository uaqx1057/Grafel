import json
import os
import re


ROUTING_START = "<!-- graphify-tool:routing:start -->"
ROUTING_END = "<!-- graphify-tool:routing:end -->"
STRICT_MODE_LEVELS = {
    "advisory": {
        "title": "Advisory",
        "policy": "Prefer Grafel helper commands first for codebase questions.",
    },
    "required": {
        "title": "Required",
        "policy": "Grafel helper commands are mandatory before repo file inspection.",
    },
    "required_alerts": {
        "title": "Required + Violation Alerts",
        "policy": "Grafel helper commands are mandatory and bypasses should be treated as policy violations.",
    },
}


def build_routing_block(strict_mode="required_alerts"):
    mode = strict_mode if strict_mode in STRICT_MODE_LEVELS else "advisory"
    enforcement = {
        "advisory": (
            "- For any codebase question, first run `graphify-out\\grafel-query.cmd \"<question>\"`.\n"
            "- Then inspect only the files returned by the graph result.\n"
            "- If graph artifacts look stale, run `INITIATE SCAN` or `WATCH` before continuing.\n"
        ),
        "required": (
            "- For any codebase question, you MUST first run `graphify-out\\grafel-query.cmd \"<question>\"`.\n"
            "- If MCP is available, use the `grafel-strict` tools (`grafel.query`, then `grafel.read_file`) instead of direct filesystem tools.\n"
            "- Only after that may you inspect files returned by the graph result.\n"
            "- Do NOT perform repo-wide grep, recursive listing, or broad file reads first.\n"
            "- If the graph is stale or missing, run `INITIATE SCAN` or `WATCH` first.\n"
        ),
        "required_alerts": (
            "- For any codebase question, you MUST first run `graphify-out\\grafel-query.cmd \"<question>\"`.\n"
            "- If MCP is available, use the `grafel-strict` tools (`grafel.query`, then `grafel.read_file`) instead of direct filesystem tools.\n"
            "- Only after that may you inspect files returned by the graph result.\n"
            "- Do NOT perform repo-wide grep, recursive listing, or broad file reads first.\n"
            "- If the graph is stale or missing, run `INITIATE SCAN` or `WATCH` first.\n"
            "- Treat any bypass of this flow as a Grafel policy violation and surface it clearly.\n"
        ),
    }[mode]
    return f"""
{ROUTING_START}
## Tool routing (token efficiency)
Strict mode: {STRICT_MODE_LEVELS[mode]['title']}
Policy: {STRICT_MODE_LEVELS[mode]['policy']}
{enforcement}- Use sibling helpers where relevant: `graphify-out\\grafel-path.cmd`, `graphify-out\\grafel-explain.cmd`, and `graphify-out\\grafel-save-result.cmd`.
- Library/framework documentation (Flutter, Laravel, Django, Node, etc.): use the Context7 MCP server (resolve-library-id + query-docs) instead of guessing APIs from memory.
- Answer reuse: before querying, check graphify-out/memory/ for a saved answer to the same question. After answering a non-trivial question well, save it with `graphify-out\\grafel-save-result.cmd "<question>"`.
- Quiet output: run tests/builds with filtered or quiet flags (e.g. `--compact`, `2>&1 | tail -20`). Never dump full verbose logs into the conversation - quote only the failing lines.
- Cost discipline: prefer minimal diffs/patches over full-file rewrites; batch related edits and questions into ONE request instead of many small ones; use the cheapest capable model for routine work and reserve premium / high-reasoning models for genuinely hard problems; prefer `/compact` over `/clear` to keep the prompt cache warm.
- Checkpoints: after each working state, make a git commit. If a change breaks things, revert to the last commit instead of debugging your own regressions from scratch.
- Self-updating docs: when you discover a non-obvious fact about this codebase (convention, gotcha, build quirk), append it to this file so future sessions never re-discover it.
{ROUTING_END}
"""


def write_routing_block(path, log=None, strict_mode="required_alerts"):
    """Idempotently write or refresh the tool-routing block in an agent rules file."""
    block_re = re.compile(
        re.escape(ROUTING_START) + r".*?" + re.escape(ROUTING_END), re.DOTALL
    )
    name = os.path.basename(path)
    block = build_routing_block(strict_mode).strip()
    try:
        existing = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                existing = f.read()
        if ROUTING_START in existing and ROUTING_END in existing:
            updated = block_re.sub(lambda _m: block, existing)
            if updated == existing:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
            if log:
                log(f"[routing] updated {name}\n")
            return
        if ROUTING_START in existing:
            # Orphaned START without END (crash mid-write, manual edit).
            # Appending a second full block here would let the NEXT run's
            # START..END substitution greedily swallow everything between the
            # orphaned START and the new block's END — silently deleting user
            # content. Recover explicitly instead: the region from the orphaned
            # START to EOF is the half-written Grafel-owned block, so replace
            # exactly that region with a fresh block and keep everything above.
            idx = existing.index(ROUTING_START)
            with open(path, "w", encoding="utf-8") as f:
                f.write(existing[:idx] + block + "\n")
            if log:
                log(f"[routing] {name}: recovered unterminated routing block "
                    "(replaced from marker to end of file)\n")
            return
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(build_routing_block(strict_mode))
        if log:
            log(f"[routing] added routing to {name}\n")
    except OSError as exc:
        if log:
            log(f"[routing] {name}: {exc}\n")


def parse_workspace_folders(ws_file):
    """Read a VS Code .code-workspace JSONC file and return existing member folders."""
    try:
        with open(ws_file, encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except OSError:
        return []
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    raw = re.sub(r"(?m)//.*$", "", raw)
    raw = re.sub(r",(\s*[}\]])", r"\1", raw)
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    base = os.path.dirname(ws_file)
    out = []
    for folder in data.get("folders", []) or []:
        rel_path = folder.get("path") if isinstance(folder, dict) else None
        if not rel_path:
            continue
        abs_path = os.path.normpath(os.path.join(base, rel_path))
        if os.path.isdir(abs_path) and abs_path not in out:
            out.append(abs_path)
    return out


def merge_json_servers(file_path, root_key, servers, log):
    """Merge MCP server entries into a JSON config.

    Entries Grafel manages are added when missing and refreshed when their
    content differs from what Grafel would write now (a stale command — old
    exe path, moved repo — must not persist forever). Entries Grafel does not
    manage (names not in `servers`) are never touched, and an identical merge
    leaves the file byte-for-byte unchanged (idempotent)."""
    data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            log(f"[mcp] {os.path.basename(file_path)} exists but is not valid JSON - skipped\n")
            return
    section = data.setdefault(root_key, {})
    added = []
    updated = []
    for name, cfg in servers.items():
        if name not in section:
            section[name] = cfg
            added.append(name)
        elif section[name] != cfg:
            section[name] = cfg
            updated.append(name)
    if not added and not updated:
        log(f"[mcp] {os.path.basename(file_path)} already configured\n")
        return
    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    changes = []
    if added:
        changes.append(f"added {', '.join(added)}")
    if updated:
        changes.append(f"updated {', '.join(updated)}")
    log(f"[mcp] {os.path.basename(file_path)}: {'; '.join(changes)}\n")
