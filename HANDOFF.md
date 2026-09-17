# Grafel — Handoff / Resume Point

_Last updated: 2026-07-09_

This is the **single doc to read when resuming work**. It captures the mission, the
current state, the architecture, everything built so far, how to build/test, and the
open items. For the marketing/product framing see `GRAFEL.md`; for the running task
list see `TODO.md`.

---

## 1. Mission (why this exists)

**Grafel — the memory layer for AI coding.** Heavy users of Copilot / Claude Code /
Codex burn tokens and credits because agents keep **re-reading the codebase** to answer
questions. Grafel maps a repo into a persistent **knowledge graph** (pure AST, zero
tokens to build) and wires it into every AI tool via routing rules, so agents answer
from a ~2k-token graph query instead of grepping/reading dozens of files.

The product goal is a **sellable Windows desktop tool** that: builds the graph, wires
the AI tools, and — crucially — **proves the savings with the user's own real usage
data**, then helps them **realize** those savings (auto-wire, optimizer, live meter).

---

## 2. Current status

- **Version:** `APP_VERSION = "1.0.0"`, primary desktop GUI in `grafel.py` with non-UI logic now increasingly moved into `grafel_core/`.
- **State:** fully working. Compiles clean, Problems tab is clean, builds to a single
  `Grafel.exe` (~46–89 MB) + `GrafelSetup.exe` installer.
- **Stack:** Python 3.12 + Tkinter (alien-tech neon theme). PyInstaller onefile +
  Inno Setup. Backend: FastAPI + SQLite in `server/`. CI in `.github/workflows/build.yml`.
- **Interpreter gotcha:** VS Code keeps reverting to a `.venv` that lacks deps. Pin it to
  `C:\Users\Usman\AppData\Local\Programs\Python\Python312\python.exe` (has fastapi,
  pystray, PIL, tiktoken, graphify). `.vscode/settings.json` sets this + disables
  cSpell/markdownlint noise.

---

## 3. Architecture

**Core helper modules (`grafel_core/`):**
- `savings.py`: token counting, repo/question measurement, savings/A-B display helpers.
- `sessions.py`: Claude/Copilot/Codex session discovery, usage parsing, token aggregation.
- `config.py`: routing block management, workspace JSONC parsing, MCP JSON merge helpers.
- `chat_export.py`: Claude/Copilot chat digest parsing and trimming helpers.
- `workspace.py`: config load/save and `.code-workspace` discovery.
- `graphs.py`: graph wiring status, artifact freshness checks, report loading, graph snapshot diff helpers.
- `optimizer.py`: pure recommendation planning for the savings optimizer.
- `workflows.py`: reusable build/wire helpers for graph build, integration wiring, local MCP files, routing targets, and `.gitignore`.
- `live.py`: watch-line classification plus live meter scope/session selection helpers.
- `release.py`: build/release helpers for version extraction and Inno Setup command generation.
- `watch_runtime.py`: watch process launch/start/exit behavior helpers.
- `meter_runtime.py`: live meter fallback logic, Copilot event accumulation, Claude prompt accounting, and baseline-update helpers.

**Remaining top-level helpers in `grafel.py`:**
- `run_cmd` (streams output, filters `_ENGINE_NOISE` benign warnings),
  `graphify_cmd`, `engine_available`, `find_graphify`, `resource_path`, `tool_installed`.
- Pricing constants and UI-only constants/theme state.

**`App` class (Tkinter):**
- UI: animated header, TARGET row, AI-uplink checkboxes, 2 button rows, a `ttk.Notebook`
  with tabs: **Console / Insights / Q&A / Graph / ◈ SESSIONS**. A persistent service
  badge (`svc_var`) shows `◭ WATCH ●` / `◉ METER ●` so both are visibly live.
- Logging: thread-safe queue (`_logq`) flushed by `_flush_log`; `self.log(text, tag,
  box=...)` routes to `_boxes` **or** `_session_boxes` (per-session tabs).
- Pipeline: `start` → `pipeline` → `graphify update` + `install_integrations` +
  `install_mcp` + `ensure_gitignore`.
- Watch: `toggle_watch` / `_start_watch(path, quiet)` / `_watch_reader` (streams
  rebuild output; start/exit handling now delegates into `grafel_core.watch_runtime`
  and watch-line classification delegates into `grafel_core.live`;
  runs side by side with the meter).
