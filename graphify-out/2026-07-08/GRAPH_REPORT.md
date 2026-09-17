# Graph Report - Graftool  (2026-07-08)

## Corpus Check
- 16 files · ~27,097 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 274 nodes · 509 edges · 19 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- .configure
- Community 1
- Community 2
- App
- .log
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
- .toggle_meter
- Chat digest — Grafel Live Meter rework (2026-07-08)
- ._copilot_monitor

## God Nodes (most connected - your core abstractions)
1. `App` - 89 edges
2. `graphify_cmd()` - 13 edges
3. `Grafel — Product Document` - 13 edges
4. `run_cmd()` - 12 edges
5. `Grafel — Master TODO / Suggestions Checklist` - 10 edges
6. `NeonButton` - 9 edges
7. `db()` - 9 edges
8. `run_headless()` - 8 edges
9. `Grafel — Handoff / Resume Point` - 8 edges
10. `find_workspace_for()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `graphify_cmd()` --calls--> `find_graphify()`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 2 → community 15_
- `list_vscode_copilot_sessions()` --calls--> `vscode_chat_dirs_for()`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 2 → community 16_
- `find_workspace_for()` --calls--> `parse_workspace_folders()`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 2 → community 11_
- `run_headless()` --calls--> `merge_json_servers()`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 4 → community 2_
- `main()` --calls--> `App`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 3 → community 2_

## Import Cycles
- None detected.

## Communities (19 total, 0 thin omitted)

### Community 0 - ".configure"
Cohesion: 0.36
Nodes (3): NeonButton, Modal picker: list Claude sessions (name + open/closed) and return the, Angular cyber-style button with hover glow and disabled state.

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (11): 1. Core tool (build → graph → wire AI), 2. AI tool integrations (query the graph, not the repo), 3. MCP + tool routing, 4. Proof & trust (the sales engine), 5. Core power features, 6. Packaging & branding, 7. Business / go-to-market, 8. Token-saving strategies (advice — apply as habits) (+3 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (31): active_claude_session(), _claude_dir_newest_mtime(), engine_available(), find_graphify(), fmt_tokens(), _human_ago(), _is_engine_noise(), load_config() (+23 more)

### Community 3 - "App"
Cohesion: 0.06
Nodes (15): App, Show a folder picker (blocking); return a path or ''. Uses the modern         W, Modern Windows folder picker (IFileOpenDialog) in a subprocess - fully, Launch a second independent Grafel window (own process, no instance         loc, Let the user pick a .code-workspace file and wire every interlinked         pro, Measure real token savings: full codebase context vs Grafel's graph         ind, Ask a real codebase question and compare, in actual tokens, what an agent, Ask a question; show the graph answer AND the real per-prompt cost         (tok (+7 more)

### Community 4 - ".log"
Cohesion: 0.22
Nodes (5): merge_json_servers(), Configure Context7 + Filesystem MCP servers per repo and append         tool-ro, Resolve how to launch graphify's MCP server for this graph., Register the repo's graph as an MCP server so agents query it natively., Add missing MCP server entries to a JSON config without clobbering existing ones

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
Cohesion: 0.13
Nodes (10): find_workspace_for(), Replay a session's cost history into its tab, then tail it live. Runs per, Return (has_graph, has_routing) for a repo: whether the graph is built, Tell the user, in the meter, whether the live repo is actually wired —, Report wire status for every project in a multi-root workspace, and offer, Deduped Claude Code usage (by assistant message id) with a per-model         sp, Return (total_cost, {class: cost}) using per-model published rates., Return the most recent real working directory recorded in a Claude session (+2 more)

### Community 12 - "_feat_test.py"
Cohesion: 0.29
Nodes (11): db(), get_graph(), ingest(), init(), issue(), put_graph(), Grafel backend - license validation, cloud graph sync, auto-update, analytics., require_admin() (+3 more)

### Community 13 - ".browse"
Cohesion: 0.22
Nodes (8): 1. Mission (why this exists), 2. Current status, 3. Architecture (grafel.py map), 4. Key domain facts (hard-won, don't re-discover), 5. Build / run / test, 6. Open items / next steps, 7. How to resume, Grafel — Handoff / Resume Point

### Community 14 - ".run_batch"
Cohesion: 0.29
Nodes (6): Endpoints, Environment, Grafel Backend (starter), Run locally, Run with Docker, Wiring the desktop app

### Community 15 - ".log"
Cohesion: 0.11
Nodes (15): count_tokens(), graphify_cmd(), Thread-safe: queue the line for a specific tab; a single UI timer         flush, Wire every selected AI tool to the graph. Tools graphify supports use its, Keep the graph local: in the project for AI tools, out of git., Start the file-watcher on a repo. Safe to call from any thread; the         wat, Pump watcher stdout into the console and flag if it dies immediately., Resolve how to invoke the graphify engine, in preference order:     system CLI (+7 more)

### Community 16 - ".toggle_meter"
Cohesion: 0.12
Nodes (14): claude_log_dir(), friendly_project_name(), list_claude_sessions(), list_vscode_copilot_sessions(), Open a live tab per AI session (Claude Code + VS Code Copilot Chat) for, True if a session belongs to the meter's current repo/workspace scope., (Re)build the SESSIONS sub-notebook: one tab per Claude session., While the meter runs, add a tab + monitor for any newly opened session (+6 more)

### Community 17 - "Chat digest — Grafel Live Meter rework (2026-07-08)"
Cohesion: 0.33
Nodes (5): Chat digest — Grafel Live Meter rework (2026-07-08), Still pending / next steps, Verified against real data, What the user reported, What was changed in grafel.py (all compile-verified)

### Community 18 - "._copilot_monitor"
Cohesion: 0.50
Nodes (3): iter_vscode_chat_events(), Replay + live-tail a VS Code Copilot Chat session into its tab —         reques, Parse a VS Code chatSessions .jsonl from byte `pos`. Returns (events,     new_p

## Knowledge Gaps
- **49 isolated node(s):** `context7`, `npx`, `@modelcontextprotocol/server-filesystem`, `graphify`, `Tool routing (token efficiency)` (+44 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `App` connect `App` to `.configure`, `Community 2`, `.log`, `.log`, `.log`, `.toggle_meter`, `._copilot_monitor`?**
  _High betweenness centrality (0.307) - this node is a cross-community bridge._
- **Why does `NeonButton` connect `.configure` to `Community 2`, `.log`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Why does `graphify_cmd()` connect `.log` to `Community 2`?**
  _High betweenness centrality (0.010) - this node is a cross-community bridge._
- **What connects `context7`, `npx`, `@modelcontextprotocol/server-filesystem` to the rest of the system?**
  _115 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.06612685560053981 - nodes in this community are weakly interconnected._
- **Should `App` be split into smaller, more focused modules?**
  _Cohesion score 0.06280193236714976 - nodes in this community are weakly interconnected._
- **Should `App` be split into smaller, more focused modules?**
  _Cohesion score 0.125 - nodes in this community are weakly interconnected._