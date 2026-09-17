# Graph Report - Graftool  (2026-07-12)

## Corpus Check
- 51 files · ~17,653,457 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 672 nodes · 1274 edges · 45 communities (38 shown, 7 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 51 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- .__init__
- Community 1
- App
- ._add_session_tab
- grafel.py
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- App
- .log
- _feat_test.py
- .browse
- .run_batch
- .configure
- ._copilot_monitor
- Chat digest — Grafel Live Meter rework (2026-07-08)
- App
- Copilot Chat (VS Code) — Copilot·Graftool·10bbef01 (2026-07-08)
- ServerConfigTests
- .__init__
- .register_mcp_server
- Copilot Chat (VS Code) — Copilot·Graftool·cef900b1 (2026-07-08)
- sessions.py
- sessions.py
- grafel.py
- __init__.py
- savings.py
- .open_new_window
- resource_path
- .run_ask
- .run_batch
- .toggle_meter
- graphs.py
- ._session_savings_state
- ._savings_health_snapshot
- Grafel — Known Issues (2026-07-11)
- resource_path
- ._export_chats_worker
- ._scan_usage_worker
- merge_json_servers

## God Nodes (most connected - your core abstractions)
1. `App` - 114 edges
2. `Copilot Chat (VS Code) — Copilot | Graftool | 10bbef01 (2026-07-08)` - 73 edges
3. `GrafelCoreTests` - 30 edges
4. `graphify_cmd()` - 16 edges
5. `GrafelProductTests` - 15 edges
6. `run_cmd()` - 14 edges
7. `Grafel — Product Document` - 14 edges
8. `parse_workspace_folders()` - 12 edges
9. `Grafel — Known Issues (2026-07-11)` - 12 edges
10. `run_headless()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `build_graph()` --calls--> `graphify_cmd()`  [INFERRED]
  grafel_core/workflows.py → grafel.py
- `build_graph()` --calls--> `run_cmd()`  [INFERRED]
  grafel_core/workflows.py → grafel.py
- `run_headless()` --indirect_call--> `merge_json_servers()`  [INFERRED]
  grafel.py → grafel_core/config.py
- `GrafelCoreTests` --uses--> `StrictGateway`  [INFERRED]
  tests/test_grafel_core.py → grafel_core/strict_mcp.py
- `install_selected_integrations()` --calls--> `graphify_cmd()`  [INFERRED]
  grafel_core/workflows.py → grafel.py

## Import Cycles
- None detected.

## Communities (45 total, 7 thin omitted)

### Community 0 - ".__init__"
Cohesion: 0.06
Nodes (14): engine_available(), find_graphify(), Let the user pick a .code-workspace file and wire every interlinked         proj, Measure real token savings: full codebase context vs Grafel's graph         inde, Ask a real codebase question and compare, in actual tokens, what an agent, Ask a question; show the graph answer AND the real per-prompt cost         (toke, Graph every git repo directly under a chosen parent folder., Scan REAL local AI-tool usage logs (token counts only) and report actual (+6 more)

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (11): 1. Core tool (build → graph → wire AI), 2. AI tool integrations (query the graph, not the repo), 3. MCP + tool routing, 4. Proof & trust (the sales engine), 5. Core power features, 6. Packaging & branding, 7. Business / go-to-market, 8. Token-saving strategies (advice — apply as habits) (+3 more)

### Community 2 - "App"
Cohesion: 0.08
Nodes (8): build_installer_command(), detect_inno_setup(), read_app_version(), release_preflight(), run_installer_build(), FakeProcess, TempRepoHarness, GrafelProductTests

### Community 3 - "._add_session_tab"
Cohesion: 0.10
Nodes (25): build_optimizer_plan(), append_graph_use_event(), graph_use_summary(), proof_log_path(), read_graph_use_events(), count_tokens(), Exact token count via tiktoken if available; else ~4 chars/token., content_result() (+17 more)

### Community 4 - "grafel.py"
Cohesion: 0.18
Nodes (17): codex_session_meta(), enrich_session(), friendly_project_name(), iter_claude_usage_entries(), list_ai_sessions(), list_claude_sessions(), list_codex_sessions(), list_vscode_copilot_sessions() (+9 more)

### Community 5 - "Community 5"
Cohesion: 0.29
Nodes (6): C:\Users\Usman\OneDrive - iLab\Desktop\Graftool\graphify-out\grafel-mcp.cmd, npx, context7, filesystem, grafel-strict, @modelcontextprotocol/server-filesystem

### Community 6 - "Community 6"
Cohesion: 0.67
Nodes (3): draw_logo(), main(), Generate grafel.ico + grafel.png - neon node-graph logo on dark tile.

### Community 7 - "Community 7"
Cohesion: 0.40
Nodes (4): Grafel Brevity Mode (Ultra), graphify, Tool routing (token efficiency), Tool routing (token efficiency)

### Community 8 - "Community 8"
Cohesion: 0.40
Nodes (4): Grafel Brevity Mode (Ultra), graphify, Tool routing (token efficiency), Tool routing (token efficiency)

### Community 9 - "Community 9"
Cohesion: 0.40
Nodes (4): Grafel Brevity Mode (Ultra), graphify, Tool routing (token efficiency), Tool routing (token efficiency)

### Community 10 - "App"
Cohesion: 0.12
Nodes (16): 10. Roadmap ideas, 11. Current status, 1. What Grafel is, 2. The problem it solves, 3. How it works (pipeline), 3a. Savings Report (proof of value), 4. Architecture, 5. Installation & requirements (+8 more)

### Community 11 - ".log"
Cohesion: 0.33
Nodes (5): Findings, Grafel Audit And Test Matrix, Manual Smoke Checks, Refactor Status, Test Inventory

### Community 12 - "_feat_test.py"
Cohesion: 0.23
Nodes (13): db(), get_graph(), ingest(), init(), issue(), put_graph(), Grafel backend - license validation, cloud graph sync, auto-update, analytics., Fail fast on obviously unsafe production defaults. (+5 more)

### Community 13 - ".browse"
Cohesion: 0.22
Nodes (8): 1. Mission (why this exists), 2. Current status, 3. Architecture, 4. Key domain facts (hard-won, don't re-discover), 5. Build / run / test, 6. Open items / next steps, 7. How to resume, Grafel — Handoff / Resume Point

### Community 14 - ".run_batch"
Cohesion: 0.29
Nodes (6): Endpoints, Environment, Grafel Backend (starter), Run locally, Run with Docker, Wiring the desktop app

### Community 15 - ".configure"
Cohesion: 0.13
Nodes (5): AdminTokenTests, GraphOwnershipTests, issue_license(), SeatLimitTests, UploadSizeCapTests

### Community 16 - "._copilot_monitor"
Cohesion: 0.09
Nodes (29): watch_event_kind(), classify_claude_model(), claude_baseline_update(), claude_prompt_summary(), copilot_apply_events(), copilot_ready_indexes(), meter_fallback_message(), meter_refresh_sessions() (+21 more)

### Community 17 - "Chat digest — Grafel Live Meter rework (2026-07-08)"
Cohesion: 0.33
Nodes (5): Chat digest — Grafel Live Meter rework (2026-07-08), Still pending / next steps, Verified against real data, What the user reported, What was changed in grafel.py (all compile-verified)

### Community 18 - "App"
Cohesion: 0.22
Nodes (8): 1. Runtime extraction, 2. Deterministic integration harness, 3. Release hardening, Current limitations, Goal, Grafel Product Evolution Plan, Implementation tracks, Near-term next steps

### Community 19 - "Copilot Chat (VS Code) — Copilot·Graftool·10bbef01 (2026-07-08)"
Cohesion: 0.03
Nodes (73): Copilot Chat (VS Code) — Copilot | Graftool | 10bbef01 (2026-07-08), Prompt 1, Prompt 10, Prompt 11, Prompt 12, Prompt 13, Prompt 14, Prompt 15 (+65 more)

### Community 21 - ".__init__"
Cohesion: 0.15
Nodes (13): backup_memory_file(), brevity_dashboard_lines(), brevity_level_config(), brevity_rule_block(), can_compress_memory_file(), compress_memory_file(), compress_memory_text(), compress_plain_line() (+5 more)

### Community 23 - ".register_mcp_server"
Cohesion: 0.27
Nodes (16): dedupe_sessions(), find_git_root(), initial_meter_sessions(), meter_scope_state(), normalize_scope_path(), path_is_related(), Summarize whether this machine currently has live AI sessions linked to a repo., refresher_sessions() (+8 more)

### Community 24 - "Copilot Chat (VS Code) — Copilot·Graftool·cef900b1 (2026-07-08)"
Cohesion: 0.29
Nodes (4): Copilot Chat (VS Code) — Copilot | Graftool | cef900b1 (2026-07-08), Prompt 1, Prompt 2, AI chat digests for this repo

### Community 26 - "sessions.py"
Cohesion: 0.13
Nodes (12): build_routing_block(), Idempotently write or refresh the tool-routing block in an agent rules file., write_routing_block(), build_graph(), install_graph_query_helpers(), install_repo_mcp(), Build the graph and return a small status dict., write_repo_routing() (+4 more)

### Community 27 - "sessions.py"
Cohesion: 0.29
Nodes (3): Atomic write: dump to a temp file in the same directory, then     os.replace() i, save_config(), Realized, meter-proven savings ONLY (live session tailing). The         hypothet

### Community 28 - "grafel.py"
Cohesion: 0.16
Nodes (9): ensure_gitignore_entry(), install_selected_integrations(), graphify_cmd(), Wire every selected AI tool to the graph. Tools graphify supports use its, Keep the graph local: in the project for AI tools, out of git., Configure Context7 + Filesystem MCP servers per repo and append         tool-rou, Resolve how to invoke the graphify engine, in preference order:     system CLI -, Run a command, stream output lines to log(). Returns (exit_code, full_output). (+1 more)

### Community 30 - "savings.py"
Cohesion: 0.16
Nodes (14): ab_report_lines(), graph_token_stats(), iter_code_files(), prompt_comparison_lines(), question_file_matches(), question_keywords(), question_match_stats(), Yield readable code-like files under a repo, skipping noisy folders. (+6 more)

### Community 31 - ".open_new_window"
Cohesion: 0.20
Nodes (5): reduction_percent(), Launch a second independent Grafel window (own process, no instance         lock, Start the file-watcher on a repo. Safe to call from any thread; the         watc, Pump watcher stdout into the console and flag if it dies immediately., Hypothetical/what-if deltas (savings report, A/B test, ask, benchmark):

### Community 34 - ".run_ask"
Cohesion: 0.15
Nodes (7): write_brevity_block(), write_repo_brevity(), Cumulative, persisted counters — kept honestly separate: realized         saving, Render a shareable PNG savings card from the last measurement., Register a daily Windows scheduled task to rebuild this repo's graph., Show a folder picker (blocking); return a path or ''. Uses the modern         Wi, Thread-safe: queue the line for a specific tab; a single UI timer         flushe

### Community 36 - ".toggle_meter"
Cohesion: 0.10
Nodes (14): Return install/readiness flags for the current repo., repo_install_health(), meter_machine_sessions_message(), meter_start_state(), meter_unscoped_console_notice(), codex_session_cwd_fast(), Best-effort evidence of broad repo exploration without graph-first behavior., session_bypass_risk() (+6 more)

### Community 37 - "graphs.py"
Cohesion: 0.19
Nodes (11): diff_graph_snapshot(), graph_artifact_state(), graph_report_text(), graph_wired_status(), _iter_source_files(), node_ids(), Return whether a repo has a built graph and routing instructions installed., Return freshness information for graph artifacts versus source files. (+3 more)

### Community 39 - "._savings_health_snapshot"
Cohesion: 0.28
Nodes (7): parse_workspace_folders(), Read a VS Code .code-workspace JSONC file and return existing member folders., accumulate_usage_bucket(), session_cwd(), find_workspace_for(), Find a .code-workspace file that includes repo_path among its folders., Replay a session's cost history into its tab, then tail it live. Runs per

### Community 40 - "Grafel — Known Issues (2026-07-11)"
Cohesion: 0.15
Nodes (12): 0. CLI proof-command output — attempted fix shipped, confirmed NOT working, 1. "Proven savings" dashboard number is not measuring what it claims, 2. Every session's cache-cold first prompt is auto-"PROVEN", 3. Log tailing drops or duplicates data on partial writes, 4. Server: no owner check on graph upload/download, 5. Strict mode is undermined by Grafel's own MCP wiring, 6. `~/.grafel.json` writes are racy and non-atomic, 7. Live meter prices everything at Sonnet rates (+4 more)

### Community 42 - "._export_chats_worker"
Cohesion: 0.39
Nodes (6): claude_exchanges(), _claude_text_content(), copilot_exchanges(), trim_text(), claude_log_dir(), is_text_user_content()

### Community 44 - "merge_json_servers"
Cohesion: 0.33
Nodes (4): merge_json_servers(), Add missing MCP server entries to a JSON config without clobbering existing ones, Resolve how to launch graphify's MCP server for this graph., Register the repo's graph as an MCP server so agents query it natively.

## Knowledge Gaps
- **150 isolated node(s):** `context7`, `npx`, `@modelcontextprotocol/server-filesystem`, `C:\Users\Usman\OneDrive - iLab\Desktop\Graftool\graphify-out\grafel-mcp.cmd`, `graphify` (+145 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `App` connect `resource_path` to `.__init__`, `.run_ask`, `._add_session_tab`, `.toggle_meter`, `graphs.py`, `grafel.py`, `._savings_health_snapshot`, `._session_savings_state`, `._export_chats_worker`, `merge_json_servers`, `._copilot_monitor`, `sessions.py`, `grafel.py`, `savings.py`, `.open_new_window`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Why does `GrafelCoreTests` connect `resource_path` to `._add_session_tab`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `graphify_cmd()` (e.g. with `.install_integrations()` and `.pipeline()`) actually correct?**
  _`graphify_cmd()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `context7`, `npx`, `@modelcontextprotocol/server-filesystem` to the rest of the system?**
  _220 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `.__init__` be split into smaller, more focused modules?**
  _Cohesion score 0.06451612903225806 - nodes in this community are weakly interconnected._
- **Should `App` be split into smaller, more focused modules?**
  _Cohesion score 0.08045977011494253 - nodes in this community are weakly interconnected._
- **Should `._add_session_tab` be split into smaller, more focused modules?**
  _Cohesion score 0.0990990990990991 - nodes in this community are weakly interconnected._