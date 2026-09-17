import os
import re


def build_graph(path, run_cmd, graphify_cmd, log):
    """Build the graph and return a small status dict."""
    code, output = run_cmd(graphify_cmd() + ["update", path], log)
    html = os.path.join(path, "graphify-out", "graph.html")
    report = os.path.join(path, "graphify-out", "GRAPH_REPORT.md")
    return {
        "code": code,
        "output": output,
        "graph_html": html if os.path.exists(html) else None,
        "report": report if os.path.exists(report) else None,
    }


def install_selected_integrations(
    path,
    selected,
    hooks_enabled,
    custom_rule_files,
    run_cmd,
    graphify_cmd,
    write_routing_block,
    log,
    write_brevity_block=None,
    brevity_level=None,
    strict_mode="required_alerts",
):
    results = []
    for cmd in selected:
        if cmd in custom_rule_files:
            rule = os.path.join(path, custom_rule_files[cmd])
            write_routing_block(rule, log, strict_mode)
            if write_brevity_block:
                write_brevity_block(rule, brevity_level, log)
            log(f"[{cmd}] OK (rules file)\n")
            results.append({"cmd": cmd, "code": 0, "mode": "rules"})
        else:
            code, _ = run_cmd(graphify_cmd() + [cmd, "install"], log, cwd=path)
            log(f"[{cmd}] {'OK' if code == 0 else 'FAILED'}\n")
            results.append({"cmd": cmd, "code": code, "mode": "install"})
    hooks_result = None
    if hooks_enabled:
        if os.path.isdir(os.path.join(path, ".git")):
            code, _ = run_cmd(graphify_cmd() + ["hook", "install"], log, cwd=path)
            log(f"[git hooks] {'OK' if code == 0 else 'FAILED'}\n")
            hooks_result = code
        else:
            log("[git hooks] skipped - not a git repo\n")
            hooks_result = None
    return {"integrations": results, "hooks": hooks_result}


def ensure_gitignore_entry(path, entry, log):
    if not os.path.isdir(os.path.join(path, ".git")):
        return False
    gi = os.path.join(path, ".gitignore")
    try:
        existing = ""
        if os.path.exists(gi):
            with open(gi, encoding="utf-8", errors="replace") as f:
                existing = f.read()
        pattern = r"^" + re.escape(entry.rstrip("/")) + r"/?\s*$"
        if re.search(pattern, existing, re.MULTILINE):
            return False
        with open(gi, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(entry.rstrip("/") + "/\n")
        log(f"[.gitignore] added {entry.rstrip('/')}/\n")
        return True
    except OSError as exc:
        log(f"[.gitignore] could not update: {exc}\n")
        return False


STRICT_ENFORCING_MODES = ("required", "required_alerts")


def install_repo_mcp(path, merge_json_servers, log, strict_mode="required_alerts"):
    """Write per-repo MCP server configs (.vscode/mcp.json + .mcp.json).

    In enforcing strict modes (required/required_alerts) the unrestricted
    filesystem MCP server is NOT installed: it would hand the agent a
    full-repo read bypass in the very config that tells it to route reads
    through grafel-strict. Advisory mode keeps the filesystem server since
    strict enforcement isn't claimed there. Note merge_json_servers only
    adds entries, so a filesystem entry written earlier in advisory mode is
    not removed here (see KNOWN_ISSUES #9 on stale MCP entries).

    Paths: .vscode/mcp.json uses ${workspaceFolder} (documented VS Code MCP
    predefined-variable support) so the committed config is machine-portable.
    .mcp.json keeps a machine-absolute path — Claude Code does not document
    ${workspaceFolder}; merge_json_servers refreshes a stale absolute path on
    the next Grafel run on that machine."""
    context7_http = {"type": "http", "url": "https://mcp.context7.com/mcp"}
    helpers = install_graph_query_helpers(path, log)
    strict_stdio = {
        "command": helpers["mcp"],
        "args": [],
    }
    vscode_servers = {
        "context7": context7_http,
        "grafel-strict": {
            "type": "stdio",
            "command": "${workspaceFolder}/graphify-out/grafel-mcp.cmd",
            "args": [],
        },
    }
    claude_servers = {"context7": context7_http, "grafel-strict": strict_stdio}
    if strict_mode in STRICT_ENFORCING_MODES:
        log("[mcp] strict mode active - unrestricted filesystem MCP server skipped "
            "(reads go through grafel-strict)\n")
    else:
        fs_stdio = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", path],
        }
        vscode_servers["filesystem"] = {"type": "stdio", **fs_stdio}
        claude_servers["filesystem"] = fs_stdio
    merge_json_servers(
        os.path.join(path, ".vscode", "mcp.json"),
        "servers",
        vscode_servers,
        log,
    )
    merge_json_servers(
        os.path.join(path, ".mcp.json"),
        "mcpServers",
        claude_servers,
        log,
    )
    return {
        "vscode": os.path.join(path, ".vscode", "mcp.json"),
        "claude": os.path.join(path, ".mcp.json"),
    }


