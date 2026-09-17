# Graph Report - Graftool  (2026-07-07)

## Corpus Check
- 11 files · ~14,300 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 151 nodes · 276 edges · 11 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 1
- Community 2
- .log
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- App
- .log
- .log

## God Nodes (most connected - your core abstractions)
1. `App` - 55 edges
2. `Grafel — Product Document` - 13 edges
3. `graphify_cmd()` - 12 edges
4. `run_cmd()` - 10 edges
5. `Grafel — Master TODO / Suggestions Checklist` - 10 edges
6. `NeonButton` - 8 edges
7. `run_headless()` - 8 edges
8. `count_tokens()` - 6 edges
9. `write_routing_block()` - 6 edges
10. `merge_json_servers()` - 6 edges

## Surprising Connections (you probably didn't know these)
- `graphify_cmd()` --calls--> `find_graphify()`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 2 → community 11_
- `run_headless()` --calls--> `graphify_cmd()`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 11 → community 15_
- `main()` --calls--> `App`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 4 → community 2_
- `main()` --calls--> `run_headless()`  [EXTRACTED]
  grafel.py → grafel.py  _Bridges community 15 → community 2_

## Import Cycles
- None detected.

## Communities (11 total, 0 thin omitted)

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (11): 1. Core tool (build → graph → wire AI), 2. AI tool integrations (query the graph, not the repo), 3. MCP + tool routing, 4. Proof & trust (the sales engine), 5. Core power features, 6. Packaging & branding, 7. Business / go-to-market, 8. Token-saving strategies (advice — apply as habits) (+3 more)

### Community 2 - "Community 2"
Cohesion: 0.15
Nodes (11): engine_available(), find_graphify(), load_config(), main(), NeonButton, Grafel - the memory layer for AI coding.  A minimal desktop app that maps any, Render a shareable PNG savings card from the last measurement., Locate bundled assets both in dev and in a PyInstaller onefile exe. (+3 more)

### Community 4 - ".log"
Cohesion: 0.10
Nodes (8): App, Measure real token savings: full codebase context vs Grafel's graph         ind, Ask a real codebase question and compare, in actual tokens, what an agent, Ask a question; show the graph answer AND the real per-prompt cost         (tok, Graph every git repo directly under a chosen parent folder., Scan REAL local AI-tool usage logs (token counts only) and report actual, Merge the graphs of every repo under a chosen folder into one graph., Modern Windows folder picker (IFileOpenDialog) in a subprocess - fully

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
Cohesion: 0.16
Nodes (10): count_tokens(), graphify_cmd(), Return (with_tokens, without_tokens, matched) for one question., Load GRAPH_REPORT.md into the in-app GRAPH tab (no browser needed)., Resolve how to invoke the graphify engine, in preference order:     system CLI, Run a command, stream output lines to log(). Returns (exit_code, full_output)., Exact token count via tiktoken if available; else the standard ~4-chars     per, Wire every selected AI tool to the graph. Tools graphify supports use its (+2 more)

### Community 15 - ".log"
Cohesion: 0.11
Nodes (14): merge_json_servers(), Keep the graph local: in the project for AI tools, out of git., Configure Context7 + Filesystem MCP servers per repo and append         tool-ro, Cumulative, persisted proof: total tokens Grafel has kept out of context, Idempotently write/refresh the tool-routing block in an agent rules file., Register a daily Windows scheduled task to rebuild this repo's graph., Resolve how to launch graphify's MCP server for this graph., Register the repo's graph as an MCP server so agents query it natively. (+6 more)

## Knowledge Gaps
- **33 isolated node(s):** `context7`, `npx`, `@modelcontextprotocol/server-filesystem`, `graphify`, `Tool routing (token efficiency)` (+28 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `App` connect `.log` to `Community 2`, `.log`, `.log`?**
  _High betweenness centrality (0.288) - this node is a cross-community bridge._
- **Why does `NeonButton` connect `Community 2` to `.log`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Why does `graphify_cmd()` connect `.log` to `Community 2`, `.log`?**
  _High betweenness centrality (0.016) - this node is a cross-community bridge._
- **What connects `context7`, `npx`, `@modelcontextprotocol/server-filesystem` to the rest of the system?**
  _62 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.14736842105263157 - nodes in this community are weakly interconnected._
- **Should `.log` be split into smaller, more focused modules?**
  _Cohesion score 0.09885057471264368 - nodes in this community are weakly interconnected._
- **Should `App` be split into smaller, more focused modules?**
  _Cohesion score 0.125 - nodes in this community are weakly interconnected._