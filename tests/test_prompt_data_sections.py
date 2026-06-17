import tempfile
import unittest
from pathlib import Path

from app.file_context import collect_prompt_context_v2


class PromptDataSectionsTests(unittest.TestCase):
    def test_data_section_splits_instruction_and_data_context_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            note_path = root / "note.md"
            note_path.write_text("# Note\n", encoding="utf-8")

            style_path = root / "style.md"
            style_path.write_text("Du bist ein strenger Lektor.", encoding="utf-8")

            data_path = root / "data.csv"
            data_path.write_text("a,b\n1,2\n", encoding="utf-8")

            prompt = (
                "Bitte nutze meinen Stil.\n"
                "[Stil](style.md)\n\n"
                "### Daten\n"
                "[Tabelle](data.csv)\n"
            )

            collected = collect_prompt_context_v2(prompt, note_path)

            self.assertTrue(collected.data_mode_active)
            self.assertEqual(collected.file_context_block.strip(), "")
            self.assertIn("Zusätzliche Anweisungsquellen:", collected.instruction_context_block)
            self.assertIn(str(style_path), collected.instruction_context_block)
            self.assertIn("Zusätzliche Datenquellen", collected.data_context_block)
            self.assertIn(str(data_path), collected.data_context_block)
            self.assertEqual(collected.image_paths, [])

    def test_png_is_always_data_even_above_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            note_path = root / "note.md"
            note_path.write_text("# Note\n", encoding="utf-8")

            image_path = root / "image.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

            prompt = (
                "Bitte analysiere das Bild.\n"
                "[[image.png]]\n\n"
                "### Daten\n"
            )

            collected = collect_prompt_context_v2(prompt, note_path)

            self.assertTrue(collected.data_mode_active)
            self.assertEqual(collected.file_context_block.strip(), "")
            self.assertEqual(collected.instruction_context_block.strip(), "")
            self.assertIn(image_path, collected.image_paths)
            self.assertIn("Bild-Datenquellen", collected.data_context_block)
            self.assertIn(str(image_path), collected.data_context_block)

    def test_without_data_section_keeps_legacy_combined_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            note_path = root / "note.md"
            note_path.write_text("# Note\n", encoding="utf-8")

            context_path = root / "context.md"
            context_path.write_text("Kontext", encoding="utf-8")

            prompt = "[Kontext](context.md)\n"

            collected = collect_prompt_context_v2(prompt, note_path)

            self.assertFalse(collected.data_mode_active)
            self.assertEqual(collected.instruction_context_block, "")
            self.assertEqual(collected.data_context_block, "")
            self.assertIn("Zusätzliche Dateiquellen:", collected.file_context_block)
            self.assertIn(str(context_path), collected.file_context_block)
