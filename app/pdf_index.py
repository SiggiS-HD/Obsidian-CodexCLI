from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import RAG_MAX_INDEX_TEXT_CHARS


class PdfIndexError(Exception):
    pass


@dataclass(frozen=True)
class PdfDocumentSignature:
    source_path: Path
    normalized_path: str
    size_bytes: int
    mtime_utc: str
    doc_id: str


LOCK_FILENAME = ".build.lock"
RAG_CHUNK_TARGET_CHARS = 1200
RAG_CHUNK_OVERLAP_CHARS = 120
RAG_TOP_K = 10
RAG_MAX_CONTEXT_CHARS = 18_000


@dataclass(frozen=True)
class PdfPageText:
    page: int
    text: str
    char_count: int


@dataclass(frozen=True)
class PdfTextChunk:
    page_start: int
    page_end: int
    chunk_index: int
    text: str
    char_count: int


@dataclass(frozen=True)
class PdfIndexStatus:
    exists: bool
    needs_rebuild: bool
    chunk_count: int


@dataclass(frozen=True)
class PdfIndexBuildResult:
    signature: PdfDocumentSignature
    page_count: int
    chunk_count: int
    db_path: Path


@dataclass(frozen=True)
class PdfRetrievedChunk:
    page_start: int
    page_end: int
    chunk_index: int
    text: str
    char_count: int
    score: float


def normalize_document_path(path: Path) -> str:
    text = str(path)

    if len(path.drive) == 2 and path.drive.endswith(":"):
        drive = path.drive.upper()
        text = drive + text[len(path.drive) :]

    text = text.replace("/", "\\")
    return text.rstrip("\\")


def build_pdf_document_signature(pdf_path: Path) -> PdfDocumentSignature:
    try:
        stat = pdf_path.stat()
    except OSError as error:
        raise PdfIndexError(f"PDF-Datei konnte nicht gelesen werden: {pdf_path} ({error})") from error

    normalized_path = normalize_document_path(pdf_path)
    mtime_utc = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    signature_text = f"{normalized_path}|{stat.st_size}|{mtime_utc}"
    doc_id = hashlib.sha256(signature_text.encode("utf-8")).hexdigest()

    return PdfDocumentSignature(
        source_path=pdf_path,
        normalized_path=normalized_path,
        size_bytes=stat.st_size,
        mtime_utc=mtime_utc,
        doc_id=doc_id,
    )


def normalize_pdf_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u00ad", "")
    normalized = normalized.replace("\u200b", "")
    normalized = normalized.replace("\t", " ")
    normalized = re.sub(r"[ ]{2,}", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def extract_pdf_pages_for_index(pdf_path: Path) -> list[PdfPageText]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise PdfIndexError(
            "PDF-Unterstuetzung ist nicht installiert. Bitte installiere 'pypdf' in der .venv."
        ) from error

    try:
        with pdf_path.open("rb") as handle:
            reader = PdfReader(handle)
            total_pages = len(reader.pages)

            pages: list[PdfPageText] = []
            for page_index in range(total_pages):
                page = reader.pages[page_index]
                page_text = page.extract_text() or ""
                page_text = normalize_pdf_text(page_text)

                if not page_text:
                    page_text = _extract_pdf_page_with_pdfminer(pdf_path, page_index)

                page_links = _extract_pdf_page_uri_links(page)
                if page_links:
                    links_text = "PDF-Links:\n" + "\n".join(page_links)
                    page_text = normalize_pdf_text(f"{page_text}\n\n{links_text}" if page_text else links_text)

                if not page_text:
                    continue

                pages.append(
                    PdfPageText(
                        page=page_index + 1,
                        text=page_text,
                        char_count=len(page_text),
                    )
                )
    except PdfIndexError:
        raise
    except Exception as error:
        raise PdfIndexError(f"PDF-Datei konnte nicht extrahiert werden: {pdf_path} ({error})") from error

    if pages:
        return pages

    raise PdfIndexError(
        "PDF enthaelt keinen extrahierbaren Text fuer den Index-Build. "
        "Scan-/OCR-PDFs sind fuer Phase 9 v1 noch nicht im Index-Flow abgedeckt."
    )


def _extract_pdf_page_uri_links(page) -> list[str]:
    if not hasattr(page, "get"):
        return []

    annots = page.get("/Annots")
    if not annots:
        return []

    links: list[str] = []
    seen: set[str] = set()

    for annot_ref in annots:
        try:
            annot = annot_ref.get_object()
        except Exception:
            continue

        if str(annot.get("/Subtype") or "") != "/Link":
            continue

        action = annot.get("/A")
        if not action or not hasattr(action, "get"):
            continue

        uri = action.get("/URI")
        uri_text = str(uri).strip() if uri is not None else ""
        if not uri_text or uri_text in seen:
            continue

        seen.add(uri_text)
        links.append(uri_text)

    return links


def _split_pdf_link_annotations(text: str) -> tuple[str, list[str]]:
    marker = "\nPDF-Links:\n"
    if marker in text:
        body, links_block = text.split(marker, 1)
    elif text.startswith("PDF-Links:\n"):
        body, links_block = "", text[len("PDF-Links:\n") :]
    else:
        return text, []

    links = [line.strip() for line in links_block.splitlines() if line.strip()]
    return body.strip(), links


def _extract_pdf_page_with_pdfminer(pdf_path: Path, page_index: int) -> str:
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
    except ImportError:
        return ""

    try:
        return normalize_pdf_text(
            pdfminer_extract_text(str(pdf_path), page_numbers=[page_index], maxpages=1) or ""
        )
    except Exception as error:
        raise PdfIndexError(
            f"PDF-Fallback-Extraktion fehlgeschlagen (Seite {page_index + 1}): {pdf_path} ({error})"
        ) from error


def build_pdf_chunks(
    pages: list[PdfPageText],
    *,
    target_chars: int = RAG_CHUNK_TARGET_CHARS,
    overlap_chars: int = RAG_CHUNK_OVERLAP_CHARS,
) -> list[PdfTextChunk]:
    if target_chars <= 0:
        raise PdfIndexError("target_chars muss groesser als 0 sein.")
    if overlap_chars < 0:
        raise PdfIndexError("overlap_chars darf nicht negativ sein.")
    if overlap_chars >= target_chars:
        raise PdfIndexError("overlap_chars muss kleiner als target_chars sein.")

    chunks: list[PdfTextChunk] = []
    chunk_index = 0

    for page in pages:
        if not page.text:
            continue

        start = 0
        text = page.text
        text_len = len(text)
        while start < text_len:
            end = min(text_len, start + target_chars)
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    PdfTextChunk(
                        page_start=page.page,
                        page_end=page.page,
                        chunk_index=chunk_index,
                        text=chunk_text,
                        char_count=len(chunk_text),
                    )
                )
                chunk_index += 1

            if end >= text_len:
                break

            start = max(start + 1, end - overlap_chars)

    return chunks


