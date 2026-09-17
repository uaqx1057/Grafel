# Grafel Audit And Test Matrix

Last updated: 2026-07-09

## Findings

| Area | Finding | Improvement | Verification |
|---|---|---|---|
| `grafel.py` structure | Main desktop app is still large, but savings math, session/log parsing, config/routing, workspace discovery, graph/report freshness, optimizer planning, and chat export parsing are now extracted into `grafel_core/` helpers | Keep UI orchestration in `App` and continue moving any new business logic into helper modules first | `powershell -ExecutionPolicy Bypass -File .\verify-grafel.ps1` |
| Workflow orchestration | Repo wiring/build logic was embedded directly inside the Tk app and headless entrypoint | Extracted reusable workflow helpers into `grafel_core/workflows.py` for build, routing, MCP config, `.gitignore`, and integration wiring | `tests/test_grafel_workflows.py` |
| Live UI shell | Watch-output classification and meter session-scope selection were embedded in UI methods | Extracted live watch/session decision helpers into `grafel_core/live.py` so watch and meter behavior are testable without Tk | `tests/test_grafel_product.py` |
| Runtime orchestration | Watch and meter runtime decisions were still spread across long Tk methods | Added `grafel_core/watch_runtime.py` and `grafel_core/meter_runtime.py` for watch start/exit behavior, Copilot event folding, Claude prompt accounting, and meter fallback logic | `tests/test_grafel_runtime.py` |
| Live meter scope UX | Repo-scoped monitoring and machine-wide discovery were blended together, which could flood the session tabs with unrelated AI activity | Added explicit live-meter scope modes (`Repo Only`, `Workspace Only`, `All PC Sessions`), kept scoped tabs as the default working view, and moved out-of-scope sessions into a separate machine-wide summary panel | `tests/test_grafel_product.py`, `tests/test_grafel_runtime.py` |
| Detector evolution | AI-session discovery logic was hard-coded per tool with no common adapter contract for future Windows expansion | Added a shared session-detector catalog and normalized AI session metadata so future Windows detectors can plug into one common listing/scoping pipeline | `tests/test_grafel_core.py` |
| Native brevity mode | Grafel could reduce codebase context waste, but had no native way to reduce verbose agent replies | Added Grafel Brevity Mode with repo instruction blocks, per-agent terse rule installation, selectable levels, and output-side savings tracking | `tests/test_grafel_brevity.py`, `tests/test_grafel_workflows.py` |
| Memory file compression | Repo instruction/memory files could grow noisy and cost extra tokens every session | Added safe local memory-file compression with backups and code-block preservation for repo docs like `CLAUDE.md`, `AGENTS.md`, and `README.md` | `tests/test_grafel_brevity.py` |
| Dead code | Obsolete paths existed for `active_claude_session`, `_pick_session`, and `_meter_worker` | Removed the confirmed obsolete functions from `grafel.py` | `rg -n "def active_claude_session|def _pick_session|def _meter_worker" grafel.py` |
| Backend safety | Starter backend could boot with placeholder production settings | Added production startup validation in `server/app.py` | `tests/test_server_config.py` |
| Artifact freshness | Generated graph/report artifacts could look current even when source files had changed afterward | Added graph/report freshness checks before displaying the in-app report and exposed snapshot diffing through extracted helpers | `tests/test_grafel_core.py` |
| Runtime confidence | Earlier verification only covered compile and unit-level helper behavior | Added a real temp-repo smoke test for build, freshness, local MCP/routing wiring, and rebuild refresh behavior | `tests/test_grafel_smoke.py` |
| Release polish | Build and installer versioning depended on duplicated manual values and ad-hoc packaging steps | Added release helpers, made `build.bat` verify first, build from `Grafel.spec`, clean stale artifacts, and pass `APP_VERSION` into Inno Setup automatically | `build.bat`, `tests/test_grafel_product.py` |
| Release preflight | Packaging inputs and installer dependencies were not checked in one place before build | Added `release_preflight(...)` and wired `build.bat` to run it before verify/build steps | `grafel_core/release.py`, `build.bat` |
| Test coverage | Repo had no dedicated automated tests | Added dependency-free `unittest` coverage for helper modules, workflow wiring logic, runtime smoke, freshness logic, optimizer planning, and backend config | `verify-grafel.ps1` |
| Compile friction | Local compile checks can fail when `__pycache__` writes collide with the repo location | Added `verify-grafel.ps1` with `PYTHONPYCACHEPREFIX` redirected to temp | `.\verify-grafel.ps1` |

