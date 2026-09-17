# Grafel — Known Issues (2026-07-11)

Full audit of correctness/robustness bugs found in one session: a manual dig into the
CLI helper commands (`grafel-query.cmd` etc.), followed by a dedicated full-codebase
audit run via a Fable 5 agent. Nothing below is fixed yet except where noted. This is a
punch list, not a design doc — see `HANDOFF.md` for architecture and `TODO.md` for the
product checklist.

Status legend: 🔴 open · 🟡 partially fixed / fix shipped but unverified · ✅ fixed & verified

---

## 0. CLI proof-command output — attempted fix shipped, confirmed NOT working

**Status: ✅ fixed & verified (2026-07-11).** Added a second, `console=True` PyInstaller
`EXE()` target (`GrafelCLI.exe`) in `Grafel.spec` sharing the same `Analysis`/`PYZ` as the
windowed `Grafel.exe`; `installer.iss` now bundles it into `{app}` (already on PATH via
the `addtopath` task); the `grafel-query.cmd`/`grafel-path.cmd`/`grafel-explain.cmd`/
`grafel-save-result.cmd`/`grafel-mcp.cmd` shims (and their generator in
`grafel_core/workflows.py`) now look for `GrafelCLI.exe` instead of `Grafel.exe` and no
longer fall back to the broken windowed exe at all. `run_headless()` also now propagates
`build_graph()`'s real exit code instead of always returning 0. Empirically re-proven
against the actual built `dist\GrafelCLI.exe` (not just unit tests): captured piped
output via `--proof-command` had length 0 with the old `Grafel.exe`, now returns real
graph content (99 lines for a `query` proof-command, e.g. `Traversal: BFS depth=2 ...`
plus `NODE ...` lines); a temp-PATH `.cmd` routing test (`GrafelCLI.exe` copied to a
scratch dir prepended to `PATH`, then `graphify-out\grafel-query.cmd "..."` invoked
exactly as an AI agent would) returned exit code 0 and 87 lines of real graph output.
Full suite still 69/69 passing after the change.

- **Original bug:** `graphify-out/grafel-query.cmd` (and `grafel-path.cmd`,
  `grafel-explain.cmd`, `grafel-save-result.cmd`) prefer the **installed** `Grafel.exe`
  over the dev-mode `grafel.py` fallback when it's on PATH. That exe is built with
  `console=False` (`Grafel.spec:41`). `main()`'s `--proof-query`/`--proof-command`
  dispatch (`run_proof_command()` in `grafel.py`) writes via `sys.stdout.write(out)`,
  which is a no-op for a windowed PyInstaller build — the query still runs internally
  (graphify executes, the usage-proof event still gets logged), but the caller sees
  **zero output**. This breaks the "strict mode" routing rules Grafel itself writes
  into `CLAUDE.md`/`AGENTS.md` for every repo it wires, for anyone using the installed
  product rather than running from source.
- **Attempted fix (grafel.py, `_ensure_cli_console()`):** calls
  `ctypes.windll.kernel32.AttachConsole(-1)`, falls back to `AllocConsole()`, then
  rebinds `sys.stdout`/`stderr`/`stdin` to `CONOUT$`/`CONIN$`. Called from `main()`
  right before the `--proof-query`/`--proof-command` branches.
- **Why it doesn't work:** `AttachConsole`+`CONOUT$` only helps genuine *interactive*
  terminal use with no redirection. It writes to a console screen buffer, which is a
  **different destination** than a redirected pipe. The actual real-world consumption
  pattern — an AI agent's shell tool capturing stdout via a pipe (exactly how
  `grafel-query.cmd` is meant to be used) — is still broken. Confirmed empirically:

  ```powershell
  $out = & ".\dist\Grafel.exe" --proof-command "$PWD" query "..."
  # captured length: 0   <- still empty, even in the build with the shim
  ```

- **Real fix needed:** build a dedicated `console=True` companion executable/PyInstaller
  `EXE()` entry point (share the same `Analysis`/`PYZ` in `Grafel.spec`, just a second
  `EXE()` block with `console=True`, e.g. `GrafelCLI.exe`) used **only** for the CLI
  dispatch paths (`--proof-query`, `--proof-command`, possibly `--run-grafel-strict-mcp`
  and the headless `Grafel.exe <path>` path too — verify those aren't silently broken
  the same way). Update the four `grafel-*.cmd` shims to call the console companion
  instead of `Grafel.exe` for these operations. This is the standard, reliable pattern
  for Windows apps that are both a GUI and a scriptable CLI — don't keep patching the
  windowed exe's stdout.
- **Also verify:** whether `--run-grafel-strict-mcp` (used by `grafel-mcp.cmd`) has the
  same problem. It wasn't touched by the shim, and the audit assumed it was fine, but
  that assumption was never actually tested against the installed windowed exe with a
  real piped MCP client — worth confirming before relying on it.

---

## 1. "Proven savings" dashboard number is not measuring what it claims

**Status: ✅ fixed & verified (2026-07-11).** Stats split into two counters: the
hypothetical deltas from `_compute_savings`/`_compute_ab`/`_ask_worker` (and
`_benchmark_worker`, same defect) now go through a new `App._record_estimated` into
`cfg["stats"]["estimated_tokens"]`, while `cfg["stats"]["saved_tokens"]` is meter-proven
only; `show_dashboard`/`_log_savings_health` now label the two numbers separately
("REALIZED (proven by the live meter)" vs "ESTIMATED (hypothetical what-if, NOT
realized)"). Replay is now side-effect-free via strategy (a): a new pure
`meter_runtime.prompt_recording_decision(caught_up, proven, saved_tokens)` gates both
`_record_saved` and `claude_baseline_update` in `_session_monitor`'s `flush()` so only
prompts completing after the tailer catches up to live are persisted (chosen over the
high-water-mark option (b) because it needs no new persisted state and the
between-meter-sessions undercount is explicitly acceptable); a "new chat" file switch
also resets `replayed = False` so a resumed session's re-contained transcript replays
display-only. Covered by `test_replay_pass_never_re_records_savings` /
`test_replay_pass_never_updates_baseline` (`tests/test_grafel_runtime.py`): the same
prompt sequence run through a second replay pass leaves the recorded total unchanged.

**Severity: silent-wrong-number, highest — this is the product's core sales claim.**