def ensure_index_root_available(index_root: Path) -> Path:
    try:
        index_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise PdfIndexError(
            "Index-Root ist nicht erreichbar oder konnte nicht angelegt werden: "
            f"{index_root} ({error})"
        ) from error

    try:
        if not index_root.is_dir():
            raise PdfIndexError(f"Index-Root ist kein Verzeichnis: {index_root}")
    except OSError as error:
        raise PdfIndexError(
            "Index-Root konnte nicht geprueft werden: "
            f"{index_root} ({error})"
        ) from error

    return index_root


def get_document_index_dir(index_root: Path, signature: PdfDocumentSignature) -> Path:
    return ensure_index_root_available(index_root) / signature.doc_id


def ensure_document_index_dir(index_root: Path, signature: PdfDocumentSignature) -> Path:
    document_index_dir = get_document_index_dir(index_root, signature)

    try:
        document_index_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise PdfIndexError(
            "Dokument-Indexordner konnte nicht angelegt werden: "
            f"{document_index_dir} ({error})"
        ) from error

    return document_index_dir


def get_document_index_db_path(index_root: Path, signature: PdfDocumentSignature) -> Path:
    return get_document_index_dir(index_root, signature) / "index.sqlite3"


def open_index_db(index_root: Path, signature: PdfDocumentSignature) -> sqlite3.Connection:
    db_path = get_document_index_db_path(index_root, signature)
    document_index_dir = ensure_document_index_dir(index_root, signature)

    try:
        connection = sqlite3.connect(db_path)
    except sqlite3.Error as error:
        raise PdfIndexError(
            "SQLite-Index konnte nicht geoeffnet werden: "
            f"{db_path} ({error})"
        ) from error

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_index_schema(connection)
    except sqlite3.Error as error:
        connection.close()
        raise PdfIndexError(
            "SQLite-Schema konnte nicht initialisiert werden: "
            f"{document_index_dir} ({error})"
        ) from error

    return connection


