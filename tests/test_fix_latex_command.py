import tempfile
import unittest
from pathlib import Path

from app.connector import run as connector_run


class FixLatexCommandTests(unittest.TestCase):
    def test_fix_latex_normalizes_outside_code_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            note_path = Path(temp_dir) / "note.md"
            note_path.write_text(
                (
                    "# Note\n\n"
                    "Preis in Text: 60€\n\n"
                    "Inline: \\(x+1\\).\n\n"
                    "Display:\n\\[\n"
                    "x^2 + 1 = 60\\,€\n"
                    "\\]\n\n"
                    "```text\n"
                    "\\[do_not_change\\]\n"
                    "\\(do_not_change\\)\n"
                    "```\n"
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as cm:
                connector_run(["fix_latex", str(note_path)])

            self.assertEqual(cm.exception.code, 0)

            updated = note_path.read_text(encoding="utf-8")
            self.assertIn("Preis in Text: 60€", updated)
            self.assertIn("Inline: $x+1$", updated)
            self.assertIn("$$\nx^2 + 1 = 60\\,\\unicode{x20AC}\n$$", updated)
            self.assertIn("```text\n\\[do_not_change\\]\n\\(do_not_change\\)\n```", updated)
            self.assertNotIn("\\(x+1\\)", updated)
            self.assertNotIn("\\[\n", updated)