## Refactor Status

Completed:

1. Extracted savings math and repo/question token measurement into `grafel_core/savings.py`.
2. Extracted Claude/Copilot/Codex session and usage parsing into `grafel_core/sessions.py`.
3. Extracted config/routing helpers into `grafel_core/config.py`.
4. Extracted chat digest parsing into `grafel_core/chat_export.py`.
5. Extracted workspace discovery and config persistence into `grafel_core/workspace.py`.
6. Extracted graph wiring/freshness/report/diff helpers into `grafel_core/graphs.py`.
7. Extracted optimizer recommendation planning into `grafel_core/optimizer.py`.
8. Extracted workflow/build wiring helpers into `grafel_core/workflows.py`.
9. Extracted live watch/session selection helpers into `grafel_core/live.py`.
10. Extracted release/build metadata helpers into `grafel_core/release.py`.
11. Extracted watch runtime helpers into `grafel_core/watch_runtime.py`.
12. Extracted meter runtime helpers into `grafel_core/meter_runtime.py`.
13. Added a shared deterministic integration harness in `tests/integration_harness.py`.
14. Switched `grafel.py` to use those helpers in savings, A/B, ask, usage scan, live session parsing, watch output handling, meter start/fallback logic, Copilot event folding, Claude prompt accounting, wiring, workspace discovery, graph report loading, snapshot diffing, optimizer planning, chat export paths, and headless build/wire flow.
15. Expanded dependency-free tests around the extracted helpers and added a real temp-repo runtime smoke test.
16. Added live-meter scope controls plus split scoped-vs-machine session presentation in the Tk shell.
17. Added a detector foundation for future Windows AI-session adapters through normalized session metadata and a registry of supported/pending detectors.
18. Added `grafel_core/brevity.py` for native brevity rule generation, safe memory-file compression, and output-savings estimation.
19. Added repo-level brevity installation and per-agent terse rule writing alongside existing routing installs.
20. Added dashboard and usage-scan reporting for brevity-mode output savings plus memory-compression savings.

Next:

1. Keep UI orchestration in `App`, but stop adding new product logic directly there.
2. Add broader smoke coverage for real graph build/wire/export flows when those flows can be exercised deterministically.
3. Harden packaging/release behavior separately from core refactor work.

## Test Inventory

| Test File | Focus |
|---|---|
| `tests/test_grafel_core.py` | formatting helpers, savings helpers, Claude usage parsing, workspace parsing, routing-block idempotency, MCP merge behavior, chat export parsing, graph freshness/diff helpers, optimizer planning |
| `tests/test_grafel_product.py` | live watch/session helper behavior and release/version helper behavior |
| `tests/test_grafel_runtime.py` | watch-runtime and meter-runtime helper behavior |
| `tests/test_grafel_workflows.py` | workflow helper coverage for `.gitignore`, local MCP files, routing targets, and integration/hook wiring behavior |
| `tests/test_grafel_brevity.py` | brevity rule writing, memory compression safety, and output-savings estimation |
| `tests/test_grafel_smoke.py` | real temp-repo smoke flow for graph build, artifact freshness, local wiring, and rebuild refresh |
| `tests/test_server_config.py` | production config safety checks |

## Manual Smoke Checks

| Flow | Status |
|---|---|
| Build graph from local repo | `[ ]` |
| Wire AI integrations | `[ ]` |
| Watch mode | `[ ]` |
| Live meter | `[ ]` |
| Savings report | `[ ]` |
| A/B test | `[ ]` |
| Ask flow | `[ ]` |
| Backend health/update/licensing smoke | `[ ]` |
