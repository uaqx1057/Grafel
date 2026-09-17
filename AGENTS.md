## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Tool routing (token efficiency)
- Codebase questions (architecture, "what calls X", impact analysis): run `graphify query "<question>"` FIRST. Do NOT grep or read files across the repo - the knowledge graph at graphify-out/graph.json already has the answer for ~2k tokens.
- Library/framework documentation (Flutter, Laravel, Django, Node, etc.): use the Context7 MCP server (resolve-library-id + query-docs) instead of guessing APIs from memory.
- File access: after a graphify query identifies the relevant files, read ONLY those specific files. Avoid directory-wide listing/exploration.
- Answer reuse: before querying, check graphify-out/memory/ for a saved answer to the same question. After answering a non-trivial question well, save it with `graphify save-result --question "<question>"`.
- Quiet output: run tests/builds with filtered or quiet flags (e.g. `--compact`, `2>&1 | tail -20`). Never dump full verbose logs into the conversation - quote only the failing lines.
- Checkpoints: after each working state, make a git commit. If a change breaks things, revert to the last commit instead of debugging your own regressions from scratch.
- Self-updating docs: when you discover a non-obvious fact about this codebase (convention, gotcha, build quirk), append it to this file so future sessions never re-discover it.
<!-- graphify-tool:routing:end -->

<!-- graphify-tool:routing:start -->
## Tool routing (token efficiency)
Strict mode: Required + Violation Alerts
Policy: Grafel helper commands are mandatory and bypasses should be treated as policy violations.
- For any codebase question, you MUST first run `graphify-out\grafel-query.cmd "<question>"`.
- If MCP is available, use the `grafel-strict` tools (`grafel.query`, then `grafel.read_file`) instead of direct filesystem tools.
- Only after that may you inspect files returned by the graph result.
- Do NOT perform repo-wide grep, recursive listing, or broad file reads first.
- If the graph is stale or missing, run `INITIATE SCAN` or `WATCH` first.
- Treat any bypass of this flow as a Grafel policy violation and surface it clearly.
- Use sibling helpers where relevant: `graphify-out\grafel-path.cmd`, `graphify-out\grafel-explain.cmd`, and `graphify-out\grafel-save-result.cmd`.
- Library/framework documentation (Flutter, Laravel, Django, Node, etc.): use the Context7 MCP server (resolve-library-id + query-docs) instead of guessing APIs from memory.
- Answer reuse: before querying, check graphify-out/memory/ for a saved answer to the same question. After answering a non-trivial question well, save it with `graphify-out\grafel-save-result.cmd "<question>"`.
- Quiet output: run tests/builds with filtered or quiet flags (e.g. `--compact`, `2>&1 | tail -20`). Never dump full verbose logs into the conversation - quote only the failing lines.
- Cost discipline: prefer minimal diffs/patches over full-file rewrites; batch related edits and questions into ONE request instead of many small ones; use the cheapest capable model for routine work and reserve premium / high-reasoning models for genuinely hard problems; prefer `/compact` over `/clear` to keep the prompt cache warm.
- Checkpoints: after each working state, make a git commit. If a change breaks things, revert to the last commit instead of debugging your own regressions from scratch.
- Self-updating docs: when you discover a non-obvious fact about this codebase (convention, gotcha, build quirk), append it to this file so future sessions never re-discover it.
<!-- graphify-tool:routing:end -->
<!-- grafel-brevity:start -->
## Grafel Brevity Mode (Ultra)
- Purpose: reduce output-token waste while preserving technical substance.
- Style: Aggressive compression. Fragments first. Keep code exact.
- Drop filler, pleasantries, and hedging.
- Use short, direct engineering language. Fragments OK when clarity stays high.
- Keep code, commands, paths, URLs, env vars, errors, versions, commit text, and irreversible warnings exact.
- When user seems confused, safety risk high, or action irreversible: temporarily answer in normal clear prose.
- Prefer pattern: [thing] [action] [reason]. [next step].
<!-- grafel-brevity:end -->