- **Live Meter (tabbed, multi-session):** `toggle_meter` now delegates initial scope
  selection and session discovery into `grafel_core.live`/`grafel_core.meter_runtime`,
  then builds one tab per Claude
  session (`_build_session_tabs` / `_add_session_tab`), spawns a `_session_monitor`
  thread per session (replays the session's cost history, then tails live), and a
  `_session_refresher` that adds tabs for newly opened chats. All monitors stop when
  `meter_on` goes False.
- **Wire status + auto-wire:** `_graph_wired_status` now delegates into `grafel_core.graphs`,
  `_report_wire_status(path, box)`, `_offer_autowire` (offers whole-workspace wiring when
  the repo is in a `.code-workspace`), `_autowire_worker` → `_do_autowire` (pauses WATCH
  during writes, resumes after) → `_autowire_build` (per-project progress + merged
  cross-project graph). `wire_workspace` = manual entry (Repos menu).
- **Realized savings (proven):** the meter records per-repo baseline context-tokens/turn
  while UNWIRED (persisted in `cfg["meter_baselines"]`), then shows the MEASURED drop
  once a wired/leaner session runs, feeding real tokens into the Dashboard.
- **Optimizer:** `run_optimizer` / `_optimize_worker` now consumes usage scanners plus
  `grafel_core.optimizer.build_optimizer_plan(...)` for prioritized $/month savings advice.
- **Usage scan:** `scan_usage` / `_scan_usage_worker` (Claude deduped, Codex
  token_count, Copilot request/turn counts from `~/.copilot/session-store.db`).
- Other: `show_savings`, `run_ab_test`, `run_ask`, `run_benchmark`, `run_batch`,
  `merge_repos`, `graph_diff`, `export_card`, `show_dashboard`, `register_mcp_server`,
  `cloud_upload/_download`, `schedule_rebuild`, `check_updates`, tray, single-instance
  socket lock, `run_headless` (CLI `Grafel.exe <path>`), `main` (self-dispatch
  `--run-graphify` / `--run-mcp`).

**`server/app.py`:** FastAPI + SQLite — `/health`, `/license/issue|validate`,
`PUT|GET /graph/{key}`, `/update/manifest`, `/analytics/*`.

---

## 4. Key domain facts (hard-won, don't re-discover)

- **Claude logs:** `~/.claude/projects/<encoded-cwd>/*.jsonl`. Encoding = every
  non-alphanumeric char → `-`, drive-letter case varies (match case-insensitively).
- **Multi-root workspaces:** Claude Code anchors the session folder to the FIRST
  workspace folder, but each turn records the true `cwd` — always use `session_cwd()` to
  get the real repo.
- **Usage double-counting:** each assistant message logs 2–3 content-block lines with
  the SAME `usage`. **Dedupe by `message.id`** or totals are inflated 2–3x.
- **Cost reality:** per-prompt bills are dominated by **cache-read** (carried context
  re-read every turn, $0.30/M). The "93% savings" is a *per-codebase-question* figure
  (2k graph vs ~30k reading files) and lives in A/B Test / Savings — NOT the live bill.
  The meter honestly shows real billed cost + **recoverable** (estimate, tunable
  `cfg["codebase_context_fraction"]`, default 0.5) and, once wired, **proven** realized
  savings.
- **Copilot** is trackable via `~/.copilot/session-store.db` (`sessions`, `turns`) —
  each turn ≈ 1 premium request (~$0.04 over allowance). VS Code inline chat is NOT
  logged locally.
- **Build output** must go OUTSIDE OneDrive (`%LocalAppData%\GrafelBuild`) to avoid
  file-lock errors. `build.bat` handles this; exit code 1 can be spurious if "DONE:"
  printed.
- **Engine noise:** the `graphify` "skill is from 0.9.3, package 0.9.9" warning and
  zero-node/Gemini-tip lines are benign and filtered by `_is_engine_noise` in `run_cmd`.
- **Artifact freshness:** the GRAPH tab now warns if `graphify-out/graph.json` or
  `GRAPH_REPORT.md` is older than source files in the repo, so stale outputs are surfaced
  instead of quietly shown as current.

---

## 5. Build / run / test

```powershell
# run from source
pythonw grafel.py

# compile + test
.\verify-grafel.ps1

# full build (exe + installer) — kill running instances first
Get-Process pythonw,Grafel,python,graphify -EA SilentlyContinue | Stop-Process -Force
.\build.bat        # verifies first, then -> dist\Grafel.exe + %LocalAppData%\GrafelBuild\GrafelSetup.exe

# backend
cd server; uvicorn app:app --port 8137
```

Automated tests now live under `tests/` and run with the standard library
`unittest` runner via `.\verify-grafel.ps1`. Current coverage includes savings
helpers, session parsing, workspace discovery, routing/MCP config writes, chat
export parsing, graph freshness/diff helpers, optimizer planning, workflow
wiring helpers, live watch/session helper behavior, watch-runtime and meter-runtime
helper behavior, release helper behavior, a real temp-repo runtime smoke flow, and
backend runtime config validation.

---

## 6. Open items / next steps

- **See `KNOWN_ISSUES.md`** for a full audit (2026-07-11) of correctness/robustness bugs
  found across the meter's cost math, log tailing, config persistence, strict-mode MCP
  wiring, and the server backend — including that the `--proof-command`/`--proof-query`
  CLI dispatch used by `grafel-*.cmd` is still broken for real (piped) usage despite an
  attempted fix. Read it before touching the Live Meter, savings/A-B reporting, or
  `strict_mcp.py`.
- **Refactor next:** `grafel.py` is still the main maintenance hotspot, but the first
  major split is now done: savings, sessions, routing/config, workspace discovery,
  graph freshness/diff logic, optimizer planning, workflow wiring, live meter/watch
  decisions, runtime accounting helpers, and chat export parsing live in `grafel_core/`.
  The next refactor should
  focus on moving more workflow orchestration out of `App` if future feature work makes
  that worthwhile.
- **Deferred (user said "at the end"):** licensing + landing page, deploy the backend
  (user hosts), push a `v1.0.0` tag to trigger CI, register domain, light theme,
  interactive in-app graph viewer (needs embedded webview).
- **Watch vs auto-wire:** handled (auto-wire pauses/resumes WATCH), but if a workspace is
  huge, per-project graph builds are sequential and can take a while (progress is shown).

---

## 7. How to resume

1. Open the workspace; ensure the interpreter is **Python312** (not `.venv`).
2. `.\verify-grafel.ps1` - should compile `grafel.py`, `grafel_core/*.py`, and `server/app.py`, then run
   the `tests/` suite including the real temp-repo smoke flow.
3. Read this file + `TODO.md` (checklist) for what's done/pending.
4. Make changes, run `.\verify-grafel.ps1`, then `.\build.bat`, then `pythonw grafel.py`
   to smoke test.
5. Commit at each working state.
