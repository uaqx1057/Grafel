# Graph Report - Graftool  (2026-07-09)

## Corpus Check
- 44 files · ~17,639,460 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 492 nodes · 900 edges · 29 communities (24 shown, 5 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 48 edges (avg confidence: 0.76)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- .__init__
- Community 1
- App
- ._add_session_tab
- .register_mcp_server
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
- .log
- ._copilot_monitor
- Chat digest — Grafel Live Meter rework (2026-07-08)
- App
- Copilot Chat (VS Code) — Copilot·Graftool·10bbef01 (2026-07-08)
- ServerConfigTests
- .__init__
- ._session_refresher
- Copilot Chat (VS Code) — Copilot·Graftool·cef900b1 (2026-07-08)
- run_headless
- .install_mcp
- __init__.py

## God Nodes (most connected - your core abstractions)
1. `App` - 86 edges
2. `Copilot Chat (VS Code) — Copilot | Graftool | 10bbef01 (2026-07-08)` - 73 edges
3. `GrafelCoreTests` - 17 edges
4. `graphify_cmd()` - 15 edges
5. `run_cmd()` - 14 edges
6. `Grafel — Product Document` - 13 edges
7. `run_headless()` - 11 edges
8. `parse_workspace_folders()` - 11 edges
9. `initial_meter_sessions()` - 11 edges
10. `refresher_sessions()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `build_graph()` --calls--> `graphify_cmd()`  [INFERRED]
  grafel_core/workflows.py → grafel.py
- `install_selected_integrations()` --calls--> `graphify_cmd()`  [INFERRED]
  grafel_core/workflows.py → grafel.py
- `build_graph()` --calls--> `run_cmd()`  [INFERRED]
  grafel_core/workflows.py → grafel.py
- `install_selected_integrations()` --calls--> `run_cmd()`  [INFERRED]
  grafel_core/workflows.py → grafel.py
- `run_headless()` --indirect_call--> `merge_json_servers()`  [INFERRED]
  grafel.py → grafel_core/config.py

## Import Cycles
- None detected.

## Communities (29 total, 5 thin omitted)

### Community 0 - ".__init__"
Cohesion: 0.07
Nodes (14): engine_available(), find_graphify(), Let the user pick a .code-workspace file and wire every interlinked         pro, Measure real token savings: full codebase context vs Grafel's graph         ind, Ask a real codebase question and compare, in actual tokens, what an agent, Ask a question; show the graph answer AND the real per-prompt cost         (tok, Graph every git repo directly under a chosen parent folder., Scan REAL local AI-tool usage logs (token counts only) and report actual (+6 more)

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (11): 1. Core tool (build → graph → wire AI), 2. AI tool integrations (query the graph, not the repo), 3. MCP + tool routing, 4. Proof & trust (the sales engine), 5. Core power features, 6. Packaging & branding, 7. Business / go-to-market, 8. Token-saving strategies (advice — apply as habits) (+3 more)

### Community 2 - "App"
Cohesion: 0.10
Nodes (8): build_installer_command(), detect_inno_setup(), read_app_version(), release_preflight(), run_installer_build(), FakeProcess, TempRepoHarness, GrafelProductTests

### Community 4 - ".register_mcp_server"
Cohesion: 0.14
Nodes (12): diff_graph_snapshot(), graph_artifact_state(), graph_report_text(), graph_wired_status(), _iter_source_files(), node_ids(), Return freshness information for graph artifacts versus source files., Return whether a repo has a built graph and routing instructions installed. (+4 more)

### Community 5 - "Community 5"
Cohesion: 0.40
Nodes (4): npx, context7, filesystem, @modelcontextprotocol/server-filesystem

### Community 6 - "Community 6"
Cohesion: 0.67
Nodes (3): draw_logo(), main(), Generate grafel.ico + grafel.png - neon node-graph logo on dark tile.

### Community 7 - "Community 7"
Cohesion: 0.50
Nodes (3): graphify, Tool routing (token efficiency), Tool routing (token efficiency)

### Community 8 - "Community 8"
Cohesion: 0.50
Nodes (3): graphify, Tool routing (token efficiency), Tool routing (token efficiency)

### Community 9 - "Community 9"
Cohesion: 0.50
Nodes (3): graphify, Tool routing (token efficiency), Tool routing (token efficiency)

### Community 10 - "App"
Cohesion: 0.12
Nodes (15): 10. Roadmap ideas, 11. Current status, 1. What Grafel is, 2. The problem it solves, 3. How it works (pipeline), 3a. Savings Report (proof of value), 4. Architecture, 5. Installation & requirements (+7 more)

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

### Community 15 - ".log"
Cohesion: 0.07
Nodes (24): App, count_tokens(), Exact token count via tiktoken if available; else ~4 chars/token., reduction_percent(), build_graph(), install_selected_integrations(), Build the graph and return a small status dict., save_config() (+16 more)

### Community 16 - "._copilot_monitor"
Cohesion: 0.06
Nodes (63): claude_exchanges(), _claude_text_content(), copilot_exchanges(), trim_text(), parse_workspace_folders(), Read a VS Code .code-workspace JSONC file and return existing member folders., dedupe_sessions(), initial_meter_sessions() (+55 more)

### Community 17 - "Chat digest — Grafel Live Meter rework (2026-07-08)"
Cohesion: 0.33
Nodes (5): Chat digest — Grafel Live Meter rework (2026-07-08), Still pending / next steps, Verified against real data, What the user reported, What was changed in grafel.py (all compile-verified)

### Community 18 - "App"
Cohesion: 0.22
Nodes (8): 1. Runtime extraction, 2. Deterministic integration harness, 3. Release hardening, Current limitations, Goal, Grafel Product Evolution Plan, Implementation tracks, Near-term next steps

### Community 19 - "Copilot Chat (VS Code) — Copilot·Graftool·10bbef01 (2026-07-08)"
Cohesion: 0.03
Nodes (73): Copilot Chat (VS Code) — Copilot | Graftool | 10bbef01 (2026-07-08), Prompt 1, Prompt 10, Prompt 11, Prompt 12, Prompt 13, Prompt 14, Prompt 15 (+65 more)

### Community 23 - "._session_refresher"
Cohesion: 0.21
Nodes (11): ab_report_lines(), graph_token_stats(), iter_code_files(), prompt_comparison_lines(), question_keywords(), question_match_stats(), Yield readable code-like files under a repo, skipping noisy folders., Return token totals for all code-like files in a repo. (+3 more)

### Community 24 - "Copilot Chat (VS Code) — Copilot·Graftool·cef900b1 (2026-07-08)"
Cohesion: 0.29
Nodes (4): Copilot Chat (VS Code) — Copilot | Graftool | cef900b1 (2026-07-08), Prompt 1, Prompt 2, AI chat digests for this repo

### Community 26 - "run_headless"
Cohesion: 0.09
Nodes (16): merge_json_servers(), Idempotently write or refresh the tool-routing block in an agent rules file., Add missing MCP server entries to a JSON config without clobbering existing ones, write_routing_block(), ensure_gitignore_entry(), install_repo_mcp(), write_repo_routing(), main() (+8 more)

## Knowledge Gaps
- **134 isolated node(s):** `context7`, `npx`, `@modelcontextprotocol/server-filesystem`, `graphify`, `Tool routing (token efficiency)` (+129 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `App` connect `.log` to `.__init__`, `._copilot_monitor`, `run_headless`, `.register_mcp_server`?**
  _High betweenness centrality (0.150) - this node is a cross-community bridge._
- **Why does `GrafelCoreTests` connect `._add_session_tab` to `._copilot_monitor`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `Copilot Chat (VS Code) — Copilot | Graftool | 10bbef01 (2026-07-08)` connect `Copilot Chat (VS Code) — Copilot·Graftool·10bbef01 (2026-07-08)` to `Copilot Chat (VS Code) — Copilot·Graftool·cef900b1 (2026-07-08)`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `graphify_cmd()` (e.g. with `.install_integrations()` and `.pipeline()`) actually correct?**
  _`graphify_cmd()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `run_cmd()` (e.g. with `.install_integrations()` and `build_graph()`) actually correct?**
  _`run_cmd()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `context7`, `npx`, `@modelcontextprotocol/server-filesystem` to the rest of the system?**
  _190 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `.__init__` be split into smaller, more focused modules?**
  _Cohesion score 0.06666666666666667 - nodes in this community are weakly interconnected._