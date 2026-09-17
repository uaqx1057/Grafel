import unittest

from grafel_core import meter_runtime, watch_runtime


class GrafelRuntimeTests(unittest.TestCase):
    def test_watch_start_plan_and_exit_state(self):
        plan = watch_runtime.watch_start_plan(r"C:\repo", quiet=False)
        self.assertEqual(plan["button_text"], "STOP WATCH")
        self.assertEqual(plan["status"], "Sentinel active - watching")
        self.assertEqual(len(plan["logs"]), 2)

        exit_state = watch_runtime.watch_exit_state(1, started_at=0, saw_output=False, now=1)
        self.assertEqual(exit_state["status"], "Watch failed")
        self.assertIsNotNone(exit_state["log"])

    def test_terminate_watch_process_kills_tree_on_windows(self):
        # KNOWN_ISSUES #9: graphify.exe (pip launcher) runs the engine as a
        # CHILD process — plain .terminate() on Windows orphans it. The helper
        # must use taskkill /T on nt and fall back to terminate() elsewhere.
        class FakeProc:
            def __init__(self, alive=True):
                self.pid = 4242
                self._alive = alive
                self.terminated = False

            def poll(self):
                return None if self._alive else 0

            def terminate(self):
                self.terminated = True

        calls = []
        proc = FakeProc()
        watch_runtime.terminate_watch_process(
            proc, os_name="nt", run=lambda cmd, **kw: calls.append(cmd)
        )
        self.assertEqual(calls, [["taskkill", "/F", "/T", "/PID", "4242"]])
        self.assertFalse(proc.terminated)

        proc = FakeProc()
        watch_runtime.terminate_watch_process(
            proc, os_name="posix", run=lambda cmd, **kw: calls.append(cmd)
        )
        self.assertTrue(proc.terminated)

        # already-exited or missing processes are a no-op
        calls.clear()
        watch_runtime.terminate_watch_process(
            FakeProc(alive=False), os_name="nt", run=lambda cmd, **kw: calls.append(cmd)
        )
        watch_runtime.terminate_watch_process(
            None, os_name="nt", run=lambda cmd, **kw: calls.append(cmd)
        )
        self.assertEqual(calls, [])

    def test_classify_watch_line(self):
        self.assertIsNone(watch_runtime.classify_watch_line(""))
        self.assertEqual(watch_runtime.classify_watch_line("updated graph")["tag"], "ok")
        self.assertEqual(watch_runtime.classify_watch_line("Traceback happened")["tag"], "err")
        self.assertEqual(watch_runtime.classify_watch_line("watching repo")["tag"], "dim")

    def test_meter_start_and_fallback_helpers(self):
        result = meter_runtime.meter_start_state(
            repo_path=r"C:\repo",
            scope_mode="repo",
            find_workspace_for=lambda _repo, _parse: (None, [r"C:\repo"]),
            parse_workspace_folders=lambda _ws: [r"C:\repo"],
            claude_log_dir=lambda _folder: r"C:\claude",
            list_ai_sessions=lambda _folders, _parse: [
                {"dir": r"C:\claude", "file": "a", "mtime": 2, "kind": "claude", "cwd": r"C:\repo"},
                {"dir": r"C:\copilot", "file": "b", "mtime": 1, "kind": "copilot", "cwd": r"C:\repo"},
                {"dir": r"C:\codex", "file": "c", "mtime": 3, "kind": "codex", "cwd": r"C:\repo"},
            ],
            session_cwd_fast=lambda _fp: r"C:\repo",
        )
        self.assertEqual(result["folders"], [r"C:\repo"])
        self.assertEqual(len(result["sessions"]), 3)
        self.assertEqual(result["sessions"][0]["kind"], "codex")
        self.assertEqual(result["out_of_scope_count"], 0)
        self.assertEqual(result["mode"], "repo")
        title, body = meter_runtime.meter_fallback_message([r"C:\repo"])
        self.assertIn("Grafel Live Meter", title)
        self.assertIn("repo", body)
        title, body = meter_runtime.meter_machine_sessions_message(
            [r"C:\repo"],
            3,
            {"claude": 1, "copilot": 1, "codex": 1, "other": 0},
        )
        self.assertIn("machine-wide", body)
        self.assertIn("1 Claude, 1 Codex, 1 Copilot", body)

    def test_copilot_runtime_helpers(self):
        reqs = meter_runtime.copilot_apply_events([], [
            ("request", 0, "Find auth"),
            ("usage", 0, "promptTokens", 10),
            ("usage", 0, "completionTokens", 4),
        ])
        self.assertEqual(reqs[0]["text"], "Find auth")
        self.assertEqual(reqs[0]["pt"], 10)
        self.assertEqual(reqs[0]["ct"], 4)
        self.assertEqual(meter_runtime.copilot_ready_indexes(reqs, printed=0, replayed=False, idle_seconds=0), [0])
        self.assertEqual(meter_runtime.copilot_ready_indexes(reqs, printed=0, replayed=True, idle_seconds=9), [0])

    # The three tests below are SYNTHETIC / hypothesis-driven (KNOWN_ISSUES
    # point 9, item 12): no real captured VS Code Copilot kind==2 event exists
    # in this repo, so the true wire-format semantics (append vs full-array
    # resend) are unconfirmed. They exercise copilot_apply_events' defensive
    # tail-dedup for None-index ("kind==2 style") request batches under BOTH
    # interpretations — they are not a confirmed real-world reproduction.

    def test_copilot_kind2_synthetic_true_append_unchanged(self):
        # All-distinct texts: dedup must never trigger; every event appends,
        # exactly like the pre-fix behavior (regression guard).
        reqs = meter_runtime.copilot_apply_events([], [
            ("request", None, "one"),
            ("request", None, "two"),
            ("request", None, "three"),
        ])
        self.assertEqual([r["text"] for r in reqs], ["one", "two", "three"])
        # a later distinct batch on top of existing requests still appends all
        reqs = meter_runtime.copilot_apply_events(reqs, [
            ("request", None, "four"),
            ("request", None, "five"),
        ])
        self.assertEqual([r["text"] for r in reqs],
                         ["one", "two", "three", "four", "five"])

    def test_copilot_kind2_synthetic_full_resend_not_duplicated(self):
        # Build up requests via normal indexed events first.
        reqs = meter_runtime.copilot_apply_events([], [
            ("request", 0, "alpha"),
            ("request", 1, "beta"),
            ("usage", 0, "promptTokens", 10),
        ])
        # kind==2-style batch resending everything-so-far plus one new item:
        # under the full-resend interpretation this must not duplicate alpha/beta.
        reqs = meter_runtime.copilot_apply_events(reqs, [
            ("request", None, "alpha"),
            ("request", None, "beta"),
            ("request", None, "gamma"),
        ])
        self.assertEqual([r["text"] for r in reqs], ["alpha", "beta", "gamma"])
        # existing usage data on the resent items survives untouched
        self.assertEqual(reqs[0]["pt"], 10)

    def test_copilot_kind2_synthetic_edge_cases(self):
        # empty incoming event batch: no-op, no crash
        reqs = meter_runtime.copilot_apply_events(
            [{"text": "alpha", "pt": 0, "ct": 0, "cr": 0.0}], [])
        self.assertEqual([r["text"] for r in reqs], ["alpha"])
        # batch where NOTHING matches the current tail: pure new appends,
        # everything is kept
        reqs = meter_runtime.copilot_apply_events(reqs, [
            ("request", None, "beta"),
            ("request", None, "gamma"),
        ])
        self.assertEqual([r["text"] for r in reqs], ["alpha", "beta", "gamma"])

    def test_claude_runtime_helpers(self):
        state = {"n": 0, "reqs": 0, "tok": 0, "cost": 0.0, "opp": 0.0, "opp_tok": 0, "realized": 0.0, "saved_tok": 0}
        bucket = {"in": 100, "cr": 20000, "cw": 50, "out": 400, "msgs": 2}
        summary = meter_runtime.claude_prompt_summary(
            state,
            bucket,
            base_cr=15000,
            wired_now=False,
            fraction=0.5,
            prices={"in": 3.0, "cw": 3.75, "cr": 0.30, "out": 15.0},
        )
        self.assertEqual(summary["state"]["n"], 1)
        self.assertGreater(summary["recoverable_tokens"], 0)
        updated, rec = meter_runtime.claude_baseline_update({}, "repo", False, 12000)
        self.assertEqual(rec["n"], 1)
        self.assertIn("repo", updated)

    def test_cache_cold_first_prompt_is_not_proven(self):
        # KNOWN_ISSUES #2: cr=0 (session start / post-compaction) used to always
        # beat the 85% threshold and fabricate huge "proven" savings.
        state = {"n": 0, "reqs": 0, "tok": 0, "cost": 0.0, "opp": 0.0, "opp_tok": 0, "realized": 0.0, "saved_tok": 0}
        prices = {"in": 3.0, "cw": 3.75, "cr": 0.30, "out": 15.0}
        cold = {"in": 0, "cr": 0, "cw": 50_000, "out": 0, "msgs": 5}
        summary = meter_runtime.claude_prompt_summary(
            state, cold, base_cr=30_000, wired_now=True, fraction=0.5, prices=prices
        )
        self.assertFalse(summary["proven"])
        self.assertEqual(summary["saved_tokens"], 0)
        # just under the floor is still not proven
        near_floor = {"in": 0, "cr": meter_runtime.PROVEN_CR_FLOOR * 2, "cw": 0, "out": 0, "msgs": 2}
        summary = meter_runtime.claude_prompt_summary(
            state, near_floor, base_cr=30_000, wired_now=True, fraction=0.5, prices=prices
        )
        self.assertFalse(summary["proven"])
        # a genuinely lean cache-warm prompt (above floor, under 85% of baseline)
        # still comes out proven
        warm = {"in": 0, "cr": 24_000, "cw": 0, "out": 100, "msgs": 2}
        summary = meter_runtime.claude_prompt_summary(
            state, warm, base_cr=30_000, wired_now=True, fraction=0.5, prices=prices
        )
        self.assertTrue(summary["proven"])
        self.assertGreater(summary["saved_tokens"], 0)

    def test_replay_pass_never_re_records_savings(self):
        # KNOWN_ISSUES #1: restart the meter -> the historical replay pass must be
        # side-effect-free. Simulate the same prompt sequence twice: run 1 replays
        # then goes live; run 2 (after a meter restart) sees everything as history.
        prices = {"in": 3.0, "cw": 3.75, "cr": 0.30, "out": 15.0}
        prompts = [
            ({"in": 0, "cr": 12_000 * 2, "cw": 0, "out": 50, "msgs": 2}, False),  # history
            ({"in": 0, "cr": 11_000 * 2, "cw": 0, "out": 50, "msgs": 2}, True),   # live
        ]

        def run_pass(recorded_total, live_flags):
            state = {"n": 0, "reqs": 0, "tok": 0, "cost": 0.0, "opp": 0.0,
                     "opp_tok": 0, "realized": 0.0, "saved_tok": 0}
            for (bucket, _), caught_up in zip(prompts, live_flags):
                summary = meter_runtime.claude_prompt_summary(
                    state, bucket, base_cr=30_000, wired_now=True, fraction=0.5, prices=prices
                )
                state.update(summary["state"])
                decision = meter_runtime.prompt_recording_decision(
                    caught_up, summary["proven"], summary["saved_tokens"]
                )
                if decision["record_saved"]:
                    recorded_total += summary["saved_tokens"]
            return recorded_total

        # run 1: first prompt is replayed history, second completes live
        total_after_first = run_pass(0, [flag for _, flag in prompts])
        self.assertGreater(total_after_first, 0)
        # run 2: meter restarted -> the whole sequence is a replay pass
        total_after_second = run_pass(total_after_first, [False, False])
        self.assertEqual(total_after_second, total_after_first)

    def test_replay_pass_never_updates_baseline(self):
        decision = meter_runtime.prompt_recording_decision(False, False, 0)
        self.assertFalse(decision["update_baseline"])
        self.assertFalse(decision["record_saved"])
        decision = meter_runtime.prompt_recording_decision(True, True, 500)
        self.assertTrue(decision["update_baseline"])
        self.assertTrue(decision["record_saved"])
        # live but unproven prompts still may feed the baseline, never the counter
        decision = meter_runtime.prompt_recording_decision(True, False, 0)
        self.assertTrue(decision["update_baseline"])
        self.assertFalse(decision["record_saved"])

    def test_per_model_meter_pricing(self):
        # KNOWN_ISSUES #7: identical token counts must price differently per model.
        rates = {
            "opus":   {"in": 15.0, "cw": 18.75, "cr": 1.50, "out": 75.0},
            "sonnet": {"in": 3.0,  "cw": 3.75,  "cr": 0.30, "out": 15.0},
            "haiku":  {"in": 0.80, "cw": 1.00,  "cr": 0.08, "out": 4.0},
            "other":  {"in": 3.0,  "cw": 3.75,  "cr": 0.30, "out": 15.0},
        }
        self.assertEqual(meter_runtime.classify_claude_model("claude-opus-4-1"), "opus")
        self.assertEqual(meter_runtime.classify_claude_model("claude-3-5-haiku"), "haiku")
        self.assertEqual(meter_runtime.classify_claude_model("claude-sonnet-4-5"), "sonnet")
        self.assertEqual(meter_runtime.classify_claude_model("mystery-model"), "other")
        self.assertEqual(meter_runtime.classify_claude_model(None), "other")
        self.assertEqual(meter_runtime.prices_for_model("claude-opus-4-1", rates), rates["opus"])

        bucket = {"in": 1_000, "cr": 200_000, "cw": 5_000, "out": 2_000, "msgs": 2}
        state = {"n": 0, "reqs": 0, "tok": 0, "cost": 0.0, "opp": 0.0,
                 "opp_tok": 0, "realized": 0.0, "saved_tok": 0}

        def cost_for(model_id):
            summary = meter_runtime.claude_prompt_summary(
                dict(state), dict(bucket), base_cr=0, wired_now=False, fraction=0.5,
                prices=meter_runtime.prices_for_model(model_id, rates),
            )
            return summary["real_cost"], summary["cache_read_cost"]

        opus_cost, opus_cr = cost_for("claude-opus-4-1")
        sonnet_cost, sonnet_cr = cost_for("claude-sonnet-4-5")
        haiku_cost, haiku_cr = cost_for("claude-3-5-haiku")
        self.assertGreater(opus_cost, sonnet_cost)
        self.assertGreater(sonnet_cost, haiku_cost)
        self.assertAlmostEqual(opus_cr, 200_000 / 1e6 * 1.50)
        self.assertAlmostEqual(sonnet_cr, 200_000 / 1e6 * 0.30)
        self.assertAlmostEqual(haiku_cr, 200_000 / 1e6 * 0.08)

    def test_seed_baseline_if_missing_estimates_and_is_replaceable(self):
        updated, seeded = meter_runtime.seed_baseline_if_missing({}, "repo", 500_000)
        self.assertEqual(seeded, {"cr": 30_000.0, "n": 0, "estimated": True})
        self.assertIn("repo", updated)
        # small repos aren't capped at the 30k naive_per_q ceiling
        _, small = meter_runtime.seed_baseline_if_missing({}, "repo", 8_000)
        self.assertEqual(small["cr"], 8_000.0)
        # never overwrites an existing baseline (real or previously estimated)
        existing = {"repo": {"cr": 9_999.0, "n": 4}}
        same, none = meter_runtime.seed_baseline_if_missing(existing, "repo", 500_000)
        self.assertIsNone(none)
        self.assertIs(same, existing)
        # a real unwired sample (n=0) fully replaces the estimate, not averages it
        after_real = meter_runtime.claude_baseline_update(updated, "repo", False, 15000)[1]
        self.assertEqual(after_real["cr"], 15000)
        self.assertEqual(after_real["n"], 1)


if __name__ == "__main__":
    unittest.main()
