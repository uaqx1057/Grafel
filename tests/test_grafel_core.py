import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from grafel_core import savings, sessions
from grafel_core import chat_export, config
from grafel_core import graphs, optimizer, proof, workspace
from grafel_core import strict_mcp
from grafel_core.strict_mcp import StrictGateway


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("grafel_module", ROOT / "grafel.py")
grafel = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(grafel)


class GrafelCoreTests(unittest.TestCase):
    def test_fmt_tokens_ranges(self):
        self.assertEqual(grafel.fmt_tokens(999), "999")
        self.assertEqual(grafel.fmt_tokens(12_345), "12.3k")
        self.assertEqual(grafel.fmt_tokens(1_250_000), "1.2M")

    def test_human_ago_labels(self):
        self.assertEqual(grafel._human_ago(10), "just now")
        self.assertEqual(grafel._human_ago(120), "2m ago")
        self.assertEqual(grafel._human_ago(7_200), "2h ago")
        self.assertEqual(grafel._human_ago(172_800), "2d ago")

    def test_write_routing_block_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "AGENTS.md"
            path.write_text("Header\n", encoding="utf-8")
            config.write_routing_block(str(path))
            once = path.read_text(encoding="utf-8")
            config.write_routing_block(str(path))
            twice = path.read_text(encoding="utf-8")
            self.assertEqual(once, twice)
            self.assertIn(config.ROUTING_START, twice)
            self.assertIn(config.ROUTING_END, twice)

    def test_build_routing_block_includes_required_policy(self):
        block = config.build_routing_block("required_alerts")
        self.assertIn("Strict mode: Required + Violation Alerts", block)
        self.assertIn("MUST first run `graphify-out\\grafel-query.cmd", block)
        self.assertIn("Treat any bypass", block)

    def test_merge_json_servers_preserves_existing_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(
                json.dumps({"servers": {"existing": {"type": "http", "url": "https://example"}}}),
                encoding="utf-8",
            )
            config.merge_json_servers(
                str(path),
                "servers",
                {"context7": {"type": "http", "url": "https://mcp.context7.com/mcp"}},
                lambda *_args, **_kwargs: None,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("existing", payload["servers"])
            self.assertIn("context7", payload["servers"])

    def test_merge_json_servers_updates_changed_entries(self):
        # KNOWN_ISSUES #9: a stale managed entry (old exe path, moved repo)
        # must be refreshed, while unmanaged entries stay untouched and an
        # identical merge stays idempotent.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(
                json.dumps({"servers": {
                    "grafel-strict": {"type": "stdio", "command": r"C:\old\grafel-mcp.cmd", "args": []},
                    "custom": {"type": "http", "url": "https://example"},
                }}),
                encoding="utf-8",
            )
            logs = []
            fresh = {"grafel-strict": {"type": "stdio", "command": r"D:\new\grafel-mcp.cmd", "args": []}}
            config.merge_json_servers(str(path), "servers", fresh, logs.append)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["servers"]["grafel-strict"]["command"], r"D:\new\grafel-mcp.cmd")
            self.assertEqual(payload["servers"]["custom"], {"type": "http", "url": "https://example"})
            self.assertTrue(any("updated grafel-strict" in line for line in logs))
            # identical merge: no rewrite, reported as already configured
            before = path.read_text(encoding="utf-8")
            logs.clear()
            config.merge_json_servers(str(path), "servers", fresh, logs.append)
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertTrue(any("already configured" in line for line in logs))

    def test_write_routing_block_recovers_orphaned_start_marker(self):
        # KNOWN_ISSUES #9: START without END (crash mid-write / manual edit)
        # used to get a second block appended; the NEXT run's START..END regex
        # then greedily swallowed everything in between. The writer must
        # recover the unterminated block explicitly and preserve content above.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CLAUDE.md"
            path.write_text(
                "# My notes\nimportant user content\n\n"
                + config.ROUTING_START
                + "\n## Tool routing (token efficiency)\nhalf-written blo",
                encoding="utf-8",
            )
            logs = []
            config.write_routing_block(str(path), logs.append)
            once = path.read_text(encoding="utf-8")
            self.assertIn("important user content", once)
            self.assertEqual(once.count(config.ROUTING_START), 1)
            self.assertEqual(once.count(config.ROUTING_END), 1)
            self.assertNotIn("half-written blo", once)
            self.assertTrue(any("recovered" in line for line in logs))
            # a second run must be a no-op (no greedy deletion, no growth)
            config.write_routing_block(str(path), logs.append)
            self.assertEqual(path.read_text(encoding="utf-8"), once)

    def test_question_match_stats_counts_matching_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("def login_user():\n    return True\n", encoding="utf-8")
            (root / "b.py").write_text("def other():\n    return False\n", encoding="utf-8")
            stats = savings.question_match_stats(
                str(root),
                "how does login work?",
                {".py"},
                set(),
                token_counter=lambda text: (len(text), True),
            )
            self.assertEqual(stats["matched"], 1)
            self.assertGreater(stats["tokens"], 0)

    def test_question_keywords_drop_stopwords(self):
        # "does"/"work" appear in nearly every source file; they must not count
        # as keywords (KNOWN_ISSUES #8).
        self.assertEqual(savings.question_keywords("how does authentication work?"),
                         ["authentication"])
        self.assertEqual(savings.question_keywords("what would this need?"), [])

    def test_question_match_stats_ignores_stopword_only_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "auth.py").write_text(
                "def authentication_flow():\n    # does the login work here\n    return True\n",
                encoding="utf-8",
            )
            # files full of question stopwords but no real keyword
            (root / "a.py").write_text("# this does work with that\nx = 1\n", encoding="utf-8")
            (root / "b.py").write_text("# it will work from here\ny = 2\n", encoding="utf-8")
            stats = savings.question_match_stats(
                str(root),
                "how does authentication work?",
                {".py"},
                set(),
                token_counter=lambda text: (len(text), True),
            )
            self.assertEqual(stats["matched"], 1)

    def test_question_match_stats_requires_two_distinct_keyword_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "both.py").write_text("token = authentication()\n", encoding="utf-8")
            (root / "one.py").write_text("token = None\n", encoding="utf-8")
            (root / "none.py").write_text("x = 1\n", encoding="utf-8")
            stats = savings.question_match_stats(
                str(root),
                "authentication token flow",
                {".py"},
                set(),
                token_counter=lambda text: (len(text), True),
            )
            # only the file hitting >=2 distinct keywords counts
            self.assertEqual(stats["matched"], 1)
        # single-keyword questions still match on that one keyword
        self.assertTrue(savings.question_file_matches(["login"], "def login(): pass"))
        self.assertFalse(savings.question_file_matches(["login"], "def other(): pass"))
        # no usable keywords keeps the match-everything upper bound
        self.assertTrue(savings.question_file_matches([], "anything"))

    def test_repo_token_stats_skips_filtered_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.py").write_text("print('ok')\n", encoding="utf-8")
            skip = root / "node_modules"
            skip.mkdir()
            (skip / "ignored.py").write_text("print('ignore')\n", encoding="utf-8")
            stats = savings.repo_token_stats(
                str(root),
                {".py"},
                {"node_modules"},
                token_counter=lambda text: (len(text), True),
            )
            self.assertEqual(stats["files"], 1)

    def test_parse_claude_jsonl_chunk_dedupes_assistant_usage(self):
        chunk = "\n".join([
            json.dumps({"type": "user", "message": {"role": "user", "content": "help"}}),
            json.dumps({"message": {"role": "assistant", "id": "a1", "usage": {
                "input_tokens": 10, "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 5, "output_tokens": 7,
            }}}),
            json.dumps({"message": {"role": "assistant", "id": "a1", "usage": {
                "input_tokens": 10, "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 5, "output_tokens": 7,
            }}}),
        ])
        events, seen = sessions.parse_claude_jsonl_chunk(chunk, set())
        self.assertEqual(len(seen), 1)
        self.assertEqual(sum(1 for kind, _ in events if kind == "assistant_usage"), 1)
        self.assertEqual(events[0][0], "user")

    def test_accumulate_usage_bucket_sums_usage(self):
        bucket = sessions.accumulate_usage_bucket(None, {
            "input_tokens": 10,
            "cache_read_input_tokens": 20,
            "cache_creation_input_tokens": 5,
            "output_tokens": 7,
        })
        bucket = sessions.accumulate_usage_bucket(bucket, {
            "input_tokens": 2,
            "cache_read_input_tokens": 3,
            "cache_creation_input_tokens": 1,
            "output_tokens": 4,
        })
        self.assertEqual(bucket, {"in": 12, "cr": 23, "cw": 6, "out": 11, "msgs": 2})

    def test_codex_session_helpers_read_meta_and_token_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            path.write_text(
                "\n".join([
                    json.dumps({
                        "type": "session_meta",
                        "payload": {
                            "session_id": "abc12345",
                            "cwd": r"C:\repo",
                            "originator": "Codex Desktop",
                            "source": "vscode",
                        },
                    }),
                    json.dumps({
                        "type": "token_count",
                        "payload": {
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 10,
                                    "cached_input_tokens": 20,
                                    "output_tokens": 30,
                                    "reasoning_output_tokens": 40,
                                    "total_tokens": 100,
                                },
                                "last_token_usage": {
                                    "input_tokens": 1,
                                    "cached_input_tokens": 2,
                                    "output_tokens": 3,
                                    "reasoning_output_tokens": 4,
                                    "total_tokens": 10,
                                },
                            },
                        },
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            meta = sessions.codex_session_meta(str(path))
            self.assertEqual(meta["cwd"], r"C:\repo")
            self.assertEqual(sessions.codex_session_cwd_fast(str(path)), r"C:\repo")
            events, pos = sessions.iter_codex_token_counts(str(path), 0)
            self.assertEqual(pos, path.stat().st_size)
            self.assertEqual(events[0]["total"]["all"], 100)
            self.assertEqual(events[0]["last"]["reasoning"], 4)

    def test_read_complete_lines_does_not_consume_partial_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tail.jsonl"
            line = json.dumps({"type": "token_count", "n": 1}).encode("utf-8") + b"\n"
            split = len(line) // 2
            # Write 1: the poller fires while the writer is mid-line.
            path.write_bytes(line[:split])
            text, pos = sessions.read_complete_lines(str(path), 0)
            self.assertEqual(text, "")
            self.assertEqual(pos, 0)  # nothing consumed — partial line left alone
            # Write 2: the writer finishes the line; next poll sees it whole.
            with open(path, "ab") as f:
                f.write(line[split:])
            text, pos = sessions.read_complete_lines(str(path), pos)
            self.assertEqual(pos, path.stat().st_size)
            self.assertEqual(json.loads(text), {"type": "token_count", "n": 1})

    def test_read_complete_lines_resets_after_file_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tail.jsonl"
            path.write_bytes(b'{"a": 1}\n{"b": 2}\n')
            text, pos = sessions.read_complete_lines(str(path), 0)
            self.assertEqual(pos, path.stat().st_size)
            # File rewritten shorter (VS Code window reload): must reset,
            # not seek past EOF and return "" forever.
            path.write_bytes(b'{"c": 3}\n')
            text, pos = sessions.read_complete_lines(str(path), pos)
            self.assertEqual(json.loads(text), {"c": 3})
            self.assertEqual(pos, path.stat().st_size)

    def test_claude_tail_partial_write_counts_event_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            line = json.dumps({"message": {"role": "assistant", "id": "a1", "usage": {
                "input_tokens": 10, "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 5, "output_tokens": 7,
            }}}).encode("utf-8") + b"\n"
            seen = set()
            counted = []
            # Poll 1 lands mid-write: zero complete lines, zero bytes consumed.
            path.write_bytes(line[: len(line) // 2])
            chunk, pos = sessions.read_complete_lines(str(path), 0)
            events, seen = sessions.parse_claude_jsonl_chunk(chunk, seen)
            counted.extend(events)
            self.assertEqual(pos, 0)
            self.assertEqual(counted, [])
            # Writer finishes the line; poll 2 re-reads it complete from the start.
            with open(path, "ab") as f:
                f.write(line[len(line) // 2:])
            chunk, pos = sessions.read_complete_lines(str(path), pos)
            events, seen = sessions.parse_claude_jsonl_chunk(chunk, seen)
            counted.extend(events)
            # Poll 3: nothing new — no duplicate.
            chunk, pos = sessions.read_complete_lines(str(path), pos)
            events, seen = sessions.parse_claude_jsonl_chunk(chunk, seen)
            counted.extend(events)
            usages = [p for kind, p in counted if kind == "assistant_usage"]
            self.assertEqual(len(usages), 1)
            self.assertEqual(usages[0]["cache_read_input_tokens"], 20)
            self.assertEqual(usages[0]["output_tokens"], 7)

    def test_iter_vscode_chat_events_survives_partial_write_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat.jsonl"
            line = json.dumps({
                "kind": 1, "k": ["requests", 0, "promptTokens"], "v": 123,
            }).encode("utf-8") + b"\n"
            # Partial write: no events, position untouched.
            path.write_bytes(line[: len(line) // 2])
            events, pos = sessions.iter_vscode_chat_events(str(path), 0)
            self.assertEqual(events, [])
            self.assertEqual(pos, 0)
            # Line completed: exactly one correctly parsed event.
            with open(path, "ab") as f:
                f.write(line[len(line) // 2:])
            events, pos = sessions.iter_vscode_chat_events(str(path), pos)
            self.assertEqual(events, [("usage", 0, "promptTokens", 123)])
            self.assertEqual(pos, path.stat().st_size)
            # VS Code rewrites the file shorter: reader resets instead of
            # returning [] forever from a position past EOF.
            shorter = b'{"kind":1,"k":["requests",0,"copilotCredits"],"v":1}\n'
            self.assertLess(len(shorter), pos)
            path.write_bytes(shorter)
            events, pos = sessions.iter_vscode_chat_events(str(path), pos)
            self.assertEqual(events, [("usage", 0, "copilotCredits", 1)])
            self.assertEqual(pos, path.stat().st_size)

    def test_scan_claude_usage_dedupes_across_resumed_session_files(self):
        # KNOWN_ISSUES #9: a resumed session's new .jsonl replays the prior
        # transcript — the same message id across old + new files must count once.
        def usage_line(mid):
            return json.dumps({"message": {"role": "assistant", "id": mid, "usage": {
                "input_tokens": 10, "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 5, "output_tokens": 7,
            }, "model": "claude-sonnet-4-5"}})

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "c--repo"
            proj.mkdir()
            (proj / "old.jsonl").write_text(usage_line("m1") + "\n", encoding="utf-8")
            (proj / "resumed.jsonl").write_text(
                usage_line("m1") + "\n" + usage_line("m2") + "\n", encoding="utf-8"
            )
            data = sessions.scan_claude_usage(tmp)
            self.assertEqual(data["responses"], 2)  # m1 counted once, not twice
            self.assertEqual(data["totals"]["in"], 20)
            self.assertEqual(data["totals"]["cr"], 40)

    def test_session_cwd_fast_falls_back_when_tail_is_swamped(self):
        # KNOWN_ISSUES #9: one huge tool-output line near EOF can push every
        # "cwd" record out of the 64KB tail window — the fast path must fall
        # back to the full scan instead of misclassifying the session.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            huge = json.dumps({"type": "tool_result", "data": "A" * 80_000})
            path.write_text(
                json.dumps({"type": "user", "cwd": r"C:\repo"}) + "\n" + huge + "\n",
                encoding="utf-8",
            )
            self.assertEqual(sessions.session_cwd_fast(str(path)), r"C:\repo")
            # opt-out keeps the old fast-only, may-miss semantics
            self.assertIsNone(sessions.session_cwd_fast(str(path), fallback=False))
            # small files (tail == whole file) never trigger the extra scan
            small = Path(tmp) / "small.jsonl"
            small.write_text(json.dumps({"cwd": r"C:\small"}) + "\n", encoding="utf-8")
            self.assertEqual(sessions.session_cwd_fast(str(small)), r"C:\small")

    def test_session_catalog_and_ai_session_enrichment(self):
        catalog = sessions.session_detector_catalog()
        tools = {item["tool"] for item in catalog}
        self.assertIn("claude", tools)
        self.assertIn("cursor", tools)
        enriched = sessions.enrich_session(
            {"dir": "d", "file": "f", "mtime": 50, "cwd": r"C:\repo"},
            "codex",
            "Codex",
            now=100,
        )
        self.assertEqual(enriched["tool"], "codex")
        self.assertEqual(enriched["age"], 50)

    def test_session_graph_usage_detects_graphify_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text(
                '{"text":"Please run graphify query \\"auth flow\\" against graphify-out/graph.json"}\n',
                encoding="utf-8",
            )
            usage = sessions.session_graph_usage(str(path))
            self.assertTrue(usage["detected"])
            self.assertIn("graphify query", usage["matches"])

    def test_session_bypass_risk_detects_broad_exploration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text(
                '{"text":"run Get-ChildItem -Recurse then rg --files before reading files"}\n',
                encoding="utf-8",
            )
            risk = sessions.session_bypass_risk(str(path))
            self.assertTrue(risk["detected"])
            self.assertIn("get-childitem -recurse", risk["matches"])

    def test_graph_use_proof_log_records_and_summarizes_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            proof.append_graph_use_event(
                tmp,
                source="ask_graph",
                command="query",
                argv=["auth flow"],
                cwd=tmp,
                tokens=123,
                success=True,
            )
            events = proof.read_graph_use_events(tmp)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["source"], "ask_graph")
            summary = proof.graph_use_summary(tmp)
            self.assertEqual(summary["successful_events"], 1)
            self.assertEqual(summary["recent_successful_events"], 1)

    def test_strict_gateway_blocks_raw_reads_until_graph_query_allows_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = root / "allowed.py"
            blocked = root / "blocked.py"
            allowed.write_text("def allowed():\n    return True\n", encoding="utf-8")
            blocked.write_text("def blocked():\n    return False\n", encoding="utf-8")
            script = root / "fake_graphify.py"
            script.write_text(
                "import sys\n"
                "print('NODE allowed.py [src=allowed.py loc=L1]')\n",
                encoding="utf-8",
            )
            gateway = StrictGateway(str(root), [sys.executable, str(script)])
            with self.assertRaises(PermissionError):
                gateway.read_file("allowed.py")
            result = gateway.graph_command("query", ["what is allowed?"])
            self.assertEqual(result["code"], 0)
            self.assertIn("def allowed", gateway.read_file("allowed.py"))
            self.assertIn("allowed.py", gateway.allowed_files_list())
            self.assertIn("return True", gateway.search_allowed("return true"))
            self.assertIn("File: allowed.py", gateway.file_summary("allowed.py"))
            with self.assertRaises(PermissionError):
                gateway.read_file("blocked.py")

    def test_source_files_from_graph_output_accepts_quoted_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spaced_dir = root / "My Docs"
            spaced_dir.mkdir()
            spaced = spaced_dir / "auth flow.py"
            spaced.write_text("def auth():\n    return True\n", encoding="utf-8")
            plain = root / "plain.py"
            plain.write_text("def plain():\n    return 1\n", encoding="utf-8")
            text = (
                f'NODE auth [src="{spaced}" loc=L1]\n'
                "NODE plain [src=plain.py loc=L1]\n"
            )
            files = strict_mcp.source_files_from_graph_output(str(root), text)
            self.assertIn(os.path.normcase(os.path.realpath(str(spaced))), files)
            self.assertIn(os.path.normcase(os.path.realpath(str(plain))), files)

    def test_strict_gateway_allowlist_ages_out_old_query_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            window = strict_mcp.ALLOWLIST_RESULT_WINDOW
            names = [f"file{i}.py" for i in range(window + 1)]
            for name in names:
                (root / name).write_text(f"# {name}\n", encoding="utf-8")
            script = root / "fake_graphify.py"
            # Echoes the queried filename back as a src= attribute.
            script.write_text(
                "import sys\n"
                "q = sys.argv[2]\n"
                "print(f'NODE {q} [src={q} loc=L1]')\n",
                encoding="utf-8",
            )
            gateway = StrictGateway(str(root), [sys.executable, str(script)])
            for name in names:
                result = gateway.graph_command("query", [name])
                self.assertEqual(result["code"], 0)
            # The oldest grant fell out of the sliding window...
            with self.assertRaises(PermissionError):
                gateway.read_file(names[0])
            # ...while every result still inside the window stays readable.
            for name in names[1:]:
                self.assertIn(name, gateway.read_file(name))

    def test_parse_workspace_folders_handles_jsonc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one").mkdir()
            (root / "two").mkdir()
            ws = root / "demo.code-workspace"
            ws.write_text(
                '{\n'
                '  // comment\n'
                '  "folders": [\n'
                '    {"path": "one"},\n'
                '    {"path": "two"},\n'
                '  ],\n'
                '}\n',
                encoding="utf-8",
            )
            folders = config.parse_workspace_folders(str(ws))
            self.assertEqual(folders, [str(root / "one"), str(root / "two")])

    def test_claude_exchanges_groups_prompt_response_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claude.jsonl"
            path.write_text(
                "\n".join([
                    json.dumps({"type": "user", "message": {"role": "user", "content": "Explain login"}}),
                    json.dumps({"message": {"role": "assistant", "id": "m1", "usage": {
                        "input_tokens": 10, "cache_read_input_tokens": 5,
                        "cache_creation_input_tokens": 2, "output_tokens": 3,
                    }, "content": [{"type": "text", "text": "Use the auth service."}]}}),
                ]),
                encoding="utf-8",
            )
            exchanges = chat_export.claude_exchanges(str(path))
            self.assertEqual(
                exchanges,
                [("Explain login", "Use the auth service.", "~20 tokens")],
            )

    def test_copilot_exchanges_collects_responses_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.jsonl"
            path.write_text(
                "\n".join([
                    json.dumps({"kind": 0, "v": {"requests": [{
                        "message": {"text": "Find auth flow"},
                        "response": [{"kind": "markdownContent", "value": "Look in auth.py"}],
                    }]}}),
                    json.dumps({"kind": 1, "k": ["requests", 0, "promptTokens"], "v": 12}),
                    json.dumps({"kind": 1, "k": ["requests", 0, "completionTokens"], "v": 8}),
                    json.dumps({"kind": 1, "k": ["requests", 0, "copilotCredits"], "v": 0.5}),
                ]),
                encoding="utf-8",
            )
            exchanges = chat_export.copilot_exchanges(str(path))
            self.assertEqual(
                exchanges,
                [("Find auth flow", "Look in auth.py", "tokens: prompt 12 | completion 8 | credits: 0.50")],
            )

    def test_graph_artifact_state_marks_stale_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "graphify-out"
            out.mkdir()
            graph = out / "graph.json"
            report = out / "GRAPH_REPORT.md"
            graph.write_text("{}", encoding="utf-8")
            report.write_text("# report", encoding="utf-8")
            code = root / "app.py"
            code.write_text("print('newer')\n", encoding="utf-8")
            now = 2_000_000_000
            older = now - 100
            newer = now
            import os
            os.utime(graph, (older, older))
            os.utime(report, (older, older))
            os.utime(code, (newer, newer))
            state = graphs.graph_artifact_state(str(root), {".py"}, {"graphify-out"})
            self.assertTrue(state["graph_exists"])
            self.assertTrue(state["graph_stale"])
            self.assertTrue(state["report_stale"])

    def test_diff_graph_snapshot_reports_added_and_removed_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph = root / "graph.json"
            snap = root / "snap.json"
            snap.write_text(json.dumps({"nodes": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8")
            graph.write_text(json.dumps({"nodes": [{"id": "b"}, {"id": "c"}]}), encoding="utf-8")
            diff = graphs.diff_graph_snapshot(str(graph), str(snap))
            self.assertFalse(diff["baseline"])
            self.assertEqual(diff["added"], ["c"])
            self.assertEqual(diff["removed"], ["a"])
            self.assertTrue(diff["snapshot_updated"])

    def test_build_optimizer_plan_recommends_setup_and_codex(self):
        plan = optimizer.build_optimizer_plan(
            claude_usage=None,
            codex_usage={"reasoning": 2000, "output": 100, "total": 2100},
            copilot_usage=None,
            repo_has_graph=False,
            claude_rates={
                "opus": {"in": 15.0, "cw": 18.75, "cr": 1.50, "out": 75.0},
                "sonnet": {"in": 3.0, "cw": 3.75, "cr": 0.30, "out": 15.0},
                "haiku": {"in": 0.80, "cw": 1.00, "cr": 0.08, "out": 4.0},
                "other": {"in": 3.0, "cw": 3.75, "cr": 0.30, "out": 15.0},
            },
            query_tokens=2000,
        )
        tags = [rec["tag"] for rec in plan["recommendations"]]
        self.assertIn("SETUP", tags)
        self.assertIn("CODEX", tags)

    def test_find_workspace_for_detects_matching_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            ws = root / "demo.code-workspace"
            ws.write_text('{"folders":[{"path":"repo"}]}', encoding="utf-8")
            found, folders = workspace.find_workspace_for(
                str(repo),
                lambda ws_path: [str(repo)] if Path(ws_path).name == "demo.code-workspace" else [],
                extra_roots=[str(root)],
            )
            self.assertTrue(found.endswith("demo.code-workspace"))
            self.assertEqual(folders, [str(repo)])

    def test_save_config_round_trips_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "grafel.json")
            workspace.save_config(path, {"stats": {"saved_tokens": 7}, "seen": True})
            self.assertEqual(
                workspace.load_config(path),
                {"stats": {"saved_tokens": 7}, "seen": True},
            )
            workspace.save_config(path, {"stats": {"saved_tokens": 8}})
            self.assertEqual(workspace.load_config(path), {"stats": {"saved_tokens": 8}})
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name != "grafel.json"]
            self.assertEqual(leftovers, [])

    def test_save_config_failed_write_keeps_original_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "grafel.json")
            workspace.save_config(path, {"license": "abc", "events": 3})
            original = Path(path).read_text(encoding="utf-8")
            # a non-serializable cfg fails mid-dump — the target file must be
            # untouched (write went to a temp file) and the temp cleaned up
            with self.assertRaises(TypeError):
                workspace.save_config(path, {"bad": object()})
            self.assertEqual(Path(path).read_text(encoding="utf-8"), original)
            self.assertEqual(workspace.load_config(path), {"license": "abc", "events": 3})
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name != "grafel.json"]
            self.assertEqual(leftovers, [])

    def test_save_config_concurrent_writers_never_corrupt_file(self):
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "grafel.json")
            payloads = [{"writer": i, "blob": "x" * 2000} for i in range(4)]

            def hammer(payload):
                for _ in range(25):
                    workspace.save_config(path, payload)

            threads = [threading.Thread(target=hammer, args=(p,)) for p in payloads]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            # atomic replace: file is always one writer's complete payload
            final = workspace.load_config(path)
            self.assertIn(final, payloads)


if __name__ == "__main__":
    unittest.main()
