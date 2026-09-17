import importlib.util
import tempfile
import unittest
from pathlib import Path

from grafel_core import config, graphs, workflows


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("grafel_module", ROOT / "grafel.py")
grafel = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(grafel)


class GrafelSmokeTests(unittest.TestCase):
    def test_real_build_freshness_and_local_wiring_flow(self):
        if not grafel.find_graphify():
            self.skipTest("graphify CLI not installed")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = root / "demo.py"
            code.write_text("def hello():\n    return 1\n", encoding="utf-8")
            (root / ".git").mkdir()
            logs = []

            build = workflows.build_graph(str(root), grafel.run_cmd, grafel.graphify_cmd, logs.append)
            self.assertEqual(build["code"], 0)
            self.assertTrue((root / "graphify-out" / "graph.json").exists())
            self.assertTrue((root / "graphify-out" / "GRAPH_REPORT.md").exists())
            self.assertTrue((root / "graphify-out" / "graph.html").exists())

            fresh = graphs.graph_artifact_state(
                str(root), grafel.SAVINGS_CODE_EXT, grafel.SAVINGS_SKIP_DIRS
            )
            self.assertTrue(fresh["graph_exists"])
            self.assertFalse(fresh["graph_stale"])

            code.write_text("def hello():\n    return 2\n", encoding="utf-8")
            stale = graphs.graph_artifact_state(
                str(root), grafel.SAVINGS_CODE_EXT, grafel.SAVINGS_SKIP_DIRS
            )
            self.assertTrue(stale["graph_stale"] or stale["report_stale"])

            workflows.install_repo_mcp(str(root), config.merge_json_servers, logs.append)
            workflows.write_repo_routing(str(root), config.write_routing_block, logs.append)
            workflows.ensure_gitignore_entry(str(root), "graphify-out", logs.append)

            self.assertTrue((root / ".vscode" / "mcp.json").exists())
            self.assertTrue((root / ".mcp.json").exists())
            self.assertTrue((root / "graphify-out" / "grafel-query.cmd").exists())
            self.assertTrue((root / "CLAUDE.md").exists())
            self.assertTrue((root / "AGENTS.md").exists())
            self.assertIn("graphify-out/", (root / ".gitignore").read_text(encoding="utf-8"))

            rebuild = workflows.build_graph(str(root), grafel.run_cmd, grafel.graphify_cmd, logs.append)
            self.assertEqual(rebuild["code"], 0)
            refreshed = graphs.graph_artifact_state(
                str(root), grafel.SAVINGS_CODE_EXT, grafel.SAVINGS_SKIP_DIRS
            )
            self.assertFalse(refreshed["graph_stale"])


if __name__ == "__main__":
    unittest.main()
