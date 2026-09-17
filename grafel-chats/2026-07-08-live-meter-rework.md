# Chat digest — Grafel Live Meter rework (2026-07-08)

Agents: read this instead of replaying the full chat. Covers the Copilot session
`cef900b1` (Graftool workspace).

## What the user reported
1. Live Meter output was cost-first (`session so far: $1948 billed`) — looks unreal;
   user is on Claude Pro / ChatGPT Pro / Copilot subscriptions and never pays per token.
   Wanted **requests + token usage** as the primary display.
2. Meter showed OTHER projects' sessions when Graftool was the target — root cause:
   **no Claude Code session dir exists for Graftool** (`~/.claude/projects/C--Users-Usman-OneDrive---iLab-Desktop-Graftool` missing), so the "show ALL sessions" fallback kicked in.
   But **GitHub Copilot sessions DO exist** for Graftool.
3. Wanted multiple Grafel windows (single-instance lock blocked them).
4. Wanted chat→markdown digests so agents can resume context cheaply (this file),
   and a Grafel feature that generates such digests for any repo.

## What was changed in grafel.py (all compile-verified)
- **Token-first meter**: `_session_monitor.flush` now prints
  `tokens: N (cache-read … · out …)` first; `$` demoted to dim "API-equiv" line;
  session tail = `N requests · X tokens ($Y API-equiv) · Z tok recoverable`.
  New module helper `fmt_tokens(n)` (1,234 / 45.2k / 1.5M / 2.34B).
- **VS Code Copilot Chat support** (new — key discovery):
  - Sessions live at `%APPDATA%\Code\User\workspaceStorage\<hash>\chatSessions\<id>.jsonl`;
    `<hash>\workspace.json` maps to the repo folder (`folder` URI or `workspace` file).
  - Log format: line 1 = kind:0 snapshot; then kind:2 `k=["requests"]` appends a request
    (user prompt at `v[i].message.text`); kind:2 `k=["requests",i,"response"]` appends
    response parts (text parts have string `value` and no `kind`/`markdownContent`);
    kind:1 `k=["requests",i,"promptTokens"|"completionTokens"|"copilotCredits"]` sets usage.
  - New helpers: `_vscode_storage_roots`, `_uri_to_path`, `vscode_chat_dirs_for`,
    `list_vscode_copilot_sessions` (kind='copilot'), `iter_vscode_chat_events`.
  - `toggle_meter` merges Claude + Copilot sessions; `_start_session_monitor` dispatches
    to new `_copilot_monitor` (replay + live tail; shows requests, tokens, premium credits).
    `_session_refresher` also picks up new Copilot chats. Scope kept in `_meter_scope_folders`.
- **Multi-window**: `--new-window` argv flag skips the port-51799 single-instance lock;
  new "⧉ NEW WIN" button → `open_new_window()`. `lock` can be None — `_accept_focus`
  is only started when lock exists.
- **Chat→MD export**: new "⧩ CHAT MD" button + Analyze-menu entry → `export_chats` /
  `_export_chats_worker`. Writes `<repo>/grafel-chats/` digests (`claude-*.md`,
  `copilot-vscode-*.md`, `copilot-cli-*.md` from `~/.copilot/session-store.db`
  sessions/turns tables) + `index.md`. Trimmed to 400 chars per side, 200 prompts/file.

## Verified against real data
- `list_vscode_copilot_sessions([Graftool])` → 2 sessions (this chat = 2 requests,
  and a 72-request session, 40.1M prompt tokens, ~30.6k credits summed over sets —
  note: usage events are repeated SETS per request, so per-request value = LAST set,
  not the sum; the monitor stores by index so it's correct, but naive summing overcounts).

## Still pending / next steps
- Rebuild exe via `.\build.bat` to ship these changes.
- Dead code to delete: `_meter_worker`, `_pick_session`, `active_claude_session`.
- Consider adding grafel-chats/ to .gitignore handling (contains chat text).
