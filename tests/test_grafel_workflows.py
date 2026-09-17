import json
import tempfile
import unittest
from pathlib import Path

from grafel_core import brevity, config, workflows


class GrafelWorkflowTests(unittest.TestCase):
    def test_ensure_gitignore_entry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            logs = []
            added = workflows.ensure_gitignore_entry(str(root), "graphify-out", logs.append)
            added_again = workflows.ensure_gitignore_entry(str(root), "graphify-out", logs.append)
            self.assertTrue(added)
            self.assertFalse(added_again)
            self.assertIn("graphify-out/", (root / ".gitignore").read_text(encoding="utf-8"))
            # KNOWN_ISSUES #9: chat digests contain full chat text (pasted
            # secrets included) — grafel-chats/ must be ignorable the same way
            # and coexist with the graph entry.
            self.assertTrue(workflows.ensure_gitignore_entry(str(root), "grafel-chats", logs.append))
            self.assertFalse(workflows.ensure_gitignore_entry(str(root), "grafel-chats", logs.append))
            text = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("graphify-out/", text)
            self.assertIn("grafel-chats/", text)

    def test_install_repo_mcp_writes_local_configs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = []
            result = workflows.install_repo_mcp(str(root), config.merge_json_servers, logs.append)
            vscode = Path(result["vscode"])
            claude = Path(result["claude"])
            self.assertTrue(vscode.exists())
            self.assertTrue(claude.exists())
            vscode_servers = json.loads(vscode.read_text(encoding="utf-8"))["servers"]
            claude_servers = json.loads(claude.read_text(encoding="utf-8"))["mcpServers"]
            self.assertIn("context7", vscode_servers)
            self.assertIn("grafel-strict", vscode_servers)
            self.assertIn("grafel-strict", claude_servers)
            # .vscode/mcp.json is committed to git: use VS Code's documented
            # ${workspaceFolder} variable, not a machine-absolute path
            self.assertEqual(
                vscode_servers["grafel-strict"]["command"],
                "${workspaceFolder}/graphify-out/grafel-mcp.cmd",
            )
            # .mcp.json (Claude Code) keeps the absolute path; a stale one is
            # refreshed by merge_json_servers on the next run
            self.assertTrue(claude_servers["grafel-strict"]["command"].endswith("grafel-mcp.cmd"))
            # Default strict mode (required_alerts) must NOT ship the
            # unrestricted filesystem bypass alongside grafel-strict.
            self.assertNotIn("filesystem", vscode_servers)
            self.assertNotIn("filesystem", claude_servers)
            self.assertTrue((root / "graphify-out" / "grafel-mcp.cmd").exists())

    def test_install_repo_mcp_strict_modes_skip_filesystem_server(self):
        for mode in ("required", "required_alerts"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                logs = []
                result = workflows.install_repo_mcp(
                    str(root), config.merge_json_servers, logs.append, strict_mode=mode
                )
                vscode_servers = json.loads(
                    Path(result["vscode"]).read_text(encoding="utf-8")
                )["servers"]
                claude_servers = json.loads(
                    Path(result["claude"]).read_text(encoding="utf-8")
                )["mcpServers"]
                self.assertNotIn("filesystem", vscode_servers, mode)
                self.assertNotIn("filesystem", claude_servers, mode)
                self.assertIn("grafel-strict", vscode_servers, mode)
                self.assertIn("grafel-strict", claude_servers, mode)
                self.assertTrue(any("filesystem MCP server skipped" in line for line in logs))

    def test_install_repo_mcp_advisory_mode_keeps_filesystem_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = []
            result = workflows.install_repo_mcp(
                str(root), config.merge_json_servers, logs.append, strict_mode="advisory"
            )
            vscode_servers = json.loads(
                Path(result["vscode"]).read_text(encoding="utf-8")
            )["servers"]
            claude_servers = json.loads(
                Path(result["claude"]).read_text(encoding="utf-8")
            )["mcpServers"]
            self.assertIn("filesystem", vscode_servers)
            self.assertIn("filesystem", claude_servers)
            self.assertIn(str(root), claude_servers["filesystem"]["args"])
            self.assertIn("grafel-strict", claude_servers)

    def test_write_repo_routing_creates_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = []
            targets = workflows.write_repo_routing(str(root), config.write_routing_block, logs.append, "required")
            self.assertEqual(len(targets), 3)
            self.assertTrue((root / "graphify-out" / "grafel-query.cmd").exists())
            self.assertTrue((root / "graphify-out" / "grafel-path.cmd").exists())
            self.assertTrue((root / "graphify-out" / "grafel-explain.cmd").exists())
            self.assertTrue((root / "graphify-out" / "grafel-save-result.cmd").exists())
            self.assertTrue((root / "graphify-out" / "grafel-mcp.cmd").exists())
            for target in targets:
                text = Path(target).read_text(encoding="utf-8")
                self.assertIn(config.ROUTING_START, text)
                self.assertIn(config.ROUTING_END, text)
                self.assertIn("Strict mode: Required", text)

    def test_install_selected_integrations_uses_rules_and_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            logs = []
            calls = []

            def fake_run_cmd(cmd, log, cwd=None):
                calls.append((tuple(cmd), cwd))
                return 0, "ok"

            result = workflows.install_selected_integrations(
                str(root),
                ["continue", "claude"],
                True,
                {"continue": ".continue/rules/grafel.md"},
                fake_run_cmd,
                lambda: ["graphify"],
                config.write_routing_block,
                logs.append,
                brevity.write_brevity_block,
                "full",
            )
            self.assertEqual(result["integrations"][0]["mode"], "rules")
            self.assertEqual(result["integrations"][1]["mode"], "install")
            self.assertTrue(any(cmd[:2] == ("graphify", "claude") for cmd, _cwd in calls))
            self.assertTrue(any(cmd[:2] == ("graphify", "hook") for cmd, _cwd in calls))
            self.assertTrue((root / ".continue" / "rules" / "grafel.md").exists())
            self.assertIn(
                brevity.BREVITY_START,
                (root / ".continue" / "rules" / "grafel.md").read_text(encoding="utf-8"),
            )

    def test_write_repo_brevity_creates_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            targets = workflows.write_repo_brevity(
                str(root), brevity.write_brevity_block, lambda _msg: None, "full"
            )
            self.assertEqual(len(targets), 3)
            for target in targets:
                self.assertIn(
                    brevity.BREVITY_START,
                    Path(target).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
