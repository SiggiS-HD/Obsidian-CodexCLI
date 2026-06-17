import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.append_workflow import append_response
from app.codex_client import CodexResult
from app.image_client import ImageGenerationResult
from app.pdf_index import PdfDocumentSignature, PdfTextChunk, persist_pdf_index
from app.save_as import (
    extract_aspect_directive,
    extract_save_as_directive,
    finalize_save_as_directive,
    get_save_as_delimiter,
)


def build_note(prompt: str, chat: str = "") -> str:
    return (
        "# Test Note\n\n"
        "## Laufende Zusammenfassung\n"
        "Kurze Zusammenfassung.\n\n"
        "## Prompt\n"
        f"{prompt}\n\n"
        "## Unterhaltung\n"
        f"{chat}"
    )


class AppendWorkflowTests(unittest.TestCase):
    def create_note(self, content: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        note_path = Path(temp_dir.name) / "note.md"
        note_path.write_text(content, encoding="utf-8")
        return note_path

    def create_note_in_directory(self, directory: Path, relative_path: str, content: str) -> Path:
        note_path = directory / relative_path
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding="utf-8")
        return note_path

    def create_file(self, directory: Path, relative_path: str, content: str) -> Path:
        file_path = directory / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def create_pdf(self, directory: Path, relative_path: str, text: str) -> Path:
        file_path = directory / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(build_minimal_pdf(text))
        return file_path

    def create_png(self, directory: Path, relative_path: str) -> Path:
        file_path = directory / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        return file_path

    def test_empty_prompt_appends_error_to_note(self) -> None:
        note_path = self.create_note(build_note("   "))

        result = append_response(note_path)

        self.assertEqual(result, 1)
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Der Abschnitt ## Prompt ist leer.", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_success_appends_response_and_clears_prompt(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Das ist die Antwort.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte beantworte diese Frage."))

        result = append_response(note_path)

        self.assertEqual(result, 0)
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Ich (", updated_text)
        self.assertIn("Bitte beantworte diese Frage.", updated_text)
        self.assertIn("### Codex (", updated_text)
        self.assertIn("Das ist die Antwort.", updated_text)
        self.assertIn("## Prompt\n", updated_text)
        prompt_section = updated_text.split("## Prompt\n", maxsplit=1)[1].split("## Unterhaltung", maxsplit=1)[0]
        self.assertEqual(prompt_section.strip(), "")

    @patch("app.append_workflow.run_codex")
    def test_save_as_writes_file_and_appends_wikilink_only(self, mock_run_codex) -> None:
        note_path = self.create_note(
            build_note("Fasse den Inhalt zusammen. SAVE_AS: exports/HD_Herz.md")
        )
        cleaned, directive = extract_save_as_directive("Fasse den Inhalt zusammen. SAVE_AS: exports/HD_Herz.md")
        self.assertIsNotNone(directive)
        save_as = finalize_save_as_directive(note_path, directive)  # type: ignore[arg-type]
        delimiter = get_save_as_delimiter(save_as)

        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout=(
                "[[HD_Herz]]\n"
                f"{delimiter}\n"
                "# Zusammenfassung\n\nDas ist der gespeicherte Inhalt.\n"
            ),
            stderr="",
        )
        self.assertEqual(cleaned, "Fasse den Inhalt zusammen.")

        result = append_response(note_path)

        self.assertEqual(result, 0)
        saved_path = note_path.parent / "exports" / "HD_Herz.md"
        self.assertTrue(saved_path.exists())
        self.assertIn("Das ist der gespeicherte Inhalt.", saved_path.read_text(encoding="utf-8"))

        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("Fasse den Inhalt zusammen.", updated_text)
        self.assertNotIn("SAVE_AS:", updated_text)
        self.assertIn("### Codex (", updated_text)
        self.assertIn("[[HD_Herz]]", updated_text)
        # Ensure we do not dump the file content into the note when SAVE_AS is used.
        self.assertNotIn("Das ist der gespeicherte Inhalt.", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_save_as_without_colon_is_supported(self, mock_run_codex) -> None:
        note_path = self.create_note(
            build_note("Fasse den Inhalt zusammen. SAVE_AS exports/HD_Herz.md")
        )
        cleaned, directive = extract_save_as_directive("Fasse den Inhalt zusammen. SAVE_AS exports/HD_Herz.md")
        self.assertIsNotNone(directive)
        save_as = finalize_save_as_directive(note_path, directive)  # type: ignore[arg-type]
        delimiter = get_save_as_delimiter(save_as)

        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout=(
                "[[HD_Herz]]\n"
                f"{delimiter}\n"
                "# Zusammenfassung\n\nDas ist der gespeicherte Inhalt.\n"
            ),
            stderr="",
        )
        self.assertEqual(cleaned, "Fasse den Inhalt zusammen.")

        result = append_response(note_path)

        self.assertEqual(result, 0)
        saved_path = note_path.parent / "exports" / "HD_Herz.md"
        self.assertTrue(saved_path.exists())
        self.assertIn("Das ist der gespeicherte Inhalt.", saved_path.read_text(encoding="utf-8"))

    @patch("app.append_workflow.run_codex")
    def test_save_as_invalid_path_writes_error_and_does_not_call_codex(self, mock_run_codex) -> None:
        note_path = self.create_note(build_note("Fasse zusammen. SAVE_AS: ../evil.md"))

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Path Traversal", updated_text)

    @patch("app.append_workflow.generate_png_image")
    @patch("app.append_workflow.run_codex")
    def test_save_as_png_writes_file_and_appends_png_wikilink(
        self,
        mock_run_codex,
        mock_generate_png_image,
    ) -> None:
        note_path = self.create_note(build_note("Erzeuge ein Diagramm. ASPECT: 16:9 SAVE_AS: exports/diagramm.png"))
        mock_generate_png_image.return_value = ImageGenerationResult(
            image_bytes=b"\x89PNG\r\n\x1a\nTEST",
            error=None,
        )

        result = append_response(note_path)

        self.assertEqual(result, 0)
        mock_run_codex.assert_not_called()
        mock_generate_png_image.assert_called_once_with("Erzeuge ein Diagramm.", aspect_ratio="16:9")
        saved_path = note_path.parent / "exports" / "diagramm.png"
        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.read_bytes(), b"\x89PNG\r\n\x1a\nTEST")
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("Erzeuge ein Diagramm.", updated_text)
        self.assertNotIn("ASPECT:", updated_text)
        self.assertNotIn("SAVE_AS:", updated_text)
        self.assertIn("[[diagramm.png]]", updated_text)

    @patch("app.append_workflow.generate_png_image")
    @patch("app.append_workflow.run_codex")
    def test_save_as_png_api_error_writes_error_and_stops(
        self,
        mock_run_codex,
        mock_generate_png_image,
    ) -> None:
        note_path = self.create_note(build_note("Erzeuge ein Diagramm. SAVE_AS: exports/diagramm.png"))
        mock_generate_png_image.return_value = ImageGenerationResult(
            image_bytes=None,
            error="Bildgenerierung fehlgeschlagen (HTTP 401).",
        )

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        saved_path = note_path.parent / "exports" / "diagramm.png"
        self.assertFalse(saved_path.exists())
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Bildgenerierung fehlgeschlagen", updated_text)

    def test_finalize_save_as_directive_png_wikilink_keeps_extension(self) -> None:
        note_path = self.create_note(build_note("irrelevant"))
        _, directive = extract_save_as_directive("SAVE_AS: exports/diagramm.png")
        self.assertIsNotNone(directive)

        save_as = finalize_save_as_directive(note_path, directive)  # type: ignore[arg-type]

        self.assertEqual(save_as.output_path.suffix.lower(), ".png")
        self.assertEqual(save_as.wikilink, "[[diagramm.png]]")

    def test_extract_aspect_directive_removes_directive_from_prompt(self) -> None:
        cleaned, aspect = extract_aspect_directive("Erzeuge ein Bild. ASPECT: 16:9")

        self.assertEqual(aspect, "16:9")
        self.assertEqual(cleaned, "Erzeuge ein Bild.")

    @patch("app.append_workflow.run_codex")
    def test_save_as_empty_prompt_writes_error_and_does_not_call_codex(self, mock_run_codex) -> None:
        note_path = self.create_note(build_note("SAVE_AS: exports/out.md"))

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        saved_path = note_path.parent / "exports" / "out.md"
        self.assertFalse(saved_path.exists())
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("SAVE_AS: Der Prompt ist leer", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_export_chat_as_writes_file_and_does_not_call_codex(self, mock_run_codex) -> None:
        note_path = self.create_note(
            build_note(
                "EXPORT_CHAT_AS: exports/chat.md",
                chat=(
                    "\n\n---\n"
                    "### Ich (2026-05-20 10:00:00)\n\n"
                    "Hallo fuer schoen gruessen gross weiss heiss\n\n"
                    "### Codex (2026-05-20 10:00:01)\n\n"
                    "## Einordnung der Cholesterinwerte\n\n"
                    "- LDL ist gut.\n\n"
                    "## Quellen\n\n"
                    "- Link: https://example.com/query\n\n"
                    "Antwort 1 mit Inline-Code: `fuer schoen gruessen gross`\n\n"
                    "```text\n"
                    "fuer schoen gruessen gross\n"
                    "```\n\n"
                    "---\n"
                    "### Ich (2026-05-20 10:01:00)\n\n"
                    "Zweite Frage\n\n"
                    "### Codex (2026-05-20 10:01:01)\n\n"
                    "Antwort 2\n"
                ),
            )
        )

        result = append_response(note_path)

        self.assertEqual(result, 0)
        mock_run_codex.assert_not_called()

        exported_path = note_path.parent / "exports" / "chat.md"
        self.assertTrue(exported_path.exists())
        exported_text = exported_path.read_text(encoding="utf-8")
        self.assertNotIn("---", exported_text)
        self.assertNotIn("### Ich (", exported_text)
        self.assertNotIn("### Codex (", exported_text)
        self.assertIn("Hallo für schön grüßen groß weiß heiß", exported_text)
        self.assertIn("## Einordnung der Cholesterinwerte", exported_text)
        self.assertIn("- LDL ist gut.", exported_text)
        self.assertIn("## Quellen", exported_text)
        self.assertNotIn("## Qüllen", exported_text)
        self.assertIn("Antwort 1", exported_text)
        self.assertIn("`fuer schoen gruessen gross`", exported_text)
        self.assertIn("```text\nfuer schoen gruessen gross\n```", exported_text)
        self.assertIn("Zweite Frage", exported_text)
        self.assertIn("Antwort 2", exported_text)

        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("[[chat]]", updated_text)
        prompt_section = updated_text.split("## Prompt\n", maxsplit=1)[1].split("## Unterhaltung", maxsplit=1)[0]
        self.assertEqual(prompt_section.strip(), "")

    @patch("app.append_workflow.run_codex")
    def test_export_chat_as_invalid_path_writes_error_and_does_not_call_codex(self, mock_run_codex) -> None:
        note_path = self.create_note(build_note("EXPORT_CHAT_AS: ../evil.md"))

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Path Traversal", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_export_chat_as_empty_conversation_writes_error_and_does_not_call_codex(self, mock_run_codex) -> None:
        note_path = self.create_note(build_note("EXPORT_CHAT_AS: exports/chat.md", chat="\n"))

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("## Unterhaltung ist leer", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_export_chat_as_allows_trailing_punctuation(self, mock_run_codex) -> None:
        note_path = self.create_note(
            build_note(
                "EXPORT_CHAT_AS: exports/chat.md.",
                chat=(
                    "\n\n---\n"
                    "### Ich (2026-05-20 10:00:00)\n\n"
                    "Hallo\n\n"
                    "### Codex (2026-05-20 10:00:01)\n\n"
                    "Antwort\n"
                ),
            )
        )

        result = append_response(note_path)

        self.assertEqual(result, 0)
        mock_run_codex.assert_not_called()
        exported_path = note_path.parent / "exports" / "chat.md"
        self.assertTrue(exported_path.exists())

    @patch("app.append_workflow.run_codex")
    def test_export_chat_as_without_colon_is_supported(self, mock_run_codex) -> None:
        note_path = self.create_note(
            build_note(
                "EXPORT_CHAT_AS exports/chat.md",
                chat=(
                    "\n\n---\n"
                    "### Ich (2026-05-20 10:00:00)\n\n"
                    "Hallo\n\n"
                    "### Codex (2026-05-20 10:00:01)\n\n"
                    "Antwort\n"
                ),
            )
        )

        result = append_response(note_path)

        self.assertEqual(result, 0)
        mock_run_codex.assert_not_called()
        exported_path = note_path.parent / "exports" / "chat.md"
        self.assertTrue(exported_path.exists())

    @patch("app.append_workflow.run_codex")
    def test_codex_error_is_written_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=2,
            stdout="",
            stderr="Codex execution failed.",
        )
        note_path = self.create_note(build_note("Bitte analysieren."))

        result = append_response(note_path)

        self.assertEqual(result, 2)
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Codex execution failed.", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_start_error_is_written_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=1,
            stdout="",
            stderr="",
            start_error="Executable not found",
        )
        note_path = self.create_note(build_note("Bitte analysieren."))

        result = append_response(note_path)

        self.assertEqual(result, 1)
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Codex konnte nicht gestartet werden: Executable not found", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_markdown_link_file_is_added_to_codex_prompt(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit Kontext.",
            stderr="",
        )
        fixture_path = Path(__file__).parent / "fixtures" / "context.md"
        note_path = self.create_note(build_note(f"Bitte nutze [Kontext]({fixture_path}) fuer die Antwort."))

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("Verwende deutsche Umlaute", codex_prompt)
        self.assertIn("Vermeide ae/oe/ue/ss", codex_prompt)
        self.assertNotIn("Mathematik/LaTeX", codex_prompt)
        self.assertIn("Zusätzliche Dateiquellen:", codex_prompt)
        self.assertIn("- Pfad:", codex_prompt)
        self.assertIn("context.md", codex_prompt)
        self.assertIn("Wichtige Zusatzinfo.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_latex_rule_is_included_when_note_contains_latex(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Ok.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte berechne $x^2$ fuer x=3."))

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("Mathematik/LaTeX", codex_prompt)
        self.assertIn("Inline-Mathematik mit $...$", codex_prompt)
        self.assertIn("abgesetzte Mathematik mit $$...$$", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_latex_rule_is_included_for_common_latex_commands(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Ok.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze \\text{m} in einer Formel."))

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("Mathematik/LaTeX", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_response_latex_delimiters_are_normalized_outside_code(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout=(
                "Formel:\n"
                "\\[\n"
                "x^2 + 1\n"
                "\\]\n\n"
                "Inline: \\(x+1\\).\n\n"
                "```text\n"
                "\\[do_not_change\\]\n"
                "\\(do_not_change\\)\n"
                "```\n"
            ),
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte berechne $x^2$."))

        result = append_response(note_path)

        self.assertEqual(result, 0)
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("$$\nx^2 + 1\n$$", updated_text)
        self.assertIn("Inline: $x+1$.", updated_text)
        self.assertIn("```text\n\\[do_not_change\\]\n\\(do_not_change\\)\n```", updated_text)
        self.assertNotIn("\\[\n", updated_text)
        self.assertNotIn("\\(x+1\\)", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_euro_is_normalized_inside_math_only(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout=(
                "Preis in Text: 60€\n\n"
                "$$\n"
                "x = 60\\,€\n"
                "$$\n"
            ),
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte berechne $x$."))

        result = append_response(note_path)

        self.assertEqual(result, 0)
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("Preis in Text: 60€", updated_text)
        self.assertIn("x = 60\\,\\unicode{x20AC}", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_markdown_link_png_is_passed_as_image_attachment(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit PNG.",
            stderr="",
        )
        note_path = self.create_note(build_note("Placeholder"))
        png_path = self.create_png(note_path.parent, "image.png")
        note_path.write_text(
            build_note(f"Bitte nutze dieses Bild: [Bild]({png_path})."),
            encoding="utf-8",
        )

        append_response(note_path)

        self.assertIn("image_paths", mock_run_codex.call_args.kwargs)
        image_paths = mock_run_codex.call_args.kwargs["image_paths"]
        self.assertEqual(len(image_paths), 1)
        self.assertEqual(image_paths[0], png_path)

    @patch("app.append_workflow.run_codex")
    def test_wikilink_png_is_passed_as_image_attachment(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit PNG WikiLink.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [[bild.png]]."))
        (note_path.parent / ".obsidian").mkdir(parents=True, exist_ok=True)
        png_path = self.create_png(note_path.parent, "bild.png")

        append_response(note_path)

        image_paths = mock_run_codex.call_args.kwargs["image_paths"]
        self.assertEqual(len(image_paths), 1)
        self.assertEqual(image_paths[0], png_path)

    @patch("app.append_workflow.run_codex")
    def test_wikilink_markdown_file_is_added_to_codex_prompt(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit WikiLink-Kontext.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte beziehe [[wissen]] ein."))
        self.create_file(note_path.parent, "wissen.md", "Inhalt aus dem WikiLink.")

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("wissen.md", codex_prompt)
        self.assertIn("Inhalt aus dem WikiLink.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_wikilink_with_dots_is_resolved_as_markdown(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit WikiLink-Kontext.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte bewerte [[Urologe_3_14.4.2026]] ."))
        self.create_file(note_path.parent, "Urologe_3_14.4.2026.md", "Cholesterinwerte: LDL 120.")

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("Urologe_3_14.4.2026.md", codex_prompt)
        self.assertIn("Cholesterinwerte", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_wikilink_alias_markdown_file_is_added_to_codex_prompt(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit Alias-WikiLink-Kontext.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte beziehe [[wissen|Alias]] ein."))
        self.create_file(note_path.parent, "wissen.md", "Inhalt aus dem Alias-WikiLink.")

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("wissen.md", codex_prompt)
        self.assertIn("Inhalt aus dem Alias-WikiLink.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_wikilink_is_resolved_within_detected_vault(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit Vault-Kontext.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        vault_root = Path(temp_dir.name) / "Vault"
        (vault_root / ".obsidian").mkdir(parents=True)
        self.create_file(vault_root, "Wissen/TESTING.md", "Inhalt aus dem Vault.")
        note_path = self.create_note_in_directory(
            vault_root,
            "Beispiele/note.md",
            build_note("Bitte beziehe [[TESTING]] ein."),
        )

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("TESTING.md", codex_prompt)
        self.assertIn("Inhalt aus dem Vault.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_wikilink_does_not_resolve_file_outside_detected_vault(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        vault_root = base_dir / "Vault"
        external_root = base_dir / "External"
        (vault_root / ".obsidian").mkdir(parents=True)
        self.create_file(external_root, "TESTING.md", "Externer Inhalt.")
        note_path = self.create_note_in_directory(
            vault_root,
            "Beispiele/note.md",
            build_note("Bitte beziehe [[TESTING]] ein."),
        )

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("WikiLink konnte nicht aufgeloest werden", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_wikilink_uses_note_directory_as_fallback_without_obsidian_folder(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit Fallback-Kontext.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        note_root = Path(temp_dir.name)
        self.create_file(note_root, "wissen.md", "Fallback-Inhalt.")
        note_path = self.create_note_in_directory(
            note_root,
            "note.md",
            build_note("Bitte beziehe [[wissen]] ein."),
        )

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("wissen.md", codex_prompt)
        self.assertIn("Fallback-Inhalt.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_txt_file_is_added_to_codex_prompt(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit TXT-Kontext.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [Text](context.txt) fuer die Antwort."))
        self.create_file(note_path.parent, "context.txt", "Textdatei mit Zusatzkontext.")

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("context.txt", codex_prompt)
        self.assertIn("Textdatei mit Zusatzkontext.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_csv_file_is_added_to_codex_prompt_with_limits(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit CSV-Kontext.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [Daten](context.csv) fuer die Antwort."))
        self.create_file(
            note_path.parent,
            "context.csv",
            "name,age\nAlice,30\nBob,31\n",
        )

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("context.csv", codex_prompt)
        self.assertIn("- Typ: .csv", codex_prompt)
        self.assertIn("- Zeilen:", codex_prompt)
        self.assertIn("- Begrenzung:", codex_prompt)
        self.assertIn("| name | age |", codex_prompt)
        self.assertIn("| Alice | 30 |", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_pdf_file_is_added_to_codex_prompt_as_retrieval_context(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit PDF-Kontext.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [PDF](context.pdf) fuer die Antwort."))
        pdf_path = self.create_pdf(note_path.parent, "context.pdf", "Hello PDF")
        signature = PdfDocumentSignature(
            source_path=pdf_path,
            normalized_path=str(pdf_path),
            size_bytes=pdf_path.stat().st_size,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="context-pdf-1",
        )

        with patch("app.file_context.build_pdf_document_signature", return_value=signature):
            persist_pdf_index(
                note_path.parent / ".codexcli" / "index",
                signature,
                [PdfTextChunk(page_start=1, page_end=1, chunk_index=0, text="Hello PDF", char_count=9)],
            )
            append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("context.pdf", codex_prompt)
        self.assertIn("- Typ: .pdf", codex_prompt)
        self.assertIn("[PDF-Quelle 1]", codex_prompt)
        self.assertIn("Seite 1", codex_prompt)
        self.assertIn("- Retrieval:", codex_prompt)
        self.assertIn("Hello PDF", codex_prompt)


def build_minimal_pdf(text: str) -> bytes:
    """Build a tiny single-page PDF with an embedded text content stream.

    This avoids adding a second PDF generator dependency just for tests.
    """

    def escape_pdf_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    text = escape_pdf_text(text)
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"

    objects: list[bytes] = []

    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
    )

    stream_text = f"BT /F1 24 Tf 72 72 Td ({text}) Tj ET".encode("ascii")
    objects.append(
        b"4 0 obj\n"
        + f"<< /Length {len(stream_text)} >>\n".encode("ascii")
        + b"stream\n"
        + stream_text
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    pdf = bytearray(header)
    offsets = [0]

    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_start = len(pdf)
    pdf.extend(b"xref\n")
    pdf.extend(b"0 6\n")
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(b"trailer\n")
    pdf.extend(b"<< /Size 6 /Root 1 0 R >>\n")
    pdf.extend(b"startxref\n")
    pdf.extend(f"{xref_start}\n".encode("ascii"))
    pdf.extend(b"%%EOF\n")
    return bytes(pdf)

    @patch("app.append_workflow.run_codex")
    def test_moc_file_adds_referenced_files_in_defined_order(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit MOC-Kontext.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        vault_root = Path(temp_dir.name)
        self.create_file(vault_root, "docs/first.md", "Erster Inhalt.")
        self.create_file(vault_root, "docs/second.txt", "Zweiter Inhalt.")
        self.create_file(
            vault_root,
            "moc.md",
            "# MOC\n\n1. [[first]]\n2. [Second](docs/second.txt)\n",
        )
        note_path = self.create_note_in_directory(
            vault_root,
            "note.md",
            build_note("Bitte nutze [Arbeitsmappe](moc.md)."),
        )

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("MOC moc.md, Position 1", codex_prompt)
        self.assertIn("MOC moc.md, Position 2", codex_prompt)
        first_index = codex_prompt.index("Erster Inhalt.")
        second_index = codex_prompt.index("Zweiter Inhalt.")
        self.assertLess(first_index, second_index)
        self.assertNotIn("# MOC", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_markdown_file_with_moc_heading_later_is_not_treated_as_moc(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [Doku](doc.md)."))
        self.create_file(
            note_path.parent,
            "doc.md",
            "# Dokument\n\n"
            "Einfacher Kontext.\n\n"
            "## MOC (nur Erwaehnung)\n\n"
            "1. Das ist nur Text, keine Dateireferenz\n",
        )

        result = append_response(note_path)

        self.assertEqual(result, 0)
        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("doc.md", codex_prompt)
        self.assertIn("Einfacher Kontext.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_moc_file_is_expanded_when_directly_referenced_via_wikilink(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit WikiLink-MOC-Kontext.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        vault_root = Path(temp_dir.name)
        self.create_file(vault_root, "docs/first.md", "Erster Inhalt aus WikiLink-MOC.")
        self.create_file(
            vault_root,
            "32 Depot.md",
            "# Depot MOC\n\n1. [[first]]\n",
        )
        note_path = self.create_note_in_directory(
            vault_root,
            "note.md",
            build_note("Verarbeite [[32 Depot]]."),
        )

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("MOC 32 Depot.md, Position 1", codex_prompt)
        self.assertIn("Erster Inhalt aus WikiLink-MOC.", codex_prompt)
        self.assertNotIn("# Depot MOC", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_moc_file_deduplicates_repeated_references(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit dedupliziertem MOC-Kontext.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        vault_root = Path(temp_dir.name)
        self.create_file(vault_root, "docs/shared.md", "Nur einmal aufnehmen.")
        self.create_file(
            vault_root,
            "moc.md",
            "# MOC\n\n1. [[shared]]\n2. [[shared]]\n",
        )
        note_path = self.create_note_in_directory(
            vault_root,
            "note.md",
            build_note("Bitte nutze [Arbeitsmappe](moc.md)."),
        )

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertEqual(codex_prompt.count("Nur einmal aufnehmen."), 1)
        self.assertEqual(codex_prompt.count("Quelle "), 1)

    @patch("app.append_workflow.run_codex")
    def test_markdown_file_with_numbered_list_without_moc_heading_stays_normal_context(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit normalem Markdown-Kontext.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        vault_root = Path(temp_dir.name)
        self.create_file(
            vault_root,
            "normal.md",
            "# Notizen\n\n1. Erster Punkt\n2. Zweiter Punkt\n",
        )
        note_path = self.create_note_in_directory(
            vault_root,
            "note.md",
            build_note("Bitte nutze [Notizen](normal.md)."),
        )

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("# Notizen", codex_prompt)
        self.assertIn("Erster Punkt", codex_prompt)
        self.assertIn("Direkt aus ## Prompt", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_invalid_moc_entry_writes_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        vault_root = Path(temp_dir.name)
        self.create_file(vault_root, "docs/first.md", "Erster Inhalt.")
        self.create_file(vault_root, "docs/second.md", "Zweiter Inhalt.")
        self.create_file(
            vault_root,
            "moc.md",
            "# MOC\n\n1. [[first]] und [[second]]\n",
        )
        note_path = self.create_note_in_directory(
            vault_root,
            "note.md",
            build_note("Bitte nutze [Arbeitsmappe](moc.md)."),
        )

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Ungueltiger MOC-Eintrag", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_nested_moc_file_writes_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        vault_root = Path(temp_dir.name)
        self.create_file(vault_root, "nested.md", "# Nested MOC\n\n1. [[other]]\n")
        self.create_file(vault_root, "other.md", "Normaler Inhalt.")
        self.create_file(
            vault_root,
            "moc.md",
            "# MOC\n\n1. [Nested](nested.md)\n",
        )
        note_path = self.create_note_in_directory(
            vault_root,
            "note.md",
            build_note("Bitte nutze [Arbeitsmappe](moc.md)."),
        )

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Verschachtelte MOC-Dateien", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_absolute_windows_path_is_added_to_codex_prompt(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit absolutem Pfad.",
            stderr="",
        )
        note_path = self.create_note(build_note("Placeholder"))
        context_path = self.create_file(note_path.parent, "absolute-context.md", "Kontext ueber absoluten Pfad.")
        note_path.write_text(
            build_note(f"Bitte nutze diese Datei: {context_path}"),
            encoding="utf-8",
        )

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn(str(context_path), codex_prompt)
        self.assertIn("Kontext ueber absoluten Pfad.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_absolute_windows_path_png_is_passed_as_image_attachment(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit absolutem PNG-Pfad.",
            stderr="",
        )
        note_path = self.create_note(build_note("Placeholder"))
        png_path = self.create_png(note_path.parent, "absolute-image.png")
        note_path.write_text(
            build_note(f"Bitte nutze dieses Bild: {png_path}"),
            encoding="utf-8",
        )

        append_response(note_path)

        image_paths = mock_run_codex.call_args.kwargs["image_paths"]
        self.assertEqual(len(image_paths), 1)
        self.assertEqual(image_paths[0], png_path)

    @patch("app.append_workflow.run_codex")
    def test_unc_path_in_prompt_is_added_to_codex_prompt(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit UNC-Pfad.",
            stderr="",
        )
        note_path = self.create_note(build_note("Placeholder"))
        local_context_path = self.create_file(
            note_path.parent,
            "unc-context.md",
            "Kontext ueber UNC-Pfad.",
        )
        unc_path_text = r"\\CL10NAS.local\CL10data\docs\unc-context.md"
        note_path.write_text(
            build_note(f"Bitte nutze diese Datei: {unc_path_text}"),
            encoding="utf-8",
        )

        with patch("app.file_context.validate_resolved_path") as mock_validate:
            def validate_side_effect(path: Path) -> Path:
                self.assertTrue(str(path).startswith("\\\\"))
                return local_context_path

            mock_validate.side_effect = validate_side_effect
            append_response(note_path)

        self.assertTrue(mock_validate.called)
        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("Kontext ueber UNC-Pfad.", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_unc_path_png_is_passed_as_image_attachment(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit UNC PNG.",
            stderr="",
        )
        note_path = self.create_note(build_note("Placeholder"))
        local_png_path = self.create_png(note_path.parent, "unc-image.png")
        unc_path_text = r"\\CL10NAS.local\CL10data\docs\image.png"
        note_path.write_text(
            build_note(f"Bitte nutze dieses Bild: {unc_path_text}"),
            encoding="utf-8",
        )

        with patch("app.file_context.validate_resolved_path") as mock_validate:
            def validate_side_effect(path: Path) -> Path:
                self.assertTrue(str(path).startswith("\\\\"))
                return local_png_path

            mock_validate.side_effect = validate_side_effect
            append_response(note_path)

        image_paths = mock_run_codex.call_args.kwargs["image_paths"]
        self.assertEqual(len(image_paths), 1)
        self.assertEqual(image_paths[0], local_png_path)

    @patch("app.append_workflow.run_codex")
    def test_too_many_png_attachments_writes_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Placeholder"))
        png_paths = [self.create_png(note_path.parent, f"img-{i}.png") for i in range(5)]
        prompt = "\n".join(f"[img]({path})" for path in png_paths)
        note_path.write_text(build_note(prompt), encoding="utf-8")

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Zu viele PNG-Dateien", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_unreachable_unc_path_writes_clear_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Placeholder"))
        unc_path_text = r"\\CL10NAS.local\CL10data\docs\missing.md"
        note_path.write_text(
            build_note(f"Bitte nutze diese Datei: {unc_path_text}"),
            encoding="utf-8",
        )

        original_exists = Path.exists

        def exists_side_effect(self_path: Path) -> bool:
            if str(self_path).startswith("\\\\"):
                raise OSError("Network share unreachable")
            return original_exists(self_path)

        with patch("pathlib.Path.exists", new=exists_side_effect):
            result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("NAS/UNC-Pfad nicht erreichbar", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_unc_pdf_path_writes_clear_not_supported_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Placeholder"))
        pdf_path_text = r"\\CL10NAS.local\CL10data\Mathe\Mathe1und2.pdf"
        note_path.write_text(
            build_note(f"Nutze nur diese Quelle: {pdf_path_text}"),
            encoding="utf-8",
        )

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Bitte zuerst indexieren", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_pdf_reference_uses_retrieval_context_when_index_exists(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit PDF-Retrieval.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte beantworte die Frage mit [PDF](source.pdf)."))
        pdf_path = self.create_pdf(note_path.parent, "source.pdf", "Alpha Beta Gamma")
        signature = PdfDocumentSignature(
            source_path=pdf_path,
            normalized_path=str(pdf_path),
            size_bytes=pdf_path.stat().st_size,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="pdf-doc-1",
        )
        with patch("app.file_context.build_pdf_document_signature", return_value=signature):
            persist_pdf_index(
                note_path.parent / ".codexcli" / "index",
                signature,
                [PdfTextChunk(page_start=1, page_end=1, chunk_index=0, text="Alpha Beta Gamma", char_count=16)],
            )
            result = append_response(note_path)

        self.assertEqual(result, 0)
        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("[PDF-Quelle 1]", codex_prompt)
        self.assertIn("Seite 1", codex_prompt)
        self.assertIn("Alpha Beta Gamma", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_pdf_reference_without_index_writes_clear_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [PDF](source.pdf)."))
        self.create_pdf(note_path.parent, "source.pdf", "Alpha Beta Gamma")

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Bitte zuerst indexieren", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_pdf_wikilink_with_explicit_pdf_extension_without_index_writes_clear_error(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Fasse den Inhalt von [[RAG_Test.pdf]] zusammen."))
        self.create_pdf(note_path.parent, "RAG_Test.pdf", "Alpha Beta Gamma")

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Bitte zuerst indexieren", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_pdf_wikilink_without_extension_prefers_pdf_when_present(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Fasse den Inhalt von [[RAG_Test]] zusammen."))
        self.create_pdf(note_path.parent, "RAG_Test.pdf", "Alpha Beta Gamma")

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Bitte zuerst indexieren", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_codex_prompt_contains_priority_rules_for_file_context(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Antwort mit Prioritaetsregeln.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [[wissen]]."))
        self.create_file(note_path.parent, "wissen.md", "Inhalt mit Zusatzanweisung.")

        append_response(note_path)

        codex_prompt = mock_run_codex.call_args.args[0]
        self.assertIn("Priorität bei Widersprüchen", codex_prompt)
        self.assertIn("aktueller Prompt vor referenzierten Dateien", codex_prompt)
        self.assertIn("referenzierte Dateien vor laufender Zusammenfassung", codex_prompt)

    @patch("app.append_workflow.run_codex")
    def test_missing_referenced_file_writes_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [Fehlt](missing.md)."))

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Datei nicht gefunden", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_unsupported_referenced_file_type_writes_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [JSON](data.json)."))
        self.create_file(note_path.parent, "data.json", '{"a": 1}')

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("Nicht unterstuetzter Dateityp", updated_text)

    @patch("app.append_workflow.run_codex")
    def test_ambiguous_wikilink_writes_error_to_note(self, mock_run_codex) -> None:
        mock_run_codex.return_value = CodexResult(
            returncode=0,
            stdout="Sollte nicht verwendet werden.",
            stderr="",
        )
        note_path = self.create_note(build_note("Bitte nutze [[doppelt]]."))
        self.create_file(note_path.parent, "eins/doppelt.md", "Erster Inhalt.")
        self.create_file(note_path.parent, "zwei/doppelt.md", "Zweiter Inhalt.")

        result = append_response(note_path)

        self.assertEqual(result, 1)
        mock_run_codex.assert_not_called()
        updated_text = note_path.read_text(encoding="utf-8")
        self.assertIn("### Codex Fehler", updated_text)
        self.assertIn("WikiLink ist mehrdeutig", updated_text)


if __name__ == "__main__":
    unittest.main()
