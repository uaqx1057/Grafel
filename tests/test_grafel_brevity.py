import tempfile
import unittest
from pathlib import Path

from grafel_core import brevity


class GrafelBrevityTests(unittest.TestCase):
    def test_write_brevity_block_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "AGENTS.md"
            path.write_text("Header\n", encoding="utf-8")
            self.assertTrue(brevity.write_brevity_block(str(path), "full"))
            first = path.read_text(encoding="utf-8")
            self.assertFalse(brevity.write_brevity_block(str(path), "full"))
            self.assertEqual(first, path.read_text(encoding="utf-8"))

    def test_compress_memory_text_preserves_code_blocks(self):
        text = "# Heading\n\nYou should really run tests before push.\n\n```bash\nnpm test\n```\n"
        result = brevity.compress_memory_text(text, "full")
        self.assertIn("Run tests before push.", result)
        self.assertIn("```bash\nnpm test\n```", result)

    def test_compress_sentence_preserves_inline_code_span(self):
        result = brevity.compress_sentence("Run `npm install` now.", "full")
        self.assertIn("`npm install`", result)
        self.assertNotIn("GRAFEL", result)
        self.assertNotIn("\x00", result)

    def test_compress_sentence_preserves_url(self):
        result = brevity.compress_sentence(
            "See https://example.com/path?query=1 for details.", "full"
        )
        self.assertIn("https://example.com/path?query=1", result)
        self.assertNotIn("GRAFEL", result)
        self.assertNotIn("\x00", result)

    def test_compress_sentence_caps_plus_code_and_url_no_placeholder_collision(self):
        # Regression: ALL-CAPS protection used to re-wrap the placeholder
        # inserted for a code span/URL, leaving literal __GRAFEL_TOKEN_n__
        # garbage in the output.
        result = brevity.compress_sentence(
            "NOTE: run `git status` at https://example.com/docs for API_KEY setup.",
            "ultra",
        )
        self.assertIn("NOTE", result)
        self.assertIn("`git status`", result)
        self.assertIn("https://example.com/docs", result)
        self.assertIn("API_KEY", result)
        self.assertNotIn("GRAFEL", result)
        self.assertNotIn("\x00", result)

    def test_compress_memory_text_preserves_inline_code_on_plain_line(self):
        text = "# Setup\n\nYou should really run `npm install` first. See https://example.com for MORE INFO.\n"
        result = brevity.compress_memory_text(text, "full")
        self.assertIn("`npm install`", result)
        self.assertIn("https://example.com", result)
        self.assertNotIn("GRAFEL", result)
        self.assertNotIn("\x00", result)

    def test_compress_memory_file_writes_backup_and_saves_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CLAUDE.md"
            path.write_text(
                "# Notes\n\nYou should really make sure to run tests before pushing changes.\n",
                encoding="utf-8",
            )
            result = brevity.compress_memory_file(str(path), "full")
            self.assertTrue(result["ok"])
            self.assertTrue((Path(tmp) / "CLAUDE.original.md").exists())
            self.assertGreater(result["saved_tokens"], 0)

    def test_output_savings_snapshot_uses_output_channels(self):
        snap = brevity.output_savings_snapshot(
            {"totals": {"out": 1000}},
            {"output": 500},
            {"turns": 10},
            "ultra",
        )
        self.assertEqual(snap["estimated_output_tokens"], 3300)
        self.assertGreater(snap["estimated_saved_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