def ensure_index_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime_utc TEXT NOT NULL,
            hash TEXT NOT NULL,
            indexed_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chunks (
            doc_id TEXT NOT NULL,
            page_start INTEGER NOT NULL,
            page_end INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            PRIMARY KEY (doc_id, chunk_index),
            FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            content='chunks',
            content_rowid='rowid'
        );
        """
    )


def get_index_status(index_root: Path, signature: PdfDocumentSignature) -> PdfIndexStatus:
    db_path = get_document_index_db_path(index_root, signature)
    if not db_path.exists():
        return PdfIndexStatus(exists=False, needs_rebuild=True, chunk_count=0)

    connection = open_index_db(index_root, signature)
    try:
        document_row = connection.execute(
            """
            SELECT size_bytes, mtime_utc
            FROM documents
            WHERE doc_id = ?
            """,
            (signature.doc_id,),
        ).fetchone()

        if document_row is None:
            return PdfIndexStatus(exists=True, needs_rebuild=True, chunk_count=0)

        chunk_count_row = connection.execute(
            "SELECT COUNT(*) FROM chunks WHERE doc_id = ?",
            (signature.doc_id,),
        ).fetchone()
        chunk_count = int(chunk_count_row[0]) if chunk_count_row else 0

        size_bytes, mtime_utc = document_row
        needs_rebuild = (
            int(size_bytes) != signature.size_bytes
            or str(mtime_utc) != signature.mtime_utc
            or chunk_count == 0
        )

        return PdfIndexStatus(exists=True, needs_rebuild=needs_rebuild, chunk_count=chunk_count)
    finally:
        connection.close()


def persist_pdf_index(
    index_root: Path,
    signature: PdfDocumentSignature,
    chunks: list[PdfTextChunk],
) -> Path:
    if not chunks:
        raise PdfIndexError("Es koennen keine leeren Chunk-Listen persistiert werden.")

    with acquire_document_lock(index_root, signature):
        connection = open_index_db(index_root, signature)
        try:
            indexed_at_utc = datetime.now(tz=UTC).isoformat()
            doc_hash = hashlib.sha256(
                f"{signature.normalized_path}|{signature.size_bytes}|{signature.mtime_utc}".encode("utf-8")
            ).hexdigest()

            connection.execute("BEGIN")
            connection.execute("DELETE FROM chunks WHERE doc_id = ?", (signature.doc_id,))
            connection.execute("DELETE FROM documents WHERE doc_id = ?", (signature.doc_id,))
            connection.execute(
                """
                INSERT INTO documents (
                    doc_id, source_path, size_bytes, mtime_utc, hash, indexed_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    signature.doc_id,
                    signature.normalized_path,
                    signature.size_bytes,
                    signature.mtime_utc,
                    doc_hash,
                    indexed_at_utc,
                ),
            )
            connection.executemany(
                """
                INSERT INTO chunks (
                    doc_id, page_start, page_end, chunk_index, text, char_count
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        signature.doc_id,
                        chunk.page_start,
                        chunk.page_end,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.char_count,
                    )
                    for chunk in chunks
                ],
            )
            connection.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
            connection.commit()
        finally:
            connection.close()

    return get_document_index_db_path(index_root, signature)


def build_retrieval_query(query_text: str, *, max_terms: int = 12) -> str:
    normalized = normalize_pdf_text(query_text).lower()
    terms: list[str] = []
    for term in re.findall(r"\w+", normalized, flags=re.UNICODE):
        if len(term) < 2:
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= max_terms:
            break

    if not terms:
        return ""

    return " OR ".join(f'"{term}"' for term in terms)


def retrieve_pdf_chunks(
    index_root: Path,
    signature: PdfDocumentSignature,
    query_text: str,
    *,
    top_k: int = RAG_TOP_K,
    max_context_chars: int = RAG_MAX_CONTEXT_CHARS,
) -> list[PdfRetrievedChunk]:
    if top_k <= 0:
        raise PdfIndexError("top_k muss groesser als 0 sein.")
    if max_context_chars <= 0:
        raise PdfIndexError("max_context_chars muss groesser als 0 sein.")

    status = get_index_status(index_root, signature)
    if not status.exists:
        raise PdfIndexError(
            f"PDF-Index fehlt fuer {signature.source_path}. Bitte zuerst indexieren."
        )
    if status.needs_rebuild:
        raise PdfIndexError(
            f"PDF-Index ist veraltet fuer {signature.source_path}. Bitte zuerst neu indexieren."
        )

    fts_query = build_retrieval_query(query_text)
    if not fts_query:
        raise PdfIndexError("Prompt enthaelt zu wenig Suchbegriffe fuer PDF-Retrieval.")

    connection = open_index_db(index_root, signature)
    try:
        rows = connection.execute(
            """
            SELECT
                chunks.page_start,
                chunks.page_end,
                chunks.chunk_index,
                chunks.text,
                chunks.char_count,
                bm25(chunks_fts) AS score
            FROM chunks_fts
            JOIN chunks ON chunks.rowid = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
              AND chunks.doc_id = ?
            ORDER BY bm25(chunks_fts), chunks.chunk_index
            LIMIT ?
            """,
            (fts_query, signature.doc_id, top_k),
        ).fetchall()
    except sqlite3.Error as error:
        raise PdfIndexError(
            f"Retrieval aus dem PDF-Index ist fehlgeschlagen: {signature.source_path} ({error})"
        ) from error
    finally:
        connection.close()

    collected: list[PdfRetrievedChunk] = []
    total_chars = 0
    for row in rows:
        page_start, page_end, chunk_index, text, char_count, score = row
        if total_chars + int(char_count) > max_context_chars and collected:
            break

        collected.append(
            PdfRetrievedChunk(
                page_start=int(page_start),
                page_end=int(page_end),
                chunk_index=int(chunk_index),
                text=str(text),
                char_count=int(char_count),
                score=float(score),
            )
        )
        total_chars += int(char_count)

    return collected


def format_retrieved_chunks_for_prompt(
    pdf_path: Path,
    chunks: list[PdfRetrievedChunk],
) -> tuple[str, list[str]]:
    if not chunks:
        raise PdfIndexError(
            f"Keine relevanten Treffer im PDF-Index fuer {pdf_path}. Bitte Prompt praezisieren."
        )

    basename = pdf_path.name
    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        if chunk.page_start == chunk.page_end:
            page_label = f"Seite {chunk.page_start}"
        else:
            page_label = f"Seiten {chunk.page_start}-{chunk.page_end}"

        chunk_text, pdf_links = _split_pdf_link_annotations(chunk.text)
        block_lines = [
            f"[PDF-Quelle {index}]",
            f"Dokument: {basename}",
            f"Pfad: {pdf_path}",
            f"{page_label}",
            f"Chunk: {chunk.chunk_index}",
        ]
        if pdf_links:
            block_lines.append("PDF-Linkannotationen: ja")

        block_lines.append("Text:")
        block_lines.append(chunk_text or "(kein Fliesstext, nur PDF-Linkannotationen)")

        if pdf_links:
            block_lines.append("PDF-Links:")
            block_lines.extend(pdf_links)

        blocks.append(
            "\n".join(block_lines)
        )

    meta_lines = [
        f"- Retrieval: {len(chunks)} Treffer aus PDF-Index",
        f"- Quelle: {basename}",
    ]
    return "\n\n".join(blocks), meta_lines


def build_pdf_index(index_root: Path, pdf_path: Path) -> PdfIndexBuildResult:
    signature = build_pdf_document_signature(pdf_path)
    pages = extract_pdf_pages_for_index(pdf_path)
    chunks = build_pdf_chunks(pages)
    total_chars = sum(chunk.char_count for chunk in chunks)
    if total_chars > RAG_MAX_INDEX_TEXT_CHARS:
        raise PdfIndexError(
            "PDF-Index waere zu gross fuer v1. "
            f"Extrahierter Text: {total_chars} Zeichen, Limit {RAG_MAX_INDEX_TEXT_CHARS}. "
            "Falls du dieses PDF trotzdem indexieren willst, erhoehe "
            "`RAG_MAX_INDEX_TEXT_CHARS` in app/config.py."
        )
    db_path = persist_pdf_index(index_root, signature, chunks)
    return PdfIndexBuildResult(
        signature=signature,
        page_count=len(pages),
        chunk_count=len(chunks),
        db_path=db_path,
    )


def clear_pdf_index(index_root: Path, pdf_path: Path) -> bool:
    signature = build_pdf_document_signature(pdf_path)
    document_index_dir = get_document_index_dir(index_root, signature)

    if not document_index_dir.exists():
        return False

    try:
        shutil.rmtree(document_index_dir)
    except OSError as error:
        raise PdfIndexError(
            f"Dokument-Indexordner konnte nicht geloescht werden: {document_index_dir} ({error})"
        ) from error

    return True


def get_document_lockfile(index_root: Path, signature: PdfDocumentSignature) -> Path:
    return get_document_index_dir(index_root, signature) / LOCK_FILENAME


@contextmanager
def acquire_document_lock(index_root: Path, signature: PdfDocumentSignature):
    document_index_dir = ensure_document_index_dir(index_root, signature)
    lockfile = document_index_dir / LOCK_FILENAME

    try:
        fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise PdfIndexError(
            "Index-Build ist bereits aktiv oder wurde nicht sauber beendet: "
            f"{lockfile}"
        ) from error
    except OSError as error:
        raise PdfIndexError(
            "Lockfile konnte nicht angelegt werden: "
            f"{lockfile} ({error})"
        ) from error

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    [
                        f"doc_id={signature.doc_id}",
                        f"source_path={signature.normalized_path}",
                        f"mtime_utc={signature.mtime_utc}",
                    ]
                )
            )
        yield lockfile
    finally:
        try:
            lockfile.unlink(missing_ok=True)
        except OSError as error:
            raise PdfIndexError(
                "Lockfile konnte nicht entfernt werden: "
                f"{lockfile} ({error})"
            ) from error
