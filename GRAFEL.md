# Grafel — Product Document

> **Grafel — the memory layer for AI coding.**
> Map your codebase once. Every AI tool reads the graph instead of re-reading the repo — cutting token/credit usage dramatically.

---

## 1. What Grafel is

Grafel is a Windows desktop application that turns any local folder or public GitHub
repository into a **persistent knowledge graph** of the codebase, then automatically
wires that graph into the developer's AI tools (GitHub Copilot, Claude Code, Codex,
Cursor, Gemini CLI).

Once wired, when a developer asks an AI agent *"how does X work?"* or *"what calls Y?"*,
the agent answers from the ~2k-token graph query instead of grepping and reading dozens
of files (50k+ tokens). The result is a large reduction in AI token/credit consumption
for teams doing heavy "vibe coding."

**The graph is built with pure AST (static analysis) extraction — zero LLM calls, zero
tokens to build.** That is the core cost advantage.

---

## 2. The problem it solves

Heavy users of Copilot / Claude Code / Codex constantly hit usage limits. The #1 hidden
cost is **agents repeatedly re-reading the codebase** to answer questions. Every session,
the same files get grepped and read again, burning tokens/credits.

Grafel attacks the root cause: it builds a reusable, queryable map of the code and makes
every AI tool consult that map first.

**Typical savings:** for codebase-navigation questions, ~2k tokens (graph query) vs.
50k+ tokens (full-file exploration) — often a 50–80% reduction in total usage for
teams whose agents spend most tokens reading code.

---

## 3. How it works (pipeline)

1. **Input** — the user picks a local folder or pastes a GitHub URL.
   - GitHub URL → cloned locally first (via `graphify clone`, fallback `git clone`).
2. **Build graph** — runs the AST engine (`graphify update <path>`), producing
   `graphify-out/graph.json` + `graph.html` + `GRAPH_REPORT.md` inside the project.
   No LLM, no API key, no tokens.
3. **Wire AI tools** — runs per-tool installers so each agent queries the graph:
   - VS Code Copilot → `.github/copilot-instructions.md` + skill
   - Claude Code → `CLAUDE.md` + PreToolUse hook
   - Codex → `AGENTS.md`
   - Cursor, Gemini CLI (optional)
4. **Configure MCP servers** — writes per-repo MCP config so agents also get:
   - **Context7** (remote HTTP) for up-to-date library/framework docs
   - **Filesystem** (npx, repo-scoped) for targeted file reads
   - Files: `.vscode/mcp.json` (Copilot), `.mcp.json` (Claude Code), `~/.codex/config.toml` (Codex)
5. **Tool-routing rules** — appends a marked "Tool routing" block to
   `CLAUDE.md` / `AGENTS.md` / `copilot-instructions.md` telling agents:
   graph first → Context7 for library docs → read only the identified files.
6. **Keep fresh** — optional git hooks (rebuild graph on commit) and a **Watch** mode
   (rebuild on save). Both are token-free (AST only).
7. **View** — auto-opens `graph.html` in the browser; buttons re-open the graph or the
   repo in VS Code.

All idempotent: existing configs are merged, never clobbered; routing blocks update in
place on re-run.

---

## 3a. Savings Report (proof of value)

> "With the naked eye, developers can't see the difference in tokens/credits. Grafel
> shows a real, measurable comparison so they trust it."

The **SAVINGS** button produces an honest, reproducible token comparison after a scan.
Trust is the whole point, so every number is measured or transparently assumed:

**What it measures (real, no magic):**
- **Full-context cost** = actual token count of every code file in the repo (what
  "read the whole codebase" would cost an agent). Files walked, binaries/huge files
  skipped, `graphify-out/`, `node_modules`, `.git`, build dirs excluded.
