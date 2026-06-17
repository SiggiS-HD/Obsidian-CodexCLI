import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.config import get_runtime_tmp_root
from app.connector import run as connector_run
from app.pdf_index import PdfIndexError


def build_minimal_pdf(text: str) -> bytes:
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
    pdf.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n")
    pdf.extend(f"{xref_start}\n".encode("ascii"))
    pdf.extend(b"%%EOF\n")
    return bytes(pdf)


class PdfIndexCommandTests(unittest.TestCase):
    def create_note(self, directory: Path, relative_path: str, prompt: str) -> Path:
        note_path = directory / relative_path
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            (
                "# Note\n\n"
                "## Laufende Zusammenfassung\n\n"
                "## Prompt\n"
                f"{prompt}\n\n"
                "## Unterhaltung\n"
            ),
            encoding="utf-8",
        )
        return note_path

    def create_pdf(self, directory: Path, relative_path: str, text: str) -> Path:
        file_path = directory / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(build_minimal_pdf(text))
        return file_path

    def run_command(self, args: list[str]) -> tuple[int, str]:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as cm:
                connector_run(args)
        return int(cm.exception.code), stdout.getvalue()

    def run_diag(self, args: list[str]) -> str:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            connector_run(args)
        return stdout.getvalue()

    def test_index_pdf_builds_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            pdf_path = self.create_pdf(vault_root, "docs/source.pdf", "Hello PDF")

            code, output = self.run_command(["index_pdf", str(pdf_path)])

            self.assertEqual(code, 0)
            self.assertIn("PDF-Index erstellt", output)
            self.assertIn("Chunks:", output)

    def test_diag_reports_runtime_tmp_root_and_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            note_path = self.create_note(vault_root, "notes/source.md", "Hallo")

            output = self.run_diag(["diag", str(note_path)])
            expected_runtime_tmp_root = get_runtime_tmp_root(Path(r"D:\Ideas"))

            self.assertIn("## Laufzeit-Artefakte", output)
            self.assertIn(f"- Runtime-Tmp-Root: `{expected_runtime_tmp_root}`", output)
            self.assertIn("- Runtime-Tmp-Status: vorhanden", output)
            self.assertIn("koennen bei Bedarf manuell geloescht werden", output)

    def test_index_status_reports_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            pdf_path = self.create_pdf(vault_root, "docs/source.pdf", "Hello PDF")
            self.run_command(["index_pdf", str(pdf_path)])

            code, output = self.run_command(["index_status", str(pdf_path)])

            self.assertEqual(code, 0)
            self.assertIn("Exists: True", output)
            self.assertIn("Needs rebuild: False", output)

    def test_index_clear_deletes_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            pdf_path = self.create_pdf(vault_root, "docs/source.pdf", "Hello PDF")
            self.run_command(["index_pdf", str(pdf_path)])

            code, output = self.run_command(["index_clear", str(pdf_path)])

            self.assertEqual(code, 0)
            self.assertIn("PDF-Index geloescht", output)

            code, output = self.run_command(["index_status", str(pdf_path)])
            self.assertEqual(code, 0)
            self.assertIn("Exists: False", output)

    def test_index_pdf_requires_pdf_path(self) -> None:
        code, output = self.run_command(["index_pdf"])
        self.assertEqual(code, 1)
        self.assertIn("kein PDF-Pfad", output)

    def test_index_pdf_reports_unreachable_unc_path_clearly(self) -> None:
        unc_pdf = r"\\CL10NAS.local\share\docs\source.pdf"

        with patch("pathlib.Path.exists", side_effect=OSError("network path not found")):
            code, output = self.run_command(["index_pdf", unc_pdf])

        self.assertEqual(code, 1)
        self.assertIn("Fehler", output)

    def test_index_note_pdfs_builds_index_from_prompt_wikilink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            self.create_pdf(vault_root, "docs/RAG_Test.pdf", "Hello PDF")
            note_path = self.create_note(
                vault_root,
                "notes/test.md",
                "Fasse den Inhalt von [[RAG_Test.pdf]] zusammen.",
            )

            code, output = self.run_command(["index_note_pdfs", str(note_path)])

            self.assertEqual(code, 0)
            self.assertIn("1 PDF-Datei(en) im Prompt gefunden.", output)
            self.assertIn("Index erstellt:", output)
            updated_note = note_path.read_text(encoding="utf-8")
            self.assertIn("### Codex Index (", updated_note)
            self.assertIn("Neu indexiert: 1", updated_note)

    def test_index_note_pdfs_without_pdf_references_returns_clear_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            note_path = self.create_note(
                vault_root,
                "notes/test.md",
                "Bitte nutze [[wissen.md]] fuer die Antwort.",
            )
            (vault_root / "wissen.md").write_text("Kontext", encoding="utf-8")

            code, output = self.run_command(["index_note_pdfs", str(note_path)])

            self.assertEqual(code, 1)
            self.assertIn("Keine PDF-Referenzen", output)

    def test_index_note_pdfs_skips_current_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            pdf_path = self.create_pdf(vault_root, "docs/RAG_Test.pdf", "Hello PDF")
            note_path = self.create_note(
                vault_root,
                "notes/test.md",
                "Fasse den Inhalt von [[RAG_Test.pdf]] zusammen.",
            )

            first_code, _ = self.run_command(["index_note_pdfs", str(note_path)])
            self.assertEqual(first_code, 0)

            code, output = self.run_command(["index_note_pdfs", str(note_path)])

            self.assertEqual(code, 0)
            self.assertIn(f"Index bereits aktuell: {pdf_path}", output)
            updated_note = note_path.read_text(encoding="utf-8")
            self.assertIn("### Codex Index (", updated_note)
            self.assertIn("Unveraendert: 1", updated_note)

    def test_index_note_pdfs_writes_error_block_when_build_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            pdf_path = self.create_pdf(vault_root, "docs/RAG_Test.pdf", "Hello PDF")
            note_path = self.create_note(
                vault_root,
                "notes/test.md",
                "Fasse den Inhalt von [[RAG_Test.pdf]] zusammen.",
            )

            with patch("app.connector.build_pdf_index", side_effect=PdfIndexError("PDF-Index waere zu gross fuer v1.")):
                code, output = self.run_command(["index_note_pdfs", str(note_path)])

            self.assertEqual(code, 1)
            self.assertIn(f"Fehler bei {pdf_path}", output)
            updated_note = note_path.read_text(encoding="utf-8")
            self.assertIn("### Codex Index (", updated_note)
            self.assertIn("Neu indexiert: 0", updated_note)
            self.assertIn("PDF-Index waere zu gross fuer v1.", updated_note)

    def test_index_note_status_reports_status_and_writes_note_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            pdf_path = self.create_pdf(vault_root, "docs/RAG_Test.pdf", "Hello PDF")
            note_path = self.create_note(
                vault_root,
                "notes/test.md",
                "Fasse den Inhalt von [[RAG_Test.pdf]] zusammen.",
            )
            self.run_command(["index_note_pdfs", str(note_path)])

            code, output = self.run_command(["index_note_status", str(note_path)])

            self.assertEqual(code, 0)
            self.assertIn(f"Status: {pdf_path}", output)
            self.assertIn("Exists: True", output)
            self.assertIn("Needs rebuild: False", output)
            updated_note = note_path.read_text(encoding="utf-8")
            self.assertIn("### Codex Index Status (", updated_note)
            self.assertIn("Exists: True", updated_note)

    def test_index_note_clear_deletes_indexes_and_writes_note_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            pdf_path = self.create_pdf(vault_root, "docs/RAG_Test.pdf", "Hello PDF")
            note_path = self.create_note(
                vault_root,
                "notes/test.md",
                "Fasse den Inhalt von [[RAG_Test.pdf]] zusammen.",
            )
            self.run_command(["index_note_pdfs", str(note_path)])

            code, output = self.run_command(["index_note_clear", str(note_path)])

            self.assertEqual(code, 0)
            self.assertIn(f"PDF-Index geloescht: {pdf_path}", output)
            updated_note = note_path.read_text(encoding="utf-8")
            self.assertIn("### Codex Index Clear (", updated_note)
            self.assertIn("Geloescht: 1", updated_note)

    def test_index_note_status_without_pdf_references_returns_clear_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            note_path = self.create_note(
                vault_root,
                "notes/test.md",
                "Bitte nutze [[wissen.md]] fuer die Antwort.",
            )
            (vault_root / "wissen.md").write_text("Kontext", encoding="utf-8")

            code, output = self.run_command(["index_note_status", str(note_path)])

            self.assertEqual(code, 1)
            self.assertIn("Keine PDF-Referenzen", output)

    def test_index_note_clear_without_pdf_references_returns_clear_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_root = Path(temp_dir)
            (vault_root / ".obsidian").mkdir()
            note_path = self.create_note(
                vault_root,
                "notes/test.md",
                "Bitte nutze [[wissen.md]] fuer die Antwort.",
            )
            (vault_root / "wissen.md").write_text("Kontext", encoding="utf-8")

            code, output = self.run_command(["index_note_clear", str(note_path)])

            self.assertEqual(code, 1)
            self.assertIn("Keine PDF-Referenzen", output)