Three separate defects inflate the same persisted counter `cfg["stats"]["saved_tokens"]`
(shown by `show_dashboard` as *"Total tokens kept out of AI context"* and by
`_savings_health_snapshot` as `proven_saved_tokens`):

- `grafel.py:_compute_savings` (~line 2272) calls
  `self._record_saved(repo_tokens - graph_tokens)` every time the user clicks SAVINGS.
  Nothing was actually saved — it's a static measurement, not an event. Click it 5×
  on a 2M-token repo and the dashboard "proves" ~10M tokens saved. Same pattern in
  `_compute_ab` (~line 2326) and `_ask_worker` (~line 2383): each records the
  hypothetical `without - with` delta as if it were realized.
- `_session_monitor` **replay re-records history.** The monitor replays each session's
  jsonl from `pos=0` every time the meter starts (and again whenever a "new chat" file
  appears — including resumed sessions, whose new jsonl contains the full prior
  transcript). `flush()` calls `_record_saved(summary["saved_tokens"])` for every
  historical "proven" prompt during replay. Toggle the meter off/on N times → the same
  historical savings get persisted N times.
- The same replay re-feeds `claude_baseline_update` with duplicate samples for unwired
  repos on every restart, growing `n` and re-weighting the baseline with the same data
  repeatedly.

**Fix:** split stats into `measured_estimate_tokens` (savings report / A/B / ask —
clearly labeled as hypothetical) vs `realized_tokens` (meter-proven only, from live
tailing). Make replay side-effect-free: pass a `replaying` flag into `flush()` that
suppresses `_record_saved`/baseline updates, or persist a per-session high-water mark
(last recorded `message.id`/timestamp) and only record beyond it.

**Test that would catch it:** run `_session_monitor` twice over the same fixture jsonl;
assert `stats["saved_tokens"]` is identical after the second run.

---

## 2. Every session's cache-cold first prompt is auto-"PROVEN"

**Status: ✅ fixed & verified (2026-07-11).** `claude_prompt_summary`'s proven branch now
requires `cr_resp > PROVEN_CR_FLOOR` (new named constant, 10_000 — the same floor
`claude_baseline_update` already used, now shared) in addition to the existing
`< base_cr * 0.85` check, so cache-cold turns (session start, post-compaction) can no
longer fabricate "proven" savings. Covered by
`test_cache_cold_first_prompt_is_not_proven` (`tests/test_grafel_runtime.py`): the exact
spec bucket (`cr=0, cw=50_000, msgs=5`, `base_cr=30_000`, wired) is `proven=False`, an
at-the-floor bucket is `proven=False`, and a genuinely lean cache-warm prompt above the
floor still comes out `proven=True`; the pre-existing `test_claude_runtime_helpers`
still passes unchanged.

**Severity: silent-wrong-number, highest.**

`grafel_core/meter_runtime.py:claude_prompt_summary` (~line 136):

```python
proven = wired_now and base_cr and cr_resp < base_cr * 0.85
```

The first prompt of any Claude session has `cache_read ≈ 0` (it's all cache-*creation*,
not cache-*read*), so `cr_resp ≈ 0` always beats the threshold, and
`saved_tokens = (base_cr - 0) * msgs`. An agentic first turn with 6 assistant messages
against a freshly-seeded 30k baseline fabricates ~180k "PROVEN saved" tokens per session
start, regardless of whether Grafel changed anything. Same thing happens again after any
mid-session context compaction. Note the asymmetry with `claude_baseline_update`, which
*does* guard with `cr_resp <= 10_000` (line 160) — the proven branch has **no floor at
all**.

**Fix:** require `bucket["cr"]` (or `cr_resp`) above the same 10k floor in the proven
branch too. Consider requiring 2–3 consecutive lean prompts before declaring "proven"
rather than a single turn.

**Test:** bucket with `cr=0, cw=50_000, msgs=5`, `base_cr=30_000`, `wired_now=True` —
assert `proven is False`.

---

## 3. Log tailing drops or duplicates data on partial writes

**Status: ✅ fixed & verified (2026-07-11).** New pure helper
`read_complete_lines(path, pos)` in `grafel_core/sessions.py`: binary-mode read that
only consumes up to the last `b"\n"` in the new data — a line the writer is still
mid-write stays unconsumed (pos never advances past it) and is re-read whole on the
next poll instead of being dropped in two unparsable halves; the complete portion is
decoded with `errors="replace"` (a genuine encoding issue now shows up instead of
silently eating bytes), and cutting at a newline means a multibyte UTF-8 char can no
longer be split at the decode boundary. The helper also resets `pos` to 0 when the
file shrank. All three tailers now go through it: `iter_vscode_chat_events` and
`iter_codex_token_counts` internally (which also gives `_copilot_monitor` /
`_codex_monitor` the previously-missing truncation-reset guard), and
`_session_monitor` in `grafel.py` directly, replacing its text-mode
`seek/read/tell` block. Covered by four new tests in `tests/test_grafel_core.py`:
a JSON line split mid-way across two writes is counted exactly once (not zero, not
twice, not corrupted) for both the Claude and Copilot parse paths, and a
shrunk-file rewrite is detected and re-read instead of returning empty forever
(direct helper test + through `iter_vscode_chat_events`). Full suite 87/87 passing.

**Severity: silent undercount / silent freeze.**

- `grafel.py:_session_monitor` (~lines 1964–1972):
  `fh.seek(pos); chunk = fh.read(); pos = fh.tell()`. If Claude Code is mid-write of a
  line when the 1.5s poll fires, the truncated line fails `json.loads` and is skipped —
  but `pos` has already advanced past it, so the remainder read on the next poll is also
  garbage. Both halves get dropped, permanently (dedup never re-surfaces it). Same
  pattern in `sessions.py:iter_vscode_chat_events` and `iter_codex_token_counts`. Large
  assistant messages (multi-KB JSON lines, common with big tool outputs) hit this
  routinely. Text-mode reads with `errors="ignore"` can also split a multibyte UTF-8
  char at the read boundary.
- `_copilot_monitor` has **no truncation reset**. `_session_monitor` has
  `if size < pos: pos = 0`, but the Copilot loop doesn't. VS Code rewrites
  `chatSessions/*.jsonl` on window reload; once the file shrinks, `f.seek(pos)` lands
  past EOF, `read()` returns `""` forever, and that tab silently stops counting with no
  error.