def install_graph_query_helpers(path, log):
    out_dir = os.path.join(path, "graphify-out")
    os.makedirs(out_dir, exist_ok=True)
    def helper_text(command_name):
        extra = " ".join(f'"{part}"' for part in command_name.split())
        return (
        "@echo off\n"
        "setlocal\n"
        "for %%I in (\"%~dp0..\") do set REPO=%%~fI\n"
        "if exist \"%LocalAppData%\\Programs\\Grafel\\GrafelCLI.exe\" (\n"
            f"  \"%LocalAppData%\\Programs\\Grafel\\GrafelCLI.exe\" --proof-command \"%REPO%\" {extra} %*\n"
        "  exit /b %errorlevel%\n"
        ")\n"
        "where GrafelCLI.exe >nul 2>nul\n"
        "if not errorlevel 1 (\n"
            f"  GrafelCLI.exe --proof-command \"%REPO%\" {extra} %*\n"
        "  exit /b %errorlevel%\n"
        ")\n"
        "if exist \"%REPO%\\grafel.py\" (\n"
            f"  python \"%REPO%\\grafel.py\" --proof-command \"%REPO%\" {extra} %*\n"
        "  exit /b %errorlevel%\n"
        ")\n"
            f"graphify {command_name} %*\n"
        )
    helpers = {
        "query": os.path.join(out_dir, "grafel-query.cmd"),
        "path": os.path.join(out_dir, "grafel-path.cmd"),
        "explain": os.path.join(out_dir, "grafel-explain.cmd"),
        "save-result": os.path.join(out_dir, "grafel-save-result.cmd"),
    }
    for command_name, cmd_path in helpers.items():
        with open(cmd_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(helper_text(command_name))
        log(f"[proof] installed {os.path.relpath(cmd_path, path)}\n")
    mcp_path = os.path.join(out_dir, "grafel-mcp.cmd")
    mcp_text = (
        "@echo off\n"
        "setlocal\n"
        "for %%I in (\"%~dp0..\") do set REPO=%%~fI\n"
        "if exist \"%LocalAppData%\\Programs\\Grafel\\GrafelCLI.exe\" (\n"
        "  \"%LocalAppData%\\Programs\\Grafel\\GrafelCLI.exe\" --run-grafel-strict-mcp \"%REPO%\"\n"
        "  exit /b %errorlevel%\n"
        ")\n"
        "where GrafelCLI.exe >nul 2>nul\n"
        "if not errorlevel 1 (\n"
        "  GrafelCLI.exe --run-grafel-strict-mcp \"%REPO%\"\n"
        "  exit /b %errorlevel%\n"
        ")\n"
        "if exist \"%REPO%\\grafel.py\" (\n"
        "  python \"%REPO%\\grafel.py\" --run-grafel-strict-mcp \"%REPO%\"\n"
        "  exit /b %errorlevel%\n"
        ")\n"
        "echo Grafel strict MCP requires GrafelCLI.exe or source checkout.\n"
        "exit /b 1\n"
    )
    with open(mcp_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(mcp_text)
    helpers["mcp"] = mcp_path
    log(f"[proof] installed {os.path.relpath(mcp_path, path)}\n")
    return helpers


def write_repo_routing(path, write_routing_block, log, strict_mode="required_alerts"):
    install_graph_query_helpers(path, log)
    targets = [
        os.path.join(path, "CLAUDE.md"),
        os.path.join(path, "AGENTS.md"),
        os.path.join(path, ".github", "copilot-instructions.md"),
    ]
    for target in targets:
        write_routing_block(target, log, strict_mode)
    return targets


def write_repo_brevity(path, write_brevity_block, log, level):
    targets = [
        os.path.join(path, "CLAUDE.md"),
        os.path.join(path, "AGENTS.md"),
        os.path.join(path, ".github", "copilot-instructions.md"),
    ]
    for target in targets:
        write_brevity_block(target, level, log)
    return targets
