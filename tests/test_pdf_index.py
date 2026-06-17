import sqlite3
import hashlib
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.pdf_index import (
    RAG_CHUNK_OVERLAP_CHARS,
    RAG_CHUNK_TARGET_CHARS,
    RAG_MAX_INDEX_TEXT_CHARS,
    PdfIndexStatus,
    PdfPageText,
    PdfTextChunk,
    PdfDocumentSignature,
    PdfRetrievedChunk,
    PdfIndexError,
    acquire_document_lock,
    build_pdf_chunks,
    build_pdf_document_signature,
    build_pdf_index,
    extract_pdf_pages_for_index,
    ensure_document_index_dir,
    ensure_index_root_available,
    build_retrieval_query,
    get_document_index_db_path,
    get_document_index_dir,
    get_index_status,
    get_document_lockfile,
    format_retrieved_chunks_for_prompt,
    normalize_pdf_text,
    normalize_document_path,
    open_index_db,
    persist_pdf_index,
    retrieve_pdf_chunks,
)


class PdfIndexTests(unittest.TestCase):
    def test_normalize_pdf_text_collapses_basic_whitespace(self) -> None:
        raw = "  Alpha\t\tBeta \r\n\r\n\r\n Gamma \u200bDelta \n"
        normalized = normalize_pdf_text(raw)
        self.assertEqual(normalized, "Alpha Beta\n\nGamma Delta")

    def test_normalize_document_path_keeps_unc_prefix(self) -> None:
        path = Path(r"\\CL10NAS\lyt\Siggiverse\Docs\Scan.pdf")
        normalized = normalize_document_path(path)
        self.assertEqual(normalized, r"\\CL10NAS\lyt\Siggiverse\Docs\Scan.pdf")

    def test_normalize_document_path_uppercases_drive_letter(self) -> None:
        path = Path(r"d:\ideas\docs\scan.pdf")
        normalized = normalize_document_path(path)
        self.assertEqual(normalized, r"D:\ideas\docs\scan.pdf")

    def test_build_pdf_document_signature_uses_path_size_and_mtime(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "scan.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

        fake_mtime = 1_717_000_000
        expected_mtime = datetime.fromtimestamp(fake_mtime, tz=UTC).isoformat()
        expected_normalized = normalize_document_path(pdf_path)
        expected_size = pdf_path.stat().st_size
        expected_doc_id = hashlib.sha256(
            f"{expected_normalized}|{expected_size}|{expected_mtime}".encode("utf-8")
        ).hexdigest()

        fake_stat = SimpleNamespace(st_size=expected_size, st_mtime=fake_mtime)

        with patch("pathlib.Path.stat", return_value=fake_stat):
            signature = build_pdf_document_signature(pdf_path)

        self.assertEqual(
            signature,
            PdfDocumentSignature(
                source_path=pdf_path,
                normalized_path=expected_normalized,
                size_bytes=expected_size,
                mtime_utc=expected_mtime,
                doc_id=expected_doc_id,
            ),
        )

    def test_ensure_index_root_available_creates_directory(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        index_root = Path(temp_dir.name) / ".codexcli" / "index"
        result = ensure_index_root_available(index_root)

        self.assertEqual(result, index_root)
        self.assertTrue(index_root.is_dir())

    def test_ensure_index_root_available_wraps_os_errors(self) -> None:
        index_root = Path(r"\\CL10NAS\lyt\Siggiverse\.codexcli\index")

        with patch("pathlib.Path.mkdir", side_effect=OSError("network path not found")):
            with self.assertRaises(PdfIndexError) as ctx:
                ensure_index_root_available(index_root)

        self.assertIn("Index-Root", str(ctx.exception))
        self.assertIn("nicht erreichbar", str(ctx.exception))

    def test_extract_pdf_pages_for_index_uses_pdfminer_fallback_per_page(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "scan.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

        class _FakePage:
            def __init__(self, text: str) -> None:
                self._text = text

            def extract_text(self) -> str:
                return self._text

        class _FakeReader:
            def __init__(self, _handle):
                self.pages = [_FakePage("Page one"), _FakePage("")]

        with patch("pypdf.PdfReader", _FakeReader):
            with patch("pdfminer.high_level.extract_text", return_value="Fallback page two"):
                pages = extract_pdf_pages_for_index(pdf_path)

        self.assertEqual(
            pages,
            [
                PdfPageText(page=1, text="Page one", char_count=8),
                PdfPageText(page=2, text="Fallback page two", char_count=17),
            ],
        )

    def test_extract_pdf_pages_for_index_rejects_empty_scan_like_pdf(self) -> None:
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
                with self.assertRaises(PdfIndexError) as ctx:
                    extract_pdf_pages_for_index(pdf_path)

        self.assertIn("keinen extrahierbaren Text", str(ctx.exception))

    def test_extract_pdf_pages_for_index_appends_page_uri_links(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "links.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

        class _FakeAnnotRef:
            def __init__(self, uri: str) -> None:
                self._uri = uri

            def get_object(self):
                return {
                    "/Subtype": "/Link",
                    "/A": {"/URI": self._uri},
                }

        class _FakePage:
            def __init__(self, text: str, uris: list[str]) -> None:
                self._text = text
                self._annots = [_FakeAnnotRef(uri) for uri in uris]

            def extract_text(self) -> str:
                return self._text

            def get(self, key: str):
                if key == "/Annots":
                    return self._annots
                return None

        class _FakeReader:
            def __init__(self, _handle):
                self.pages = [_FakePage("Mathe Inhalt", ["https://example.com/video", "https://example.com/video"])]

        with patch("pypdf.PdfReader", _FakeReader):
            pages = extract_pdf_pages_for_index(pdf_path)

        self.assertEqual(len(pages), 1)
        self.assertIn("Mathe Inhalt", pages[0].text)
        self.assertIn("PDF-Links:", pages[0].text)
        self.assertIn("https://example.com/video", pages[0].text)
        self.assertEqual(pages[0].text.count("https://example.com/video"), 1)

    def test_extract_pdf_pages_for_index_keeps_link_only_pages(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "links-only.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

        class _FakeAnnotRef:
            def __init__(self, uri: str) -> None:
                self._uri = uri

            def get_object(self):
                return {
                    "/Subtype": "/Link",
                    "/A": {"/URI": self._uri},
                }

        class _FakePage:
            def extract_text(self) -> str:
                return ""

            def get(self, key: str):
                if key == "/Annots":
                    return [_FakeAnnotRef("https://example.com/qr-only")]
                return None

        class _FakeReader:
            def __init__(self, _handle):
                self.pages = [_FakePage()]

        with patch("pypdf.PdfReader", _FakeReader):
            with patch("pdfminer.high_level.extract_text", return_value=""):
                pages = extract_pdf_pages_for_index(pdf_path)

        self.assertEqual(
            pages,
            [
                PdfPageText(
                    page=1,
                    text="PDF-Links:\nhttps://example.com/qr-only",
                    char_count=len("PDF-Links:\nhttps://example.com/qr-only"),
                )
            ],
        )

    def test_build_pdf_chunks_keeps_page_boundaries(self) -> None:
        pages = [
            PdfPageText(page=1, text="A" * (RAG_CHUNK_TARGET_CHARS + 50), char_count=RAG_CHUNK_TARGET_CHARS + 50),
            PdfPageText(page=2, text="B" * 40, char_count=40),
        ]

        chunks = build_pdf_chunks(pages)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual(chunks[0].page_start, 1)
        self.assertEqual(chunks[0].page_end, 1)
        self.assertEqual(chunks[1].page_start, 1)
        self.assertEqual(chunks[1].page_end, 1)
        self.assertEqual(chunks[-1].page_start, 2)
        self.assertEqual(chunks[-1].page_end, 2)

    def test_build_pdf_chunks_uses_overlap_within_same_page(self) -> None:
        pages = [PdfPageText(page=1, text="X" * 1400, char_count=1400)]

        chunks = build_pdf_chunks(pages, target_chars=1000, overlap_chars=100)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].char_count, 1000)
        self.assertEqual(chunks[1].char_count, 500)

    def test_build_pdf_chunks_validates_limits(self) -> None:
        pages = [PdfPageText(page=1, text="abc", char_count=3)]

        with self.assertRaises(PdfIndexError):
            build_pdf_chunks(pages, target_chars=0)

        with self.assertRaises(PdfIndexError):
            build_pdf_chunks(pages, target_chars=100, overlap_chars=100)

    def test_get_document_index_dir_uses_doc_id_below_index_root(self) -> None:
        signature = PdfDocumentSignature(
            source_path=Path(r"D:\Docs\scan.pdf"),
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        index_root = Path(r"D:\Vault\.codexcli\index")

        document_index_dir = get_document_index_dir(index_root, signature)

        self.assertEqual(document_index_dir, index_root / "abc123")

    def test_ensure_document_index_dir_creates_doc_specific_directory(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        document_index_dir = ensure_document_index_dir(index_root, signature)

        self.assertTrue(document_index_dir.is_dir())
        self.assertEqual(document_index_dir, index_root / "abc123")

    def test_acquire_document_lock_creates_and_removes_lockfile(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        index_root = Path(temp_dir.name) / ".codexcli" / "index"
        lockfile = get_document_lockfile(index_root, signature)

        with acquire_document_lock(index_root, signature) as created_lockfile:
            self.assertEqual(created_lockfile, lockfile)
            self.assertTrue(lockfile.exists())
            content = lockfile.read_text(encoding="utf-8")
            self.assertIn("doc_id=abc123", content)

        self.assertFalse(lockfile.exists())

    def test_acquire_document_lock_rejects_parallel_lock(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        with acquire_document_lock(index_root, signature):
            with self.assertRaises(PdfIndexError) as ctx:
                with acquire_document_lock(index_root, signature):
                    self.fail("expected lock acquisition to fail")

        self.assertIn("bereits aktiv", str(ctx.exception))

    def test_open_index_db_creates_schema(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        connection = open_index_db(index_root, signature)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                ).fetchall()
            }
        finally:
            connection.close()

        self.assertIn("documents", tables)
        self.assertIn("chunks", tables)
        self.assertIn("chunks_fts", tables)

    def test_get_index_status_reports_missing_db_as_rebuild(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        status = get_index_status(index_root, signature)

        self.assertEqual(status, PdfIndexStatus(exists=False, needs_rebuild=True, chunk_count=0))

    def test_persist_pdf_index_writes_document_and_chunks(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        chunks = [
            PdfTextChunk(page_start=1, page_end=1, chunk_index=0, text="Alpha", char_count=5),
            PdfTextChunk(page_start=2, page_end=2, chunk_index=1, text="Beta", char_count=4),
        ]
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        db_path = persist_pdf_index(index_root, signature, chunks)

        self.assertTrue(db_path.exists())
        connection = sqlite3.connect(db_path)
        try:
            doc_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            stored = connection.execute(
                "SELECT page_start, page_end, chunk_index, text, char_count FROM chunks ORDER BY chunk_index"
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(doc_count, 1)
        self.assertEqual(chunk_count, 2)
        self.assertEqual(stored[0], (1, 1, 0, "Alpha", 5))
        self.assertEqual(stored[1], (2, 2, 1, "Beta", 4))

    def test_persist_pdf_index_is_idempotent_for_same_signature(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        chunks = [PdfTextChunk(page_start=1, page_end=1, chunk_index=0, text="Alpha", char_count=5)]
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        persist_pdf_index(index_root, signature, chunks)
        persist_pdf_index(index_root, signature, chunks)

        db_path = get_document_index_db_path(index_root, signature)
        connection = sqlite3.connect(db_path)
        try:
            doc_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(doc_count, 1)
        self.assertEqual(chunk_count, 1)

    def test_get_index_status_reports_no_rebuild_after_persist(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        chunks = [PdfTextChunk(page_start=1, page_end=1, chunk_index=0, text="Alpha", char_count=5)]
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        persist_pdf_index(index_root, signature, chunks)
        status = get_index_status(index_root, signature)

        self.assertTrue(status.exists)
        self.assertFalse(status.needs_rebuild)
        self.assertEqual(status.chunk_count, 1)

    def test_get_index_status_requests_rebuild_for_changed_signature(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        original_signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        changed_signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=999,
            mtime_utc="2024-05-01T12:05:00+00:00",
            doc_id="abc123",
        )
        chunks = [PdfTextChunk(page_start=1, page_end=1, chunk_index=0, text="Alpha", char_count=5)]
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        persist_pdf_index(index_root, original_signature, chunks)
        status = get_index_status(index_root, changed_signature)

        self.assertTrue(status.exists)
        self.assertTrue(status.needs_rebuild)
        self.assertEqual(status.chunk_count, 1)

    def test_build_retrieval_query_uses_distinct_terms(self) -> None:
        query = build_retrieval_query("Alpha alpha beta und x")
        self.assertEqual(query, '"alpha" OR "beta" OR "und"')

    def test_retrieve_pdf_chunks_returns_ranked_matches(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        chunks = [
            PdfTextChunk(page_start=1, page_end=1, chunk_index=0, text="Alpha Beta", char_count=10),
            PdfTextChunk(page_start=2, page_end=2, chunk_index=1, text="Gamma Delta", char_count=11),
        ]
        index_root = Path(temp_dir.name) / ".codexcli" / "index"
        persist_pdf_index(index_root, signature, chunks)

        results = retrieve_pdf_chunks(index_root, signature, "Bitte finde Alpha", top_k=5, max_context_chars=1000)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].page_start, 1)
        self.assertIn("Alpha", results[0].text)

    def test_retrieve_pdf_chunks_requires_existing_index(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        signature = PdfDocumentSignature(
            source_path=Path(temp_dir.name) / "scan.pdf",
            normalized_path=r"D:\Docs\scan.pdf",
            size_bytes=123,
            mtime_utc="2024-05-01T12:00:00+00:00",
            doc_id="abc123",
        )
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        with self.assertRaises(PdfIndexError) as ctx:
            retrieve_pdf_chunks(index_root, signature, "Alpha")

        self.assertIn("Bitte zuerst indexieren", str(ctx.exception))

    def test_format_retrieved_chunks_for_prompt_includes_pages(self) -> None:
        content, meta_lines = format_retrieved_chunks_for_prompt(
            Path(r"D:\Docs\scan.pdf"),
            [
                PdfRetrievedChunk(
                    page_start=3,
                    page_end=3,
                    chunk_index=7,
                    text="Wichtiger Ausschnitt",
                    char_count=19,
                    score=-1.0,
                )
            ],
        )

        self.assertIn("[PDF-Quelle 1]", content)
        self.assertIn("Seite 3", content)
        self.assertIn("Wichtiger Ausschnitt", content)
        self.assertTrue(any("Treffer" in line for line in meta_lines))

    def test_format_retrieved_chunks_for_prompt_marks_pdf_link_annotations(self) -> None:
        content, _meta_lines = format_retrieved_chunks_for_prompt(
            Path(r"D:\Docs\scan.pdf"),
            [
                PdfRetrievedChunk(
                    page_start=4,
                    page_end=4,
                    chunk_index=2,
                    text="Kurzer Kontext\n\nPDF-Links:\nhttps://example.com/video",
                    char_count=54,
                    score=-1.0,
                )
            ],
        )

        self.assertIn("PDF-Linkannotationen: ja", content)
        self.assertIn("Text:\nKurzer Kontext", content)
        self.assertIn("PDF-Links:\nhttps://example.com/video", content)

    def test_build_pdf_index_returns_page_and_chunk_counts(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "scan.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        with patch(
            "app.pdf_index.extract_pdf_pages_for_index",
            return_value=[
                PdfPageText(page=1, text="Alpha", char_count=5),
                PdfPageText(page=2, text="Beta", char_count=4),
            ],
        ):
            result = build_pdf_index(index_root, pdf_path)

        self.assertEqual(result.page_count, 2)
        self.assertEqual(result.chunk_count, 2)
        self.assertTrue(result.db_path.exists())

    def test_build_pdf_index_rejects_oversized_total_text(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        pdf_path = Path(temp_dir.name) / "scan.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")
        index_root = Path(temp_dir.name) / ".codexcli" / "index"

        oversized_text = "A" * (RAG_MAX_INDEX_TEXT_CHARS + 1)
        with patch(
            "app.pdf_index.extract_pdf_pages_for_index",
            return_value=[PdfPageText(page=1, text=oversized_text, char_count=len(oversized_text))],
        ):
            with self.assertRaises(PdfIndexError) as ctx:
                build_pdf_index(index_root, pdf_path)

        self.assertIn("zu gross", str(ctx.exception))
        self.assertIn("RAG_MAX_INDEX_TEXT_CHARS", str(ctx.exception))
        self.assertIn("app/config.py", str(ctx.exception))