**Fix:** read in binary, only consume up to the last `b"\n"`
(`chunk.rfind(b"\n")`), advance `pos` to there, decode only the complete portion. Add
the same `size < pos → pos = 0` truncation-reset guard to `_copilot_monitor`.

**Test:** feed `iter_vscode_chat_events`/`parse_claude_jsonl_chunk` a file written across
two calls that split a JSON line mid-way; assert the event is eventually counted exactly
once (not zero, not twice).

---

## 4. Server: no owner check on graph upload/download

**Status: ✅ fixed & verified (2026-07-11).** `put_graph`/`get_graph` in `server/app.py`
now enforce `owner_key` (409 on a conflicting PUT, 403 on a cross-owner GET);
`require_admin` uses `secrets.compare_digest` with a guard against a missing header;
`put_graph` rejects oversized bodies via `MAX_GRAPH_BYTES` (413); `/license/validate`'s
seat check + activation insert are now one `BEGIN IMMEDIATE` transaction. Covered by 15
new tests in `tests/test_server_graph.py`; full suite 69/69 passing (independently
re-run, not just the implementing agent's own report).

**Severity: data leak / data loss — fix before deploying the backend.**

`server/app.py:put_graph`/`get_graph` (~lines 151–175) only check "caller holds *some*
valid license" — `owner_key` is stored but **never enforced** in the query. The client
(`grafel.py:cloud_upload`, ~line 3279) uses `os.path.basename(self.repo_path)` as
`project_key`, so two different customers with same-named repos (e.g. both named
`backend`) collide: the second upload silently overwrites the first, and either
customer can download the other's graph — which encodes their proprietary codebase
structure, file names, and symbols.

**Fix:** `SELECT ... WHERE project_key=? AND owner_key=?`; on PUT, reject (409) when the
row exists with a different `owner_key`, or namespace the key server-side as
`f"{license_key}:{project_key}"`.

**Also while touching this file:**
- Use `secrets.compare_digest` in `require_admin` (timing-safe comparison).
- Cap upload body size.
- `/license/validate`'s seat check is check-then-insert — two machines activating
  simultaneously can exceed `seats`.

(This whole file is explicitly starter/scaffold code per `HANDOFF.md`, so low urgency
until the backend is actually deployed — but the owner-key fix is one line and the data
at risk is customer IP, so do it before that day comes.)

---

## 5. Strict mode is undermined by Grafel's own MCP wiring

**Status: ✅ fixed & verified (2026-07-11).** `install_repo_mcp`
(`grafel_core/workflows.py`) now takes a `strict_mode` parameter (default
`required_alerts`, injected from `App.install_mcp` via `self._strict_mode()`; the
headless path inherits the default): in `required`/`required_alerts` the unrestricted
`@modelcontextprotocol/server-filesystem` entry is skipped entirely from both
`.mcp.json` and `.vscode/mcp.json` (with a log line explaining why), while `advisory`
keeps the old behavior. Caveat: `merge_json_servers` only adds entries, so a
filesystem entry written earlier in advisory mode is not actively removed on a
strict re-install — that's the #9 "merge_json_servers never updates existing
entries" bug, still open. `SRC_RE` in `strict_mcp.py` is now quote-aware
(`src="path with spaces"` or bare `src=path`), so graph output paths containing
spaces enter the allowlist correctly. The allowlist item was implemented as a
middle ground rather than a full per-query reset: a sliding window of the last
`ALLOWLIST_RESULT_WINDOW` (5) successful query/path/explain results (a full reset
would break the legitimate query → path/explain → read-files-from-either drill-down
flow); empty results neither grant nor revoke, and the `read_file` error message now
says "recent ... results" instead of the previously-false "last result". Covered by
`test_install_repo_mcp_strict_modes_skip_filesystem_server` /
`test_install_repo_mcp_advisory_mode_keeps_filesystem_server`
(`tests/test_grafel_workflows.py`) and
`test_source_files_from_graph_output_accepts_quoted_paths_with_spaces` /
`test_strict_gateway_allowlist_ages_out_old_query_results`
(`tests/test_grafel_core.py`). Full suite 83/83 passing.

**Severity: design contradiction — the enforcement feature doesn't enforce.**

- `grafel_core/workflows.py:install_repo_mcp` (~line 79) installs an **unrestricted**
  filesystem MCP server (`@modelcontextprotocol/server-filesystem`, rooted at the repo)
  into the same `.mcp.json`/`.vscode/mcp.json` as `grafel-strict`. The routing block
  tells the agent to "use the grafel-strict tools instead of direct filesystem tools" —
  while Grafel hands the agent a full-read bypass in the same config file.
  `StrictGateway` can only gate its own tool surface; it has no way to see or block the
  client's built-in Read/Grep or the unrestricted filesystem server. With that server
  present, "Required" strict mode is decorative.
- `strict_mcp.py:source_files_from_graph_output` — `SRC_RE = r"\bsrc=([^]\s]+)"`
  truncates at the first space. Any graph output path containing a space (this very repo
  lives under `OneDrive - iLab`) never enters the allowlist, so
  `grafel.read_file` refuses files the graph legitimately returned — a confusing
  hard-block specifically for users with spaces in their path, which is a common
  Windows setup (OneDrive-synced folders, "My Documents", etc.).
- `allowed_files` only grows for the life of the server — one broad query permanently
  unlocks those files, with no per-question scoping, weakening the "only files returned
  by the *last* result" claim in the tool's own error message.

**Fix:** when strict mode is `required`/`required_alerts`, skip installing the
filesystem MCP server (or scope it to `graphify-out/` only). Make `src=` parsing
quote-aware (`src="..."`, accept spaces inside quotes). Consider resetting or aging the
allowlist per query rather than accumulating for the process lifetime.

---

## 6. `~/.grafel.json` writes are racy and non-atomic

**Status: ✅ fixed & verified (2026-07-11).** Every `self.cfg` read-modify-write-persist
now runs under `self._cfg_lock`: `_record_saved` / `_record_estimated` /
`_record_brevity_saved` / `_record_memory_compression_saved`, `remember`, the first-run
`seen` save, `_baseline_for` (whole check-seed-persist sequence, so two monitors can't
double-run the `repo_token_stats` walk or expose the `clear()/update()` window), and the
baseline update in `_session_monitor`'s `flush()`. `workspace.save_config` is now atomic
(tempfile via `mkstemp` in the same directory + `os.replace`, temp cleaned up on any
failure), and `on_close` does one final `_save_cfg_locked()` before `os._exit(0)` so
every-3rd-sample baseline state is flushed. Covered by
`test_save_config_round_trips_and_leaves_no_temp_files`,
`test_save_config_failed_write_keeps_original_and_cleans_temp`, and
`test_save_config_concurrent_writers_never_corrupt_file` (`tests/test_grafel_core.py`).

**Severity: data loss + lost updates.**

- `_record_saved` / `_record_brevity_saved` / `_record_memory_compression_saved`
  (`grafel.py:2429–2448`) do read-modify-write on `self.cfg` and call `save_config`
  **without** `self._cfg_lock`, while N session-monitor threads can be running
  concurrently. Two monitors flushing at once can lose increments; two interleaved
  `save_config` calls (plain `open(..., "w")` in `workspace.py:51`, not atomic) can
  interleave writes and corrupt the JSON file. `load_config` swallows `ValueError` and
  returns `{}` on a parse failure — meaning stats, meter baselines, license key, and
  server URL all silently vanish on next launch.
- `_baseline_for` (~line 1696, added 2026-07-11) mutates the shared `baselines` dict via
  `baselines.clear(); baselines.update(...)` — a concurrent reader in another monitor
  thread can observe the empty window mid-mutation. Two monitors on the same repo can
  also race to seed (check-then-act on `bkey not in baselines`), each running a full
  `repo_token_stats` filesystem walk.
- `on_close` calls `os._exit(0)` (~line 2232), which can kill a `save_config` writer
  mid-write — same corruption path. Baseline updates are also only persisted every 3rd
  sample (`rec["n"] % 3 == 0`) and never flushed on close.

**Fix:** funnel every `self.cfg` mutation through `self._cfg_lock`. Make `save_config`
atomic (write to a tempfile in the same directory, then `os.replace`). Do one final
locked save in `on_close` before `os._exit`.

---

## 7. Live meter prices everything at Sonnet rates

**Status: ✅ fixed & verified (2026-07-11).** `_session_monitor` no longer hardcodes the
Sonnet `P_IN/P_CW/P_CR/P_OUT` constants: each usage bucket now carries the `model` field
already parsed by `parse_claude_jsonl_chunk`, and `flush()` prices it per prompt via new
pure helpers `meter_runtime.classify_claude_model` (same opus/sonnet/haiku/other
substring matching `scan_claude_usage` uses) and `meter_runtime.prices_for_model`
selecting from `CLAUDE_RATES`, feeding the existing `prices` parameter of
`claude_prompt_summary`. Covered by `test_per_model_meter_pricing`
(`tests/test_grafel_runtime.py`): identical token counts produce opus > sonnet > haiku
`real_cost` and exact per-model `cache_read_cost` values matching `CLAUDE_RATES`.

**Severity: wrong dollar numbers on the flagship screen.**

`_session_monitor` hardcodes `P_IN, P_CW, P_CR, P_OUT = 3.0, 3.75, 0.30, 15.0` (~line
1867) — Sonnet's rates. The parsed usage payload already includes `model`
(`sessions.py:528`), and `CLAUDE_RATES` already has per-model pricing (`grafel.py:146`),
but the meter ignores both and always uses Sonnet rates. An Opus session's "API-equiv"
cost and realized-savings dollars are understated ~5×; a Haiku session is overstated
~4×. `scan_usage` gets this right elsewhere in the app — the live meter, the thing users
actually watch in real time, doesn't.

**Fix:** classify `payload["model"]` per bucket (reuse the same opus/sonnet/haiku
matching logic `scan_claude_usage` already has) and price each bucket via `CLAUDE_RATES`
instead of the hardcoded constants.

---

## 8. A/B "WITHOUT Grafel" baseline matches on stopwords

**Status: ✅ fixed & verified (2026-07-11).** `savings.question_keywords` now filters a
small deliberate `QUESTION_STOPWORDS` set (does/work/what/where/this/that/with/from/…),
and a new pure `savings.question_file_matches` requires ≥2 distinct keyword hits per
file (or all keywords, for single-keyword questions; zero-keyword questions keep the old
match-everything upper bound) before `question_match_stats` counts it. The
`ab_report_lines`/`prompt_comparison_lines` labels now say "upper bound" instead of
implying a realistic agent baseline. Covered by `test_question_keywords_drop_stopwords`,
`test_question_match_stats_ignores_stopword_only_hits`, and
`test_question_match_stats_requires_two_distinct_keyword_hits`
(`tests/test_grafel_core.py`, next to the pre-existing
`test_question_match_stats_counts_matching_files`, which still passes).

**Severity: inflated headline number (and it feeds finding #1's bad counter too).**

`savings.py:question_keywords` takes every word ≥4 characters as a "keyword" — for "how
does authentication work?" that includes `does` and `work`. `question_match_stats`
counts a file as a match if **any** keyword appears anywhere in it. Nearly every source
file contains "work" or "does" somewhere, so the "WITHOUT" baseline ends up ≈ the entire
repo's token count for most natural-language questions — including the built-in
`BENCHMARK_QS`, which all contain such words. The report labels this "worst-case," but
as implemented it isn't a plausible grep-and-read baseline — it's effectively
`cat *`, which makes the "% reduction" number look better than a real comparison would.

**Fix:** drop a small stopword list (does/work/where/what/how/this/that/with/from/into
etc.), require ≥2 distinct keyword hits (or weight by hit count) before counting a file
as a match, and label the resulting number "upper bound" rather than implying it's a
realistic agent baseline.

---

## 9. Smaller bugs (assorted)

**Status: ✅ 11/13 fixed & verified, 1 investigated-and-fine (no code change), 1
genuinely still open (2026-07-12).** Full suite 93/93 passing (87 baseline + 6 new
tests covering the fixes below).

1. **`_flush_log` freezes all logging permanently on error** — ✅ fixed. The whole
   body now runs inside `try/finally`, with `self.root.after(100, self._flush_log)`
   moved into the `finally` so a `TclError` mid-flush (or the window being torn down)
   can no longer skip re-arming the next tick — every tab keeps updating for the rest
   of the session even after a bad flush. The per-item box write is now wrapped in its
   own `try/except tk.TclError: continue` so one destroyed tab's error can't abort the
   whole batch either. Also: the 4000-line trim now runs over
   `list(self._boxes.values()) + list(self._session_boxes.values())`, not just
   `_boxes` — per-AI-session tabs no longer grow unbounded during long meter runs. No
   dedicated automated test (this is Tk main-loop/timer wiring — not practically unit
   testable without a live Tk root); verified by code inspection of the `finally`
   placement and manual reasoning about the exception paths.
2. **UI-thread repo walk** — ✅ fixed. `_load_graph_report` is called directly from
   `pipeline` (which already runs on `self.worker`, a background thread — see
   `threading.Thread(target=self.pipeline, ...)` in `start()`), not scheduled onto the
   Tk thread via `root.after` anymore. The function now does the `graph_artifact_state`
   `os.walk` on the calling (worker) thread and only marshals the final text-box update
   back via `self.root.after(0, lambda: self._set_graph_report_text(txt))` — the same
   pattern already used elsewhere in the file. No dedicated automated test (Tk
   text-widget update, not unit-testable without a live root); the split into
   `_load_graph_report` (walk) / `_set_graph_report_text` (UI write) is a straight
   application of the existing `graphs.graph_artifact_state` helper, which already has
   `test_graph_artifact_state_marks_stale_graph` coverage for its logic.
3. **Chat export privacy** — ✅ fixed. `ensure_gitignore` now writes both
   `graphify-out/` and `grafel-chats/` via two `ensure_gitignore_entry` calls, and
   `_export_chats_worker` also calls `ensure_gitignore_entry(repo, "grafel-chats", ...)`
   directly so chats exported without a prior full pipeline run are still protected.
   Covered by `test_ensure_gitignore_entry_is_idempotent` (`tests/test_grafel_workflows.py`),
   extended to assert both `graphify-out/` and `grafel-chats/` land in `.gitignore` and
   each entry is independently idempotent.
4. **`write_routing_block` can lose user content on a partial-write recovery** —
   ✅ fixed. Chose "replace from `START` to EOF" over "refuse and warn": refusing would
   leave routing permanently missing until a human notices and manually cleans the
   file, which is worse for an unattended `graphify update`/auto-wire flow than
   deterministically recovering the (Grafel-owned) block while explicitly preserving
   everything above the marker. When `ROUTING_START` is present without
   `ROUTING_END`, the writer now finds the `START` index and rewrites
   `existing[:idx] + fresh_block` instead of appending — the next run's regex
   substitution has a matched `START…END` pair again and is a no-op on a stable file.
   A `log()` line ("recovered unterminated routing block") makes the recovery visible.
   Covered by new `test_write_routing_block_recovers_orphaned_start_marker`
   (`tests/test_grafel_core.py`): user content above an orphaned `START` marker
   survives, the half-written block is discarded, and a second write is idempotent.
5. **`merge_json_servers` never updates existing entries** — ✅ fixed the "never
   updates" bug; ⚠️ partially addressed the path-portability note. `merge_json_servers`
   now compares each managed entry's existing value against what would be written and
   overwrites only when it differs (leaves identical entries untouched, still
   idempotent byte-for-byte on a no-op merge); unmanaged entries (not present in the
   `servers` dict passed in) are never touched. Log line reports `added`/`updated`
   separately. Investigated the path issue: confirmed `install_repo_mcp` was writing
   a machine-absolute path into **both** `.vscode/mcp.json` and `.mcp.json`.
   `.vscode/mcp.json` now uses VS Code's documented `${workspaceFolder}` predefined
   variable (confirmed via VS Code docs: MCP config supports predefined/input
   variables) for `grafel-strict`'s `command`, so that file is portable across
   machines/drive letters when committed. `.mcp.json` (Claude Code's own format) has
   no documented equivalent variable, so it necessarily keeps the machine-absolute
   path — but that's no longer a *permanent* breakage for teammates, since the
   "never updates" fix means a stale absolute path is now corrected automatically the
   next time anyone on that machine re-runs the wiring flow. JSONC-comment-skipping
   was left unchanged (lower value, higher risk of subtly breaking existing configs;
   not attempted). Covered by new `test_merge_json_servers_updates_changed_entries`
   (stale value overwritten, unmanaged entry preserved, identical merge is a no-op)
   and `test_install_repo_mcp_writes_local_configs` extended to assert the
   `${workspaceFolder}`-relative vscode command and the absolute claude command.
6. **`claude_log_dir` encoding collisions** — ✅ addressed via the cross-check
   strategy the doc suggested, not a scheme change (Grafel doesn't own Claude Code's
   encoding, so it can't unilaterally fix the collision at the source).
   `session_scope_details` (`grafel_core/live.py`) now only trusts the encoded
   log-directory-name match (`session_dir in scope_dirs`) when the session's real
   `cwd` could **not** be resolved at all (`not cwd`); whenever a `cwd` *is*
   resolvable it's already checked earlier in the function and is authoritative
   (matches `HANDOFF.md`'s "always use `session_cwd()`" guidance) — so a session whose
   real cwd points at a different, similarly-encoded repo is no longer pulled into
   scope just because the directory names collided. Also found and fixed the actual
   caller the doc called out as not cross-checking: `_export_chats_worker` iterated
   `claude_log_dir(fld)`'s `*.jsonl` files directly with no cwd check at all (unlike
   the meter/health-check paths, which already route through `session_scope_details`)
   — it now calls `session_cwd_fast` per file and skips any file whose real cwd isn't
   `path_is_related` to the target folder. `dirs` in `meter_scope_state` is now also
   normalized (case/realpath) so the comparison is consistent with `session_dir`.
   Covered by new `test_scope_dir_match_requires_unknown_cwd`
   (`tests/test_grafel_product.py`): a session with a colliding dir name but a
   resolvable, non-matching cwd is `machine`-scoped; the same dir match with no
   resolvable cwd still counts as `workspace`-scoped.
7. **`scan_claude_usage` dedup is per-file, not per-scan** — ✅ fixed.
   `iter_claude_usage_entries(path, seen=None)` now accepts a shared `seen` set;
   `scan_claude_usage` creates one `seen` set before the file loop and passes it into
   every call instead of letting each file start a fresh set, so a resumed session's
   duplicate message ids across the old + new `.jsonl` are only counted once for the
   whole scan. Covered by new `test_scan_claude_usage_dedupes_across_resumed_session_files`
   (`tests/test_grafel_core.py`): the same message id split across two files in one
   project directory is counted exactly once in `data["responses"]`/`totals`.
8. **Single-instance lock fails silently** — ✅ fixed. When the bind fails (port
   taken) *and* the "is this really Grafel?" connect-and-handshake also fails
   (`OSError` on `create_connection`/`sendall`), a `messagebox.showerror` now explains
   the port conflict and suggests `--new-window` as a workaround, using a throwaway
   hidden `tk.Tk()` root (the main app hasn't been constructed yet at this point in
   `main()`) instead of exiting with zero feedback and no window. Falls back to a
   `print()` if Tk itself can't be initialized. No automated test (real OS socket +
   Tk dialog interaction at process-startup time, not practically unit-testable);
   verified by code inspection of the new `except OSError` branch.
9. **`pip install graphifyy`** — investigated, **confirmed correct, no change made**.
   `pip show graphifyy` in this environment resolves to a real installed PyPI
   distribution (`graphifyy` 0.9.9, "AI coding assistant skill ... turn any folder of
   code ... into a queryable knowledge graph", home page
   `github.com/safishamsi/graphify`) whose importable module name is `graphify` — the
   double-y is the actual **distribution/package** name on PyPI, distinct from the
   **import** name, which is a legal and common (if confusing) PyPI convention. It's
   used consistently: `build.bat` (`pip install --quiet graphifyy`) and
   `.github/workflows/build.yml` (`pip install pyinstaller pillow pystray graphifyy`)
   both install the same name, while `Grafel.spec`'s `collect_all('graphify')` and all
   in-repo imports correctly use the *module* name `graphify`. Left a one-line comment
   at the `pipeline()` call site noting this isn't a typo, since it reads like one on
   sight. No test needed — this was a verify-don't-guess check, not a behavior change.
10. **`terminate()` doesn't kill grandchildren on Windows** — ✅ fixed proactively
    (real risk, not over-engineering): `graphify_cmd()` resolves to a pip
    console-script launcher (`graphify.exe`) or the frozen exe's self-dispatch, and on
    Windows a console-script launcher **is** a separate child process of the Python
    interpreter that does the actual work — so `Popen(...).terminate()` on the
    launcher does not guarantee the real worker dies, unlike on POSIX where exec
    replaces the process image in place. New `watch_runtime.terminate_watch_process(
    proc, os_name=None, run=None)` uses `taskkill /F /T /PID <pid>` (recursive tree
    kill) on Windows and falls back to `.terminate()` elsewhere or if the process has
    already exited/is `None`; `toggle_watch`, `_do_autowire`, and `on_close` (all three
    `.terminate()` call sites on `self.watch_proc`) now go through it. Covered by new
    `test_terminate_watch_process_kills_tree_on_windows`
    (`tests/test_grafel_runtime.py`) with an injectable fake process and `run`
    callable: asserts the exact `taskkill` argv on `os_name="nt"`, plain `.terminate()`
    on other OSes, and a no-op for an already-exited or `None` process.
11. **`_start_watch` runs installer/release preflight checks on every watch start** —
    ✅ fixed. The `release_preflight(...)` call and its `[watch] preflight warning`
    log line were removed from `_start_watch` entirely (along with the now-unused
    `from grafel_core.release import detect_inno_setup, release_preflight,
    run_installer_build` import in `grafel.py` — nothing else in the file used those
    three names). The check still exists and runs where it belongs, in `build.bat`
    (`python -c "from grafel_core.release import release_preflight; ..."`), which is
    the actual dev/release-build path. `grafel_core/release.py` and its
    `release_preflight`/`detect_inno_setup` functions are untouched; existing
    `test_release_preflight_and_harness` (`tests/test_grafel_product.py`) still covers
    the helper's own logic, just no longer exercised from a normal WATCH click.
12. **`copilot_apply_events` kind==2 handling** — 🟡 made safe against both
    interpretations via dedup; true wire-format semantics still unconfirmed by a
    real fixture. No captured Copilot `kind:2` event exists in `tests/` (the two
    `kind` fixtures present are `kind:1`, a different op), and an earlier attempt
    to check this machine's real VS Code `chatSessions/*.jsonl` logs was blocked
    by sandbox policy, so whether VS Code emits `kind:2` on `["requests"]` as a
    full-array replacement or an append remains unknown. Instead of guessing,
    `meter_runtime.copilot_apply_events` now handles the None-index request
    events `iter_vscode_chat_events` derives from `kind==2` defensively: each
    batch is checked against the current tail of the accumulated requests (by
    `text`), and if a non-empty prefix of the batch exactly matches the tail it
    is treated as a resend of already-known items — only the genuinely new
    suffix is appended. Under the true-append interpretation nothing matches and
    every item is appended exactly as before (no behavior change); under the
    full-resend interpretation prior requests are no longer duplicated. Covered
    by three explicitly synthetic/hypothesis-driven tests in
    `tests/test_grafel_runtime.py`
    (`test_copilot_kind2_synthetic_true_append_unchanged`,
    `test_copilot_kind2_synthetic_full_resend_not_duplicated`,
    `test_copilot_kind2_synthetic_edge_cases`). A real captured Copilot
    session-store fixture (or a VS Code source read, out of this repo) is still
    needed to confirm the actual semantics either way.
13. **`session_cwd_fast`'s 64KB tail-read can misclassify a session** — ✅ fixed.
    `session_cwd_fast(jsonl_path, tail_bytes=65536, fallback=True)` now falls back to
    the full `session_cwd()` scan when the tail-based scan finds no `"cwd"` match
    *and* the read was actually partial (`size > tail_bytes` — small files where the
    "tail" is the whole file never trigger the extra scan, so the common case pays no
    extra cost). Checked every caller (`grafel.py`'s meter/session-health/export
    call sites, `grafel_core/live.py`'s scope helpers, `grafel_core/meter_runtime.py`):
    none of them wanted fast-only "might miss" semantics on purpose, so the new
    fallback is on by default; added a `fallback=False` opt-out for exactly the case
    KNOWN_ISSUES flagged (a caller that specifically wants the original fast/lossy
    behavior for hot-path performance) even though no current caller uses it, so the
    contract stays available without forcing a design decision that isn't needed yet.
    Covered by new `test_session_cwd_fast_falls_back_when_tail_is_swamped`
    (`tests/test_grafel_core.py`): a huge tool-output line pushed past the tail window
    still resolves via fallback; `fallback=False` reproduces the old miss; small files
    are unaffected.

---

## 10. Brevity Mode corrupts inline code/URLs via placeholder collision

**Status: ✅ fixed & verified (2026-07-12).**

Found in a follow-up audit after the rest of this file was last updated.
`compress_sentence` (`grafel_core/brevity.py`) protects inline backtick code
spans, URLs, and ALL-CAPS/constant-looking words by swapping each for a
placeholder before filler-word compression, then restoring them at the end.
The old placeholder scheme `__GRAFEL_TOKEN_n__` itself matched the ALL-CAPS
protection regex (`\b[A-Z_][A-Z0-9_]{1,}\b` — underscores are word chars), so
a placeholder already inserted for a code span or URL got wrapped in a
*second* placeholder by the later ALL-CAPS pass, and the insertion-order
restore loop could no longer find the inner key. Result: "COMPRESS MD" wrote
literal `__GRAFEL_TOKEN_0__` garbage into the live `CLAUDE.md`/`AGENTS.md`/
`README.md` in place of any inline `` `command` `` or URL on a plain
(non-fenced) line — e.g. ``Run `npm install` now.`` became
`Run __GRAFEL_TOKEN_0__ now.` (recoverable from the `.original.md` backup,
but the live file was corrupted) — directly violating the brevity rule block
Grafel itself writes ("Keep code, commands, paths, URLs ... exact"). The
existing test only covered **fenced** code blocks, which route through
`split_fenced_regions` and never hit this path.

Fix: the placeholder is now structurally unmatchable by every protection
regex — `\x00grafel:<n>\x00` (null-byte-delimited, lowercase: no backticks,
no `http`, no `[A-Z_][A-Z0-9_]+` run) — so ordering between protection steps
no longer matters; restoration also runs in reverse insertion order as
defense in depth against any future nesting. Covered by four new tests in
`tests/test_grafel_brevity.py`: inline code span preserved on a plain line,
URL preserved, the ALL-CAPS + code + URL combination that triggered the
collision, and an end-to-end `compress_memory_text` plain-line case; the
existing fenced-block test still passes unchanged.

---

## 11. CI never built GrafelCLI.exe, breaking the installer step on release

**Status: 🟡 fix shipped (2026-07-12), validated by side-by-side comparison against
`build.bat` + YAML parse — not verified against a real CI run.** The Windows leg of
`.github/workflows/build.yml`'s `build` job still invoked PyInstaller with ad-hoc CLI
flags (`pyinstaller --noconfirm --clean --onefile --windowed --name Grafel ... grafel.py`),
which only ever produces the windowed `Grafel.exe` — it was never updated when #0's fix
added the second `console=True` `EXE()` target (`GrafelCLI.exe`) to `Grafel.spec`. The
downstream `installer` job downloads the `Grafel-windows` artifact into `dist\` and runs
`iscc installer.iss`, whose `[Files]` section references `dist\GrafelCLI.exe` with no
`skipifsourcedoesntexist` flag — so the next tag push would hard-fail at the
"Compile installer" step (or worse, if the flag had been added instead, ship an installer
whose `grafel-*.cmd` shims silently produce no output — the exact bug #0 fixed).

**Fix:** the Windows matrix leg now builds from the spec, matching `build.bat` step 4
(`python -m PyInstaller --noconfirm --clean Grafel.spec`), producing both exes; the
macOS/Linux legs keep the old CLI-flag invocation untouched (`Grafel.spec` is
Windows-only: backslash `assets\` paths, `version_info.txt`, the console/windowed
subsystem split). No other workflow changes were needed — prerequisites were already in
place: `assets/version_info.txt` is checked in, CI already runs `python assets/make_icon.py`
before building, the `pip install pyinstaller pillow pystray graphifyy` line already
covers both `collect_all('graphify')` and `collect_all('pystray')` in the spec, and the
artifact upload path `dist/*` already picks up every exe in `dist\`.

---

## 12. UI freeze risk in `_baseline_for`, orphaned watch process in auto-wire, and server upload-cap timing

Three unrelated small bugs from the same follow-up audit as #10/#11.

### 12a. `_cfg_lock` held across a full-repo filesystem walk (UI freeze risk)

**Status: ✅ fixed & verified (2026-07-12).** `App._baseline_for` (`grafel.py`) — added
by the #6 config-write-safety fix — held `self._cfg_lock` for the *whole*
check-seed-persist sequence, including the `repo_token_stats` full-repo `os.walk` +
tokenize (genuinely slow on large/OneDrive-synced repos). `_cfg_lock` is also acquired
synchronously on the Tk main thread by UI callbacks (`_on_brevity_changed`,
`_on_strict_mode_changed`, `_on_meter_scope_changed`, and every button handler that
persists via `_save_cfg_locked`), so a background monitor thread inside the walk froze
the entire GUI until the walk finished — the same "background walk blocks the Tk
thread" bug class the `_load_graph_report` fix (#9.2) removed, reintroduced via the
lock. Fix: the `repo_token_stats` walk now runs *outside* the lock; only the fast
seed/`clear()`/`update()`/`save_config` step takes `_cfg_lock`, with the
`bkey not in baselines` membership check repeated inside it so two monitors that both
walked concurrently can't double-seed (first to acquire the lock wins; the loser's walk
result is discarded — wasteful once, but no double-write and no `clear()/update()`
window visible to readers). Per this repo's convention `App` methods aren't
unit-tested directly; verified by code inspection that no `repo_token_stats` call
remains under the lock, and the underlying pure helper's existing test
(`test_seed_baseline_if_missing_estimates_and_is_replaceable`,
`tests/test_grafel_runtime.py`) still passes unchanged.

### 12b. Auto-wire can orphan a duplicate `graphify watch` process

**Status: ✅ fixed & verified (2026-07-12).** `App._do_autowire` (`grafel.py`) pauses an
active watcher during wiring (sets `self.watch_proc = None`, button shows idle) and
resumed it unconditionally in its `finally` block. If the user clicked the
idle-looking WATCH button during the minutes-long `_autowire_build`, `toggle_watch`
started a new watcher — and the `finally` then spawned a *second* `graphify watch`
against the same repo, overwriting the tracking handle and orphaning the user's
watcher (invisible to STOP WATCH and app shutdown, racing the tracked one to rebuild
`graphify-out/graph.json` on every save). Fix: the `finally` block now checks
`self.watch_proc is not None and self.watch_proc.poll() is None` and skips the resume
(with a log line) when a watcher is already tracked. `toggle_watch` itself is safe
(it stops a live watcher rather than double-starting), so the call-site guard is the
whole fix; kept inline rather than extracted to `grafel_core/watch_runtime.py` — it's
a two-line boolean on live `Popen` state, and `watch_start_plan`/`watch_exit_state`
model presentation, not process-spawn decisions. Verified by code inspection (no
direct `App`-method test scaffolding, same as 12a).

### 12c. Server upload size check ran only after the body was fully parsed

**Status: ✅ fixed & verified (2026-07-12).** `server/app.py:put_graph` checked
`len(json.dumps(body)) > MAX_GRAPH_BYTES` — but `Body(...)` binding has already
buffered and JSON-decoded the entire payload before the handler runs, so the check
never prevented the memory hit, it only rejected after the fact. Fix: new dependency
`reject_oversized_upload(request: Request)` on the PUT `/graph/{project_key}` route
raises 413 from the `Content-Length` header *before* body parsing; absent or
non-numeric Content-Length falls through to the existing post-parse check, kept as
defense in depth against lying clients/chunked encoding. (Starter code per the module
docstring, not yet deployed — low urgency, cheap fix.) Covered by three new tests in
`tests/test_server_graph.py:UploadSizeCapTests`: a tiny body with an oversized
`Content-Length` header 413s pre-parse (httpx preserves a caller-supplied
Content-Length via `Headers.setdefault`, so the header can lie independently of the
body), an understated Content-Length with an oversized body still 413s via the
post-parse fallback, and a direct unit test of the dependency (oversized raises 413;
under-cap/absent/malformed headers fall through). The pre-existing
`test_oversized_body_rejected` passes unchanged (its 413 now comes from the
dependency, since TestClient sends an accurate Content-Length).

---

## Prioritized punch list

1. ~~**Fix #0 properly**~~ — ✅ done (2026-07-11).
2. ~~**Meter math integrity (#1 + #2)**~~ — ✅ done (2026-07-11): proven check floored
   at `PROVEN_CR_FLOOR`, replay made side-effect-free via
   `prompt_recording_decision`, estimated vs. realized counters split.
3. ~~**Tail robustness (#3)**~~ — ✅ done (2026-07-11): all three tailers routed
   through a new binary-mode `read_complete_lines` helper (only complete lines
   consumed, partial line re-read whole next poll), truncation-reset guard now
   covers `_copilot_monitor` too.
4. ~~**Config write safety (#6)**~~ — ✅ done (2026-07-11): every `self.cfg`
   read-modify-write locked under `_cfg_lock`, `save_config` made atomic
   (tempfile + `os.replace`), final locked flush in `on_close`.
5. ~~**Server owner check (#4)**~~ — ✅ done (2026-07-11).
6. ~~**Strict mode: don't install the unrestricted filesystem MCP server alongside
   grafel-strict (#5).**~~ — ✅ done (2026-07-11): filesystem server skipped in
   `required`/`required_alerts`, `src=` parsing made quote-aware, allowlist scoped
   to a sliding window of the last 5 graph results.
7. ~~**Per-model meter pricing (#7)** and **A/B stopword filtering (#8)**~~ — ✅ done
   (2026-07-11): meter buckets priced per model via `prices_for_model`/`CLAUDE_RATES`;
   A/B keywords stopword-filtered with a ≥2-distinct-hits match rule, labeled
   "upper bound".
8. ~~**The rest of #9**~~ — ✅ done (2026-07-12), 11 of 13 items fixed & verified with
   new tests (`_flush_log` re-arm + `_session_boxes` trim, UI-thread repo walk moved
   off the Tk thread, `grafel-chats/` gitignore, `write_routing_block` orphaned-marker
   recovery, `merge_json_servers` update-on-change + `${workspaceFolder}` for
   `.vscode/mcp.json`, `claude_log_dir` collision cross-checks, `scan_claude_usage`
   scan-wide dedup, single-instance-lock messagebox, Windows `taskkill /T` process-tree
   kill, release-preflight removed from the WATCH click path); 1 item
   (`pip install graphifyy`) investigated and confirmed correct, no change needed; 1
   item (`copilot_apply_events` kind==2 full-array-replacement question) was later
   made safe against both interpretations via a defensive tail-dedup in
   `copilot_apply_events` (see item #12 above) — no more duplication risk if it turns
   out to be a full resend, though the true wire format is still unconfirmed by a
   real fixture. Every other point (0-8) in this file was already fixed before this
   pass; **this file now shows every tracked point as fixed or defensively
   mitigated (item #12: semantics still unconfirmed).**
9. ~~**CI installer break (#11)**~~ — 🟡 fix shipped (2026-07-12): Windows CI leg of
   `.github/workflows/build.yml` switched from ad-hoc PyInstaller CLI flags to the
   `Grafel.spec` build (matching `build.bat`), so `GrafelCLI.exe` reaches the
   `Grafel-windows` artifact and the `installer` job's `iscc installer.iss` step can
   find it; validated by side-by-side comparison against `build.bat` and a YAML parse,
   awaiting confirmation from the next real tag-push CI run.
10. ~~**Brevity placeholder collision (#10)**~~ — ✅ done (2026-07-12): placeholder
    scheme changed to `\x00grafel:<n>\x00` (structurally unmatchable by any protection
    regex, so protection-step ordering no longer matters), restoration made
    reverse-insertion-order, and four regression tests added to
    `tests/test_grafel_brevity.py` covering inline code spans, URLs, and the ALL-CAPS
    collision combination on plain (non-fenced) lines.
11. ~~**Follow-up audit trio (#12)**~~ — ✅ done (2026-07-12): `_baseline_for`'s
    `repo_token_stats` walk moved outside `_cfg_lock` with a re-check-inside-the-lock
    seed (12a, UI freeze risk); `_do_autowire`'s `finally` block now skips the WATCH
    resume when a watcher is already tracked, so a user click during wiring can no
    longer orphan a duplicate `graphify watch` process (12b); `put_graph` upload cap
    now enforced pre-parse via a `Content-Length` dependency raising 413, existing
    post-parse check kept as defense in depth, three new tests in
    `tests/test_server_graph.py` (12c).
