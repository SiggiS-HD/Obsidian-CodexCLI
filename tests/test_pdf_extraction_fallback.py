import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.file_context import FileContextError, render_pdf_text_for_prompt


class PdfExtractionFallbackTests(unittest.TestCase):
    def test_pdfminer_fallback_is_used_when_pypdf_returns_no_text(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "scan.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

        class _FakePage:
            def extract_text(self) -> str:
                return ""

        class _FakeReader:
            def __init__(self, _handle):
                self.pages = [_FakePage()]

        with patch("pypdf.PdfReader", _FakeReader):
            with patch("pdfminer.high_level.extract_text", return_value="Fallback text"):
                content, meta_lines = render_pdf_text_for_prompt(pdf_path)

        self.assertIn("Fallback text", content)
        self.assertTrue(any("pdfminer" in line.lower() for line in meta_lines))

    def test_ocr_fallback_is_used_when_all_text_extractors_return_empty(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "scan.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

        class _FakePage:
            def extract_text(self) -> str:
                return ""

        class _FakeReader:
            def __init__(self, _handle):
                self.pages = [_FakePage(), _FakePage()]

        class _FakeImage:
            pass

        with patch("pypdf.PdfReader", _FakeReader):
            with patch("pdfminer.high_level.extract_text", return_value=""):
                with patch("pdf2image.convert_from_path", return_value=[_FakeImage(), _FakeImage()]):
                    with patch("pytesseract.image_to_string", side_effect=["OCR page 1", "OCR page 2"]):
                        content, meta_lines = render_pdf_text_for_prompt(pdf_path)

        self.assertIn("OCR page 1", content)
        self.assertTrue(any("ocr" in line.lower() for line in meta_lines))

    def test_ocr_render_uses_temporary_output_folder(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "scan.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

        class _FakePage:
            def extract_text(self) -> str:
                return ""

        class _FakeReader:
            def __init__(self, _handle):
                self.pages = [_FakePage()]

        class _FakeImage:
            pass

        with patch("pypdf.PdfReader", _FakeReader):
            with patch("pdfminer.high_level.extract_text", return_value=""):
                with patch("pdf2image.convert_from_path", return_value=[_FakeImage()]) as mock_convert:
                    with patch("pytesseract.image_to_string", return_value="OCR page 1"):
                        render_pdf_text_for_prompt(pdf_path)

        output_folder = mock_convert.call_args.kwargs.get("output_folder")
        self.assertIsInstance(output_folder, str)
        self.assertTrue(output_folder)

    def test_error_message_mentions_ocr_when_no_text_is_extractable(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "scan.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

        class _FakePage:
            def extract_text(self) -> str:
                return ""

        class _FakeReader:
            def __init__(self, _handle):
                self.pages = [_FakePage()]

        with patch("pypdf.PdfReader", _FakeReader):
            with patch("pdfminer.high_level.extract_text", return_value=""):
                with patch("pdf2image.convert_from_path", return_value=[]):
                    with self.assertRaises(FileContextError) as ctx:
                        render_pdf_text_for_prompt(pdf_path)

        message = str(ctx.exception)
        self.assertIn("OCR", message)
        self.assertIn("Scan", message)
