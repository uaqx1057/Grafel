import tempfile
import tempfile
import unittest
from pathlib import Path

from grafel_core import graphs, live, release
from tests.integration_harness import TempRepoHarness


class GrafelProductTests(unittest.TestCase):
    def test_watch_event_kind_classifies_lines(self):
        self.assertEqual(live.watch_event_kind(""), "empty")
        self.assertEqual(live.watch_event_kind("warning: skill is from graphify 0.9.3"), "noise")
        self.assertEqual(live.watch_event_kind("[graphify watch] Rebuilt: 2 nodes"), "rebuild")
        self.assertEqual(live.watch_event_kind("Traceback (most recent call last):"), "error")
        self.assertEqual(live.watch_event_kind("watching repo"), "info")

    def test_initial_meter_sessions_scopes_and_sorts(self):
        repo = r"C:\repo"
        claude_dir = r"C:\claude-dir"
        all_sessions = [
            {"dir": claude_dir, "file": "a.jsonl", "mtime": 2, "kind": "claude", "cwd": repo},
            {"dir": r"C:\other", "file": "b.jsonl", "mtime": 1, "kind": "claude", "cwd": r"C:\elsewhere"},
            {"dir": r"C:\copilot", "file": "c.jsonl", "mtime": 3, "kind": "copilot", "cwd": r"C:\elsewhere"},
            {"dir": r"C:\codex", "file": "d.jsonl", "mtime": 4, "kind": "codex", "cwd": repo},
        ]
        result = live.initial_meter_sessions(
            repo,
            "repo",
            lambda _repo, _parse: (None, [repo]),
            lambda _ws: [repo],
            lambda _folder: claude_dir,
            lambda _folders, _parse: list(all_sessions),
            lambda fp: repo if fp == "a.jsonl" else None,
        )
        self.assertEqual(result["scope_state"]["folders"], [repo])
        self.assertEqual([s["mtime"] for s in result["sessions"]], [4, 2])
        self.assertTrue(result["has_any"])
        self.assertEqual(len(result["all_sessions"]), 4)
        self.assertEqual(result["in_scope_count"], 2)
        self.assertEqual(result["out_of_scope_count"], 2)
        self.assertEqual(result["out_of_scope_counts"]["copilot"], 1)
        self.assertEqual(len(result["other_sessions"]), 2)

    def test_refresher_sessions_uses_scope(self):
        meter_scope = {
            "mode": "repo",
            "repo_norm": r"c:\repo",
            "repo_git": None,
            "scope": {r"c:\repo"},
            "dirs": {r"c:\claude-dir"},
            "git_roots": set(),
        }
        sessions = [
            {"dir": r"c:\claude-dir", "file": "a.jsonl", "mtime": 2, "cwd": r"c:\repo"},
            {"dir": r"c:\other", "file": "b.jsonl", "mtime": 1, "cwd": r"c:\elsewhere"},
            {"dir": r"c:\codex", "file": "c.jsonl", "mtime": 3, "kind": "codex", "cwd": r"c:\repo"},
        ]
        fresh = live.refresher_sessions(
            meter_scope,
            lambda _ws: [r"c:\repo"],
            lambda _folders, _parse: list(sessions),
            lambda fp: r"c:\repo" if fp == "b.jsonl" else None,
        )
        self.assertEqual(len(fresh["scoped"]), 2)
        self.assertEqual(len(fresh["other"]), 1)

    def test_dedupe_sessions_prefers_newest_per_kind_and_file(self):
        result = live.dedupe_sessions([
            {"dir": "a", "file": "same", "mtime": 1, "kind": "copilot"},
            {"dir": "b", "file": "same", "mtime": 5, "kind": "copilot"},
            {"dir": "c", "file": "same", "mtime": 2, "kind": "codex"},
        ])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["mtime"], 5)

    def test_dedupe_sessions_collapses_duplicate_copilot_storage_copies(self):
        result = live.dedupe_sessions([
            {"dir": r"C:\a", "file": r"C:\ws1\chatSessions\abc.jsonl", "mtime": 1, "kind": "copilot"},
            {"dir": r"C:\b", "file": r"C:\ws2\chatSessions\abc.jsonl", "mtime": 5, "kind": "copilot"},
            {"dir": r"C:\c", "file": r"C:\ws3\chatSessions\def.jsonl", "mtime": 3, "kind": "copilot"},
        ])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["file"], r"C:\ws2\chatSessions\abc.jsonl")

    def test_session_kind_counts_groups_known_types(self):
        counts = live.session_kind_counts([
            {"kind": "claude"},
            {"kind": "copilot"},
            {"kind": "codex"},
            {"kind": "weird"},
        ])
        self.assertEqual(counts["claude"], 1)
        self.assertEqual(counts["copilot"], 1)
        self.assertEqual(counts["codex"], 1)
        self.assertEqual(counts["other"], 1)

    def test_scope_level_distinguishes_repo_and_machine(self):
        scope = live.meter_scope_state(
            r"C:\repo",
            "repo",
            lambda _repo, _parse: (None, [r"C:\repo"]),
            lambda _ws: [r"C:\repo"],
            lambda _folder: r"C:\claude-dir",
        )
        self.assertEqual(
            live.session_scope_level(
                {"dir": r"C:\claude-dir", "file": "a", "cwd": r"C:\repo\sub"},
                scope,
                lambda _fp: None,
            ),
            "repo",
        )
        self.assertEqual(
            live.session_scope_level(
                {"dir": r"C:\else", "file": "b", "cwd": r"C:\else"},
                scope,
                lambda _fp: None,
            ),
            "machine",
        )

    def test_scope_details_include_hard_link_reason(self):
        scope = live.meter_scope_state(
            r"C:\repo",
            "repo",
            lambda _repo, _parse: (None, [r"C:\repo"]),
            lambda _ws: [r"C:\repo"],
            lambda _folder: r"C:\claude-dir",
        )
        detail = live.session_scope_details(
            {"dir": r"C:\claude-dir", "file": "a", "cwd": r"C:\repo\sub"},
            scope,
            lambda _fp: None,
        )
        self.assertEqual(detail["level"], "repo")
        self.assertTrue(detail["hard_link"])
        self.assertEqual(detail["attribution"], "confirmed")
        self.assertTrue(detail["reasons"])

    def test_scope_level_does_not_treat_parent_folder_as_repo_match(self):
        scope = live.meter_scope_state(
            r"C:\repo\child",
            "repo",
            lambda _repo, _parse: (None, [r"C:\repo\child"]),
            lambda _ws: [r"C:\repo\child"],
            lambda _folder: r"C:\claude-dir",
        )
        self.assertEqual(
            live.session_scope_level(
                {"dir": r"C:\else", "file": "b", "cwd": r"C:\repo"},
                scope,
                lambda _fp: None,
            ),
            "machine",
        )

    def test_scope_dir_match_requires_unknown_cwd(self):
        # KNOWN_ISSUES #9: claude_log_dir's encoding collides for similarly
        # named repos (C:\repo-x and C:\repo_x share a log-dir name). A session
        # whose REAL cwd resolves to a different repo must not be pulled into
        # scope just because the encoded directory name matches.
        scope = live.meter_scope_state(
            r"C:\repo-x",
            "repo",
            lambda _repo, _parse: (None, [r"C:\repo-x"]),
            lambda _ws: [r"C:\repo-x"],
            lambda _folder: r"C:\claude\c--repo-x",
        )
        colliding = {"dir": r"C:\claude\c--repo-x", "file": "a", "cwd": r"C:\repo_x"}
        self.assertEqual(
            live.session_scope_level(colliding, scope, lambda _fp: None),
            "machine",
        )
        # when no cwd is resolvable at all, the dir-name evidence still counts
        unknown_cwd = {"dir": r"C:\claude\c--repo-x", "file": "b"}
        self.assertEqual(
            live.session_scope_level(unknown_cwd, scope, lambda _fp: None),
            "workspace",
        )

    def test_repo_live_session_health_counts_linked_sessions(self):
        repo = r"C:\repo"
        claude_dir = r"C:\claude-dir"
        sessions = [
            {"dir": claude_dir, "file": "a.jsonl", "mtime": 2, "kind": "claude", "cwd": repo},
            {"dir": r"C:\codex", "file": "b.jsonl", "mtime": 3, "kind": "codex", "cwd": repo},
            {"dir": r"C:\else", "file": "c.jsonl", "mtime": 1, "kind": "copilot", "cwd": r"C:\else"},
        ]
        health = live.repo_live_session_health(
            repo,
            lambda _repo, _parse: (None, [repo]),
            lambda _ws: [repo],
            lambda _folder: claude_dir,
            lambda _folders, _parse: list(sessions),
            lambda _fp: None,
        )
        self.assertEqual(health["linked_count"], 2)
        self.assertEqual(health["machine_count"], 3)
        self.assertEqual(health["other_count"], 1)
        self.assertEqual(health["linked_counts"]["claude"], 1)
        self.assertEqual(health["linked_counts"]["codex"], 1)

    def test_repo_install_health_detects_graph_routing_and_brevity(self):
        harness = TempRepoHarness()
        try:
            (harness.root / "graphify-out").mkdir(exist_ok=True)
            (harness.root / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
            (harness.root / "CLAUDE.md").write_text(
                "<!-- graphify-tool:routing:start -->\n"
                "routing\n"
                "<!-- graphify-tool:routing:end -->\n"
                "<!-- grafel-brevity:start -->\n"
                "brevity\n"
                "<!-- grafel-brevity:end -->\n",
                encoding="utf-8",
            )
            health = graphs.repo_install_health(
                str(harness.root),
                "<!-- graphify-tool:routing:start -->",
                "<!-- grafel-brevity:start -->",
            )
            self.assertTrue(health["graph_built"])
            self.assertTrue(health["routing_installed"])
            self.assertTrue(health["brevity_installed"])
        finally:
            harness.close()

    def test_read_app_version_and_installer_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            grafel_py = Path(tmp) / "grafel.py"
            grafel_py.write_text('APP_VERSION = "2.3.4"\n', encoding="utf-8")
            version = release.read_app_version(str(grafel_py))
            self.assertEqual(version, "2.3.4")
            cmd = release.build_installer_command("C:\\ISCC.exe", "installer.iss", "C:\\out", version)
            self.assertIn("/DAppVersion=2.3.4", cmd)

    def test_release_preflight_and_harness(self):
        harness = TempRepoHarness()
        try:
            grafel_py = harness.root / "grafel.py"
            spec = harness.root / "Grafel.spec"
            installer = harness.root / "installer.iss"
            grafel_py.write_text('APP_VERSION = "1.2.3"\n', encoding="utf-8")
            spec.write_text("spec", encoding="utf-8")
            installer.write_text("iss", encoding="utf-8")
            preflight = release.release_preflight(
                repo_root=str(harness.root),
                grafel_py_path=str(grafel_py),
                spec_path=str(spec),
                installer_script=str(installer),
                iscc_path=None,
                output_dir=str(harness.root / "out"),
                require_inno=False,
            )
            self.assertTrue(preflight["ok"])
            self.assertEqual(preflight["version"], "1.2.3")
        finally:
            harness.close()


if __name__ == "__main__":
    unittest.main()