- **Grafel index cost** = actual token count of `graphify-out/graph.json` (the
  compressed map the agent reads instead) + the **compression ratio** (e.g. "13.9x
  smaller").
- **Per-question cost** = the graph query budget (~2,000 tokens, capped).
- **Token counting** = exact via `tiktoken` (`cl100k_base`) when installed, else the
  standard ~4-chars/token estimate. **The method is printed on screen** so the number
  is never mistaken for something it isn't.
- **Dollar figures** = **real cost = tokens × published per-1M input price.** Because model
  pricing is public, the token counts convert directly into money. Default input prices
  (edit any/all in `~/.grafel.json` → `"prices"`): Claude Sonnet $3.00/M, Claude Opus
  $15.00/M, GPT-4o $2.50/M, Gemini 2.5 Pro $1.25/M. **Users can set the exact price they
  pay** — the proof then uses *their* numbers, which is what makes it trustworthy.
- **Per-100-questions illustration** = uses a clearly-labeled conservative assumption
  (~30k tokens/question exploring files vs ~2k via the graph) with the assumption
  displayed so users can plug their own workload. No hidden fudge factors.

**Why this earns trust:** the two anchor numbers (repo tokens, graph tokens) are
directly measured on the user's own code and fully reproducible; the cost math is shown
with its assumptions; nothing is fabricated.

**Roadmap for this feature:** a live A/B — run the *same* question through the agent
with and without the graph and show the actual token counts side by side; a cumulative
"tokens saved this week" counter; export a shareable savings card (great for marketing).

---

## 4. Architecture

| Layer | Detail |
|---|---|
| **UI** | Python + Tkinter, single file `grafel.py`. Custom "alien-tech" neon theme, canvas-drawn buttons, grouped action rows for a denser feature set, animated (opt-in) neural-graph header, batched thread-safe console. |
| **Engine** | The `graphify`/`graphifyy` AST package. Bundled inside the exe via PyInstaller `--collect-all graphify` + self-dispatch (`Grafel.exe --run-graphify …`). No Python/pip needed on end-user machines. |
| **Brevity layer** | Caveman-style brevity behavior is built into Grafel itself through native rule writers, memory compression helpers, and output-savings tracking. It is installed locally by Grafel and is not fetched from GitHub during normal end-user use. |
| **MCP** | Context7 (remote HTTP, no install) + `@modelcontextprotocol/server-filesystem` (via npx, needs Node.js — degrades gracefully with a warning). |
| **Packaging** | PyInstaller one-file `Grafel.exe` (~44 MB, engine inside) → Inno Setup `GrafelSetup.exe` (admin install, Program Files, PATH, desktop/Start-menu icons, uninstaller). |

**Output location rule:** the graph always lives at `<project>/graphify-out/`. AI tools
resolve it relative to their working directory (the repo root), so placement is
zero-config. `graphify-out/` is auto-added to `.gitignore`.

### Key files in this repo
- `grafel.py` — the application
- `assets/make_icon.py` — generates `grafel.ico` / `grafel.png` (neon graph "G" logo)
- `build.bat` — one-command build: icon → exe → installer
- `installer.iss` — Inno Setup script (one-click installer)
- `Grafel.bat` — dev launcher (runs `pythonw grafel.py`)
- `dist/Grafel.exe` — portable single-file build
- `installer/GrafelSetup.exe` — the distributable installer

---

## 5. Installation & requirements

**End users (via `GrafelSetup.exe`):** nothing else required — Python, the Graphify engine,
and Grafel's native brevity/Caveman-style helpers are bundled with the app experience.
Optional:
- **git** — only for the GitHub-clone feature and git hooks
- **Node.js** — only for the Filesystem MCP server (Context7 works without it)
- The AI tools themselves (VS Code+Copilot, Claude Code, Codex) — Grafel writes their
  config regardless; it activates when the tool is present.

**Developers (running source):** `pip install graphifyy pyinstaller pillow`, then
`python grafel.py` or double-click `Grafel.bat`.

---

## 6. Build & release

```
build.bat        # icon -> dist\Grafel.exe -> installer\GrafelSetup.exe
```

Requires Python 3 on PATH and Inno Setup 6 (`winget install JRSoftware.InnoSetup`).
Rebuild after any code change with the same one command.
The build also runs `validate-package.ps1`, which verifies that the packaged
`Grafel.exe` can serve the `grafel-strict` MCP tools.

---

## 6.1. How to Know Grafel Is Saving Tokens

Open **Dashboard** and check the compact health row:

```
Strict MCP: ON | Graph: Fresh | Linked: 2 | Graph-used: 1 | Bypassed: 0
```

- **Strict MCP: ON** means Grafel installed the controlled MCP gateway.
- **Graph: Fresh** means the current graph is not older than the repo source files.
- **Linked** means local AI sessions are hard-linked to this repo/workspace.
- **Graph-used** means Grafel found session evidence or mapped repo proof events from
  `grafel-strict`, `ASK GRAPH`, `A/B TEST`, or `grafel-query.cmd`.
- **Bypassed** means a linked session appears to have used broad raw file exploration
  without graph-first proof.

For strongest enforcement, launch tools through Grafel's strict profiles or configure
the AI tool to use the repo's `grafel-strict` MCP server. The strict gateway exposes
`grafel.query`, `grafel.path`, `grafel.explain`, `grafel.allowed_files`,
`grafel.search_allowed`, `grafel.file_summary`, `grafel.read_file`, and
`grafel.save_result`. `grafel.read_file` is blocked until the graph has returned
that file.

---

## 7. Branding

- **Name:** Grafel — *graf* (graph) + a clean suffix. Short, one obvious spelling,
  instantly sayable (word-of-mouth friendly), no product collisions in the dev-tools space.
- **Tagline:** *"The memory layer for AI coding."*
- **Alt taglines:**
  - *"Your codebase, mapped once. Every AI tool reads it cheap."*
  - *"Cut your AI token bill — Grafel graphs your repo so Copilot, Claude & Codex stop re-reading it."*
- **Logo:** neon node-graph forming a "G" on a dark rounded tile (cyan / magenta / green).
  `assets/grafel.ico` (16–256px) — shows in taskbar, Task Manager, desktop, Start menu,
  window title, installer.
- **Palette:** void black-blue `#050810`, cyan `#00f0ff`, magenta `#ff2fd6`, green `#39ff88`.

---

## 8. Domains

`.com` for short words is saturated; `.ai` is on-brand but **expensive** (typically
$60–150+/yr). Verified options (RDAP registry checks, 2026-07-07):

| Domain | Status | Note |
|---|---|---|
| `grafel.ai` | ✅ available | premium AI TLD, higher annual cost |
| `getgrafel.com` | ✅ likely available | ~$10/yr, common SaaS pattern |
| `usegrafel.com` | ✅ likely available | ~$10/yr |
| `trygrafel.com` | ✅ likely available | ~$10/yr |
| `grafel.com` | ❌ held since 1998 (unrelated party) | not a software product |

**Recommendation:** register a cheap `.com` (e.g. **getgrafel.com** or **usegrafel.com**)
as the primary marketing site to keep costs low; optionally grab `grafel.ai` later for
brand defense once there's revenue. Re-verify at checkout — availability can change.

> ⚠️ Before taking payment, run a 2-minute trademark search (USPTO / EUIPO) on "Grafel".
> The domain is clear; trademark is the last box to tick.

---

## 9. Positioning & go-to-market

- **Audience:** individual developers and small teams who heavily use AI coding agents
  and repeatedly hit token/credit limits (the exact pain of "high-workload vibe coding").
- **Wedge:** "cut your AI bill" — a measurable, money-saving value prop, not a vitamin.
- **Distribution:** free desktop app (installer) → viral word-of-mouth among AI-tool
  power users; content marketing around "reduce Copilot/Claude token usage."
- **Channels:** Product Hunt, dev Twitter/X, r/ChatGPTCoding & r/vscode, YouTube dev-tool
  reviewers, Hacker News "Show HN".

### Possible monetization (future)
- **Free:** local single-repo use (current app).
- **Pro (subscription):** multi-repo dashboards, team-shared graphs, cross-repo merged
  graph, cloud sync of `graphify-out`, private hosted graph endpoint, analytics on
  tokens saved, priority MCP endpoints.
- **Team/Enterprise:** SSO, on-prem/self-hosted graph server, audit, seat licensing.

---

## 10. Roadmap ideas

- One-click "graph all repos in a folder" (batch).
- Token-savings dashboard (estimate credits saved per repo/week).
- Shareable "savings card" export (marketing / social proof).
- macOS + Linux builds.
- In-app graph viewer (no browser needed).
- Scheduled auto-rebuild (Windows Task Scheduler integration).
- Team mode: push/pull a shared graph so a whole team's agents reuse one map.
- Marketplace of routing profiles per stack (Flutter, Laravel, Django, Node).

---

## 11. Current status

- ✅ Working desktop app (`grafel.py`) — build, wire AI tools, MCP, routing, watch, view.
- ✅ Alien-tech neon UI, custom logo/icon.
- ✅ Bundled engine (no Python needed for end users) — verified running inside the exe.
- ✅ One-click installer (`GrafelSetup.exe`) — admin, PATH, desktop/Start-menu icons.
- ✅ Rebranded from working prototype to **Grafel**.
- ✅ **Savings Report** — honest, measured token/cost comparison (full codebase vs graph index).
- ✅ **Live A/B test** — ask a real question; compares actual grep+read tokens vs the real graph-query tokens, with per-model cost.
- ✅ **Tabbed output** (Console / Insights / Q&A) so results are readable, not one terminal blob.
- ✅ **Per-prompt cost readout** — every ASK shows tokens & $ with vs without Grafel, plus the answer.
- ✅ **Ask / Batch / Dashboard / Card** — GUI query, multi-repo graphing, persistent savings totals, shareable PNG proof.
- ✅ **Real Usage Scanner** — reads local Claude Code logs (token counts only, never chat content, never uploaded) to show ACTUAL tokens consumed and real spend per project. Verified: parses real per-message `usage` (input/output/cache).
- ⏳ Next: register domain, trademark check, publish landing page, first release.

---

*Document generated for the Grafel project. Update as features land.*
