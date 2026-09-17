# Grafel — Master TODO / Suggestions Checklist

Status legend: ✅ done · 🟡 partial · ⬜ not started · ☁️ needs backend/other-OS (can't build locally) · 👤 your action

_Last updated: 2026-07-07_

---

## 1. Core tool (build → graph → wire AI)
- ✅ Minimal desktop GUI
- ✅ Open a local project folder and run graphify on it
- ✅ Paste a GitHub URL → clone → then graph
- ✅ Auto-open the graph (`graph.html`) in the browser
- ✅ "Open in VS Code" button
- ✅ Recent-projects dropdown + persisted settings (`~/.grafel.json`)
- ✅ Modern Windows folder picker (IFileOpenDialog)
- ✅ Single-instance lock; crash log; OneDrive warning

## 2. AI tool integrations (query the graph, not the repo)
- ✅ VS Code Copilot installer
- ✅ Claude Code installer (+ PreToolUse hook)
- ✅ Codex installer
- ✅ Cursor installer
- ✅ Gemini CLI installer
- ✅ Aider integration
- ✅ Auto-detect which AI tools are installed (pre-tick)
- ✅ Git hooks (auto-update graph on commit)
- ✅ Watch mode (rebuild on save) — now **streams live feedback** to the console ('[watch] Rebuilt: N nodes' on each save) and flags if the watcher dies immediately
- ✅ Add `graphify-out/` to `.gitignore`
- ✅ More tools: Windsurf, Cline, Continue (rule files). JetBrains AI omitted — no standard project-rules mechanism.

## 3. MCP + tool routing
- ✅ Context7 MCP (VS Code, Claude Code, Codex)
- ✅ Filesystem MCP (repo-scoped, via npx)
- ✅ Tool-routing rules written to CLAUDE.md / AGENTS.md / copilot-instructions.md
- ✅ Routing block includes: graph-first, Context7 for docs, quiet output, save-result reuse, commit checkpoints, self-updating docs
- ✅ MCP query-server (Integrations → Register MCP query-server; serves graph over stdio, bundled in exe)

## 4. Proof & trust (the sales engine)
- ✅ Savings Report (real: full codebase tokens vs graph index, compression ratio)
- ✅ Real cost = tokens × published model price; user-editable prices
- ✅ Live A/B test (grep+read baseline vs real graph query)
- ✅ Per-prompt cost readout in ASK (tokens & $ with vs without)
- ✅ **Live Meter** — tails the running Claude Code session for the open repo and reports each completed prompt's REAL billed cost (deduped by message id; input/cache-read/cache-write/output priced). Honestly attributes the cost driver (cache-read of carried context, re-paid every turn) and shows the *recoverable* share if the graph keeps the codebase out of context (tunable `codebase_context_fraction`, shown as a % of the real bill — no inflated/fixed savings claim, does not feed the proven-savings dashboard)
- ✅ **Wire-status + auto-wire** — the Live Meter reads the session's real `cwd` from the log and reports whether the graph is actually WIRED (built + routing) for that repo; if not, it flags "⚠ NOT WIRED — full un-optimized cost" and offers to build+wire it on the spot so the user actually saves
- ✅ **Realized before/after (proven savings)** — the meter records the typical context-tokens/turn while a repo is UNWIRED (persisted per-repo in `meter_baselines`), then once a wired/leaner session runs it shows the MEASURED drop ("✓ REALIZED SAVING: ~X now vs ~Y baseline → $Z actually saved, proven not an estimate") and feeds those real tokens into the proven-savings Dashboard
- ✅ **Multi-root workspace support** — detects the `.code-workspace` a repo belongs to and can wire the ENTIRE workspace (build every interlinked project's graph + routing + one merged cross-project graph). Menu: Repos → "Wire a VS Code workspace (multi-root)…"; also offered automatically when the live session is inside a workspace
- ✅ **Session picker** — if no session matches the exact target repo, the Live Meter shows a themed list of ALL Claude sessions with name + status (◉ open / ○ idle / · closed) + "time ago" so the user picks which to monitor (no more misleading "no session found" when idle >30 min)
- ✅ **Tabbed multi-session Live Meter** — a ◈ SESSIONS tab with one sub-tab per Claude session; each replays its cost history then tails live, and new chats auto-add a tab (`_session_monitor` per session, `_session_refresher`). Click any tab to see that session's live cost — no re-picking. Supersedes the single-session picker.
- ✅ **Scoped sessions (precise)** — the Live Meter now shows ONLY sessions for the currently-opened repo, and its workspace folders if it belongs to a `.code-workspace` (via `_session_in_scope` matching session dir + real `cwd` with `session_cwd_fast`). No more unrelated projects (DrAisha, etc.) in the list. Offers "show all" if nothing matches.
- ✅ **WATCH resume confirmation** — after auto-wire pauses/resumes WATCH, it now logs "✓ WATCH resumed — watching <repo>; graph auto-rebuilds on save" so the user knows it's live again.
- ⬜ **Watch the whole workspace** — when WATCH is turned on for a repo that's part of a `.code-workspace`, offer to watch ALL its folders (multiple watchers), mirroring the auto-wire whole-workspace option.
- ✅ **Problems tab clean** — fixed a real deferred-`lambda` `NameError` in the update checker, PEP8 semicolon/f-string lint, and marked optional imports (`tiktoken`/`pystray`/`PIL`/`graphify`) with `# type: ignore`. Pinned interpreter to Python312 in `.vscode/settings.json`.
- ✅ **WATCH + Live Meter side by side** — both run concurrently with an always-visible service badge (◭ WATCH ● / ◉ METER ●); auto-wire pauses WATCH during file writes and resumes it to avoid rebuild storms
- ✅ **Clean engine output + progress** — benign engine warnings (skill-version, zero-node config files, API-key tips) filtered app-wide in `run_cmd`; auto-wire shows per-project `[i/N]` progress, animated spinner, node counts, and a clear completion banner
- ✅ Persistent Dashboard (cumulative tokens & $ saved)
- ✅ Shareable savings card (PNG export with logo)
- ✅ **Real Usage Scanner** — reads local Claude Code logs (token counts only) → actual spend (now deduped by message id — no content-block double counting)
- ✅ **Optimizer / Savings Advisor** — analyzes real deduped usage (per-model split: Opus/Sonnet/Haiku) and prints a prioritized, data-backed plan to cut credits/tokens with an estimated $/month saving per recommendation (model downgrade, wire-the-graph for context bloat, keep cache warm, ask for diffs, lower Codex reasoning, Copilot premium-request discipline)
- ✅ **Optimizer APPLIES fixes** — each rec is labeled "▶ Grafel CAN APPLY this" (GRAPH/SETUP → build+wire the graph) or "• manual"; applicable fixes are offered for one-click apply (runs auto-wire for the repo/workspace, shows the "✓ WIRED … done" banner). Re-run OPTIMIZE to see the impact.
- ✅ **APPLY ALL (even behavioral recs)** — MODEL/OUTPUT/CACHE/CODEX/COPILOT advice is now encoded as **agent directives** in the routing block (prefer diffs, batch requests, cheapest capable model, `/compact` not `/clear`), installed into CLAUDE.md/AGENTS.md/copilot-instructions.md when wiring. So the optimizer applies the whole plan (graph + directives) in one action, and nothing is left as un-actionable "manual".
- ✅ Codex usage scanning (real `token_count` events).
- ✅ Copilot usage — real **request/turn** counts from `.copilot/session-store.db` + per-month + credit-overage estimate (Copilot bills per request, not tokens).
- ✅ Per-month usage trend (Claude Code tokens by month; Copilot requests by month)
- ✅ Benchmark mode (5 standard questions, aggregate savings)
- ✅ Before/after meter (visual token bar in ASK)

## 5. Core power features
- ✅ Ask-the-graph panel (query from GUI, no terminal)
- ✅ Batch mode (graph every git repo under a folder)
- ✅ Tabbed output (Console / Insights / Q&A)
- ✅ Multi-repo merged graph (Repos → Merge repo graphs)
- ✅ Scheduled auto-rebuild (Repos → Schedule daily rebuild, Task Scheduler)
- ✅ Menu bar (Analyze / Repos / Help / Integrations) + first-run onboarding welcome
- ✅ In-app GRAPH tab (loads GRAPH_REPORT.md — no browser needed)
- ✅ Graph diff (Repos → Graph diff, node-level changes since last snapshot)
- ✅ Guided onboarding tour (Help → Guided tour, 3 steps)
- ⬜ Interactive in-app graph viewer (the live HTML — needs embedded webview dependency)

## 6. Packaging & branding
- ✅ Custom neon "G" logo/icon (all sizes)
- ✅ Alien-tech neon UI (animated header opt-in, neon buttons, holo console)
- ✅ Single-file `Grafel.exe` via PyInstaller (engine bundled inside)
- ✅ Auto-install engine fallback (dev mode)
- ✅ One-click Inno Setup installer (admin, Program Files, PATH, desktop + Start-menu icons, uninstaller)
- ✅ Build outputs outside OneDrive to avoid file locks
- ✅ Rebranded Graphify → **Grafel**
- ✅ System tray + minimize-to-tray (pystray; Show / Toggle watch / Quit)
- ⬜ Light-theme toggle (deferred: neon dark look is the brand; full re-skin is high-churn/low-value)
- ⬜ Onboarding wizard on first run
- ⬜ CLI companion `grafel .` (self-dispatch exists 🟡; dedicated CLI ⬜) → ✅ done: `Grafel.exe <path>` / `grafel .` runs headless (build + wire tools)
- ☁️ Auto-update (needs a release server) → ✅ client + backend manifest built; deploy server to activate
- ☁️ macOS + Linux builds (need those OSes / CI) → ✅ GitHub Actions matrix added; push a tag to produce them

## 7. Business / go-to-market
- 🟡 License / activation (free = 1 repo; Pro = unlimited/team) — **backend scaffolded** in `server/` (FastAPI, verified); deploy + wire client next
- 🟡 Cloud / team shared graph (push-pull) — **backend + client UI built** (Cloud menu: Upload/Download, verified round-trip); needs a deployed server URL
- 🟡 Anonymized "tokens saved across all users" headline metric — **backend `/analytics` ready**; opt-in client post next
- ✅ Auto-update: client **Check for updates** (Help menu) + backend `/update/manifest` (verified). Needs a deployed server URL in config.
- ✅ Multi-OS builds via **GitHub Actions** (`.github/workflows/build.yml`: Windows/macOS/Linux + installer). Cross-platform folder-picker fallback added.
- 👤 Register domain (recommended: **getgrafel.com** cheap; `grafel.ai` available but pricey)
- 👤 Trademark check (USPTO / EUIPO) on "Grafel"
- ⬜ Landing page / marketing site
- ⬜ Launch: Product Hunt, Show HN, dev communities

## 8. Token-saving strategies (advice — apply as habits)
Built into the tool where possible; the rest are workflow habits:
- ✅ Pre-built graph context (core of the tool)
- ✅ Instruction/memory files auto-written
- ✅ Quiet tool output + save-result reuse (in routing rules)
- ✅ `graphify-out/` excluded from git noise
- 👤 Batch instructions into one Copilot message (1 premium request)
- 👤 Use 0×-multiplier models for routine work
- 👤 Short, fresh sessions; `/compact` at natural breaks
- 👤 Spec-first + plan mode before agent mode
- 👤 Commit after each working state (revert instead of re-debugging)
- 👤 Prune enabled MCP servers per project (schema overhead)
- 👤 Avoid image prompts; paste error text instead
- 👤 Local LLMs for boilerplate; lean on inline completions
- 👤 Spread load across Copilot / Claude Code / Codex

## 9. System actions done
- ✅ Disabled OneDrive (quit + removed auto-start; reversible; backup saved)

---

### Suggested next batch (my recommendation)
1. Extend Usage Scanner to **Codex + Copilot** + **per-month trend** (strongest sales proof).
2. **Benchmark mode** + **before/after meter**.
3. **System tray**, **onboarding wizard**, **light theme**.
4. Then business layer (domain 👤, landing page, license/cloud ☁️).
