import hashlib
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app.append_workflow import append_response
from app.config import APP_NAME, TEXT_MODEL_FORCED, get_codex_cmd, get_index_root, get_runtime_tmp_root, get_text_model
from app.file_context import FileContextError, extract_prompt_references, resolve_prompt_contexts
from app.markdown_sections import (
    SECTION_PROMPT,
    append_info_to_note,
    extract_section,
    normalize_latex_delimiters_outside_code,
    normalize_math_symbols_outside_code,
    normalize_newlines,
)
from app.pdf_index import (
    PdfIndexError,
    build_pdf_document_signature,
    build_pdf_index,
    clear_pdf_index,
    get_document_index_db_path,
    get_index_status,
)
from app.summary_workflow import update_summary


def normalize_cli_path(value: str) -> Path:
    # Obsidian / cmd quoting can sometimes leave a stray quote at either end.
    normalized = value.strip().strip('"').strip("'")
    return Path(normalized)


def detect_vault_root_for_path(path: Path) -> Path:
    candidate = path if path.is_dir() else path.parent
    candidate = candidate.resolve()

    for directory in [candidate, *candidate.parents]:
        if (directory / ".obsidian").is_dir():
            return directory

    return candidate


def resolve_pdf_index_context(pdf_path: Path) -> tuple[Path, Path]:
    try:
        exists = pdf_path.exists()
    except OSError as error:
        raise PdfIndexError(f"Dateipfad nicht erreichbar: {pdf_path} ({error})") from error
    if not exists:
        raise PdfIndexError(f"Datei nicht gefunden: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PdfIndexError(f"Kein PDF-Pfad: {pdf_path}")

    vault_root = detect_vault_root_for_path(pdf_path)
    index_root = get_index_root(vault_root)
    return vault_root, index_root


def collect_pdf_paths_from_note_prompt(note_path: Path) -> list[Path]:
    if not note_path.exists():
        raise PdfIndexError(f"Datei nicht gefunden: {note_path}")

    try:
        note_text = normalize_newlines(note_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise PdfIndexError(f"Fehler beim Lesen der Note: {note_path} ({error})") from error

    prompt_text = extract_section(note_text, SECTION_PROMPT)
    if not prompt_text.strip():
        raise PdfIndexError("Der Abschnitt ## Prompt ist leer.")

    references = extract_prompt_references(prompt_text)
    if not references:
        return []

    try:
        pending_contexts = resolve_prompt_contexts(references, note_path)
    except FileContextError as error:
        raise PdfIndexError(str(error)) from error

    pdf_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for pending in pending_contexts:
        if pending.path.suffix.lower() != ".pdf":
            continue
        if pending.path in seen_paths:
            continue
        seen_paths.add(pending.path)
        pdf_paths.append(pending.path)

    return pdf_paths


def describe_runtime_tmp_root(runtime_tmp_root: Path) -> list[str]:
    lines = [f"- Runtime-Tmp-Root: `{runtime_tmp_root}`"]

    try:
        exists = runtime_tmp_root.exists()
    except OSError as error:
        lines.append(f"- Runtime-Tmp-Status: Fehler beim Zugriff ({error})")
        return lines

    if not exists:
        lines.append("- Runtime-Tmp-Status: noch nicht angelegt")
        return lines

    try:
        entries = sorted(runtime_tmp_root.iterdir(), key=lambda path: path.name.lower())
    except OSError as error:
        lines.append(f"- Runtime-Tmp-Status: Fehler beim Einlesen ({error})")
        return lines

    dir_entries = [entry for entry in entries if entry.is_dir()]
    file_entries = [entry for entry in entries if entry.is_file()]
    empty_dirs = [entry for entry in dir_entries if not any(entry.iterdir())]

    lines.append(f"- Runtime-Tmp-Status: vorhanden ({len(entries)} Eintraege)")
    lines.append(f"- Runtime-Tmp-Unterordner: {len(dir_entries)}")
    lines.append(f"- Runtime-Tmp-Dateien: {len(file_entries)}")
    lines.append(f"- Leere Runtime-Tmp-Unterordner: {len(empty_dirs)}")

    if entries:
        preview = ", ".join(entry.name for entry in entries[:5])
        if len(entries) > 5:
            preview += ", ..."
        lines.append(f"- Runtime-Tmp-Vorschau: `{preview}`")

    lines.append(
        "- Runtime-Tmp-Hinweis: Der eigentliche Codex-Run-Ordner wird normalerweise automatisch entfernt; "
        "liegengebliebene leere Unterordner koennen bei Bedarf manuell geloescht werden."
    )
    return lines


def read_note_text(note_path: Path) -> str:
    if not note_path.exists():
        raise PdfIndexError(f"Datei nicht gefunden: {note_path}")

    try:
        return normalize_newlines(note_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise PdfIndexError(f"Fehler beim Lesen der Note: {note_path} ({error})") from error


def run(args: list[str] | None = None) -> None:
    args = args or []

    if not args:
        print(f"{APP_NAME} is ready.")
        return

    command = args[0]

    if command == "diag":
        def sha256_of_file(path: Path) -> str:
            try:
                data = path.read_bytes()
            except Exception:
                return "<unreadable>"
            return hashlib.sha256(data).hexdigest()

        def safe_run(cmd: list[str], timeout_s: float = 2.0) -> tuple[int, str]:
            try:
                completed = subprocess.run(
                    cmd,
                    text=True,
                    capture_output=True,
                    timeout=timeout_s,
                    encoding="utf-8",
                    errors="replace",
                )
                out = (completed.stdout or "") + (completed.stderr or "")
                out = out.strip()
                return completed.returncode, out
            except FileNotFoundError:
                return 127, "<not found>"
            except Exception as error:
                return 1, f"<error: {error}>"

        def format_code_block(text: str) -> str:
            if not text:
                return "````\n<empty>\n````"
            # Prefer a safe fence that won't conflict with typical output.
            return f"````\n{text}\n````"

        def try_import_version(module_name: str) -> str:
            try:
                mod = __import__(module_name)
            except Exception as error:
                return f"<import failed: {error}>"
            version = getattr(mod, "__version__", None)
            return str(version) if version else "<unknown>"

        here = Path(__file__).resolve()
        repo_root = here.parents[1]

        targets = {
            "connector": here,
            "append_workflow": (repo_root / "app" / "append_workflow.py").resolve(),
            "markdown_sections": (repo_root / "app" / "markdown_sections.py").resolve(),
            "save_as": (repo_root / "app" / "save_as.py").resolve(),
            "file_context": (repo_root / "app" / "file_context.py").resolve(),
        }

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cwd = str(Path.cwd())
        hostname = platform.node() or os.environ.get("COMPUTERNAME", "") or "<unknown>"
        is_windows = os.name == "nt"

        note_path_str = ""
        if len(args) >= 2 and args[1].strip():
            try:
                note_path_str = str(normalize_cli_path(args[1]).resolve())
            except Exception:
                note_path_str = str(normalize_cli_path(args[1]))

        # Environment / OCR config
        tesseract_cmd = os.environ.get("CODEXCLI_TESSERACT_CMD", "")
        poppler_path = os.environ.get("CODEXCLI_POPPLER_PATH", "")
        ocr_lang = os.environ.get("CODEXCLI_OCR_LANG", "")

        codex_cmd_env = os.environ.get("CODEXCLI_CODEX_CMD", "")
        codex_cmd_effective = get_codex_cmd()
        text_model_env = os.environ.get("CODEXCLI_TEXT_MODEL", "")
        text_model_effective = get_text_model() or "<codex-cli-default>"
        text_model_source = (
            "TEXT_MODEL_FORCED"
            if TEXT_MODEL_FORCED
            else "CODEXCLI_TEXT_MODEL"
            if text_model_env.strip()
            else "codex-cli-default"
        )

        # Tool discovery
        tesseract_which = shutil.which("tesseract") or ""
        pdftoppm_which = shutil.which("pdftoppm") or ""

        codex_which = shutil.which("codex") or ""
        codex_cmd_which = shutil.which("codex.cmd") or ""

        tesseract_version_rc, tesseract_version_out = safe_run(["tesseract", "--version"], timeout_s=2.0)
        pdftoppm_version_rc, pdftoppm_version_out = safe_run(["pdftoppm", "-v"], timeout_s=2.0)

        codex_version_rc, codex_version_out = safe_run([codex_cmd_effective, "--version"], timeout_s=5.0)

        where_tesseract_out = ""
        where_pdftoppm_out = ""
        where_codex_out = ""
        where_codex_cmd_out = ""
        if is_windows:
            _, where_tesseract_out = safe_run(["where", "tesseract"], timeout_s=2.0)
            _, where_pdftoppm_out = safe_run(["where", "pdftoppm"], timeout_s=2.0)
            _, where_codex_out = safe_run(["where", "codex"], timeout_s=2.0)
            _, where_codex_cmd_out = safe_run(["where", "codex.cmd"], timeout_s=2.0)

        # Determine Vault root based on expected layout:
        #   <VAULT_ROOT>\<ADDON_DIR>\CodexCLI\...
        # This makes DEV/PROD comparable even if CWD differs.
        addon_dir = repo_root.parent
        vault_root = addon_dir.parent
        if not vault_root.exists() or vault_root == repo_root:
            vault_root = Path.cwd()
        runtime_tmp_root = get_runtime_tmp_root(vault_root)

        # Markdown output
        lines: list[str] = []
        out_note_path = vault_root / "CodexCLI_Connector.md"

        lines.append(f"# {APP_NAME} - Diagnose")
        lines.append("")
        lines.append(f"- Zeit: {now}")
        lines.append(f"- CWD: `{cwd}`")
        lines.append(f"- Hostname: `{hostname}`")
        lines.append(f"- Vault-Root: `{vault_root}`")
        lines.append(f"- AddOn-Dir: `{addon_dir}`")
        lines.append(f"- Output: `{out_note_path}`")
        if note_path_str:
            lines.append(f"- Note: `{note_path_str}`")
        lines.append("")

        lines.append("## Python")
        lines.append(f"- Executable: `{sys.executable}`")
        lines.append(f"- Version: `{sys.version.replace(chr(10), ' ')}`")
        lines.append(f"- Platform: `{platform.platform()}`")
        lines.append("")

        lines.append("## Codex CLI")
        lines.append(f"- `CODEXCLI_CODEX_CMD`: `{codex_cmd_env or '<unset>'}`")
        lines.append(f"- Effective command: `{codex_cmd_effective}`")
        lines.append(f"- `TEXT_MODEL_FORCED`: `{TEXT_MODEL_FORCED or '<unset>'}`")
        lines.append(f"- `CODEXCLI_TEXT_MODEL`: `{text_model_env or '<unset>'}`")
        lines.append(f"- Effective text model: `{text_model_effective}`")
        lines.append(f"- Text model source: `{text_model_source}`")
        lines.append("")
        lines.append(f"- `which codex`: `{codex_which or '<none>'}`")
        lines.append(f"- `which codex.cmd`: `{codex_cmd_which or '<none>'}`")
        lines.append("")
        if is_windows:
            lines.append("### where (Windows)")
            lines.append("- `where codex`:")
            lines.append(format_code_block(where_codex_out))
            lines.append("- `where codex.cmd`:")
            lines.append(format_code_block(where_codex_cmd_out))
            lines.append("")

        lines.append("### Version")
        lines.append(f"- `codex --version` (rc={codex_version_rc}):")
        lines.append(format_code_block(codex_version_out))
        lines.append("")

        lines.append("## Codebasis")
        lines.append(f"- Repo-Root: `{repo_root}`")
        lines.append("")
        for name, path in targets.items():
            lines.append(f"- `{name}`: `{path}`")
            lines.append(f"  - sha256: `{sha256_of_file(path)}`")
        lines.append("")

        lines.append("## Laufzeit-Artefakte")
        lines.extend(describe_runtime_tmp_root(runtime_tmp_root))
        lines.append("")

        lines.append("## Python-Pakete (relevant)")
        lines.append(f"- `pypdf`: `{try_import_version('pypdf')}`")
        lines.append(f"- `pdf2image`: `{try_import_version('pdf2image')}`")
        lines.append(f"- `pytesseract`: `{try_import_version('pytesseract')}`")
        lines.append("")

        lines.append("## OCR / Poppler")
        lines.append(f"- `CODEXCLI_TESSERACT_CMD`: `{tesseract_cmd or '<unset>'}`")
        lines.append(f"- `CODEXCLI_POPPLER_PATH`: `{poppler_path or '<unset>'}`")
        lines.append(f"- `CODEXCLI_OCR_LANG`: `{ocr_lang or '<unset>'}`")
        lines.append("")
        lines.append(f"- `which tesseract`: `{tesseract_which or '<none>'}`")
        lines.append(f"- `which pdftoppm`: `{pdftoppm_which or '<none>'}`")
        lines.append("")
        if is_windows:
            lines.append("### where (Windows)")
            lines.append("- `where tesseract`:")
            lines.append(format_code_block(where_tesseract_out))
            lines.append("- `where pdftoppm`:")
            lines.append(format_code_block(where_pdftoppm_out))
            lines.append("")

        lines.append("### Versionen")
        lines.append(f"- `tesseract --version` (rc={tesseract_version_rc}):")
        lines.append(format_code_block(tesseract_version_out))
        lines.append(f"- `pdftoppm -v` (rc={pdftoppm_version_rc}):")
        lines.append(format_code_block(pdftoppm_version_out))
        lines.append("")

        markdown = "\n".join(lines).rstrip() + "\n"

        # Write a vault-level note when invoked via Obsidian Shell Command.
        # This intentionally overwrites the file to keep it easy to compare DEV/PROD.
        try:
            out_note_path.write_text(markdown, encoding="utf-8")
        except Exception as error:
            # Still print diagnostics; include a note in the output.
            markdown += f"\n## Hinweis\n\nKonnte Output-Datei nicht schreiben: `{out_note_path}` ({error})\n"

        print(markdown)

        return

    if command == "append":
        if len(args) < 2:
            print("Fehler: Es wurde kein Dateipfad übergeben.")
            raise SystemExit(1)

        raise SystemExit(append_response(normalize_cli_path(args[1])))

    if command == "update_summary":
        if len(args) < 2:
            print("Fehler: Es wurde kein Dateipfad übergeben.")
            raise SystemExit(1)

        raise SystemExit(update_summary(normalize_cli_path(args[1])))

    if command == "fix_latex":
        if len(args) < 2:
            print("Fehler: Es wurde kein Dateipfad übergeben.")
            raise SystemExit(1)

        note_path = normalize_cli_path(args[1])
        if not note_path.exists():
            print(f"Fehler: Datei nicht gefunden: {note_path}")
            raise SystemExit(1)

        try:
            original_text = normalize_newlines(note_path.read_text(encoding="utf-8"))
        except Exception as error:
            print(f"Fehler beim Lesen der Datei: {error}")
            raise SystemExit(1)

        updated_text = normalize_latex_delimiters_outside_code(original_text)
        updated_text = normalize_math_symbols_outside_code(updated_text)
        if updated_text != original_text:
            try:
                note_path.write_text(updated_text, encoding="utf-8")
            except Exception as error:
                print(f"Fehler beim Schreiben der Datei: {error}")
                raise SystemExit(1)
            print(f"LaTeX-Begrenzer normalisiert: {note_path}")
        else:
            print(f"Keine Änderungen nötig: {note_path}")

        raise SystemExit(0)

    if command == "index_pdf":
        if len(args) < 2:
            print("Fehler: Es wurde kein PDF-Pfad übergeben.")
            raise SystemExit(1)

        pdf_path = normalize_cli_path(args[1])
        try:
            _vault_root, index_root = resolve_pdf_index_context(pdf_path)
            build_result = build_pdf_index(index_root, pdf_path)
        except PdfIndexError as error:
            print(f"Fehler: {error}")
            raise SystemExit(1)

        print(f"PDF-Index erstellt: {pdf_path}")
        print(f"- Seiten mit Text: {build_result.page_count}")
        print(f"- Chunks: {build_result.chunk_count}")
        print(f"- DB: {build_result.db_path}")
        raise SystemExit(0)

    if command == "index_status":
        if len(args) < 2:
            print("Fehler: Es wurde kein PDF-Pfad übergeben.")
            raise SystemExit(1)

        pdf_path = normalize_cli_path(args[1])
        try:
            _vault_root, index_root = resolve_pdf_index_context(pdf_path)
            signature = build_pdf_document_signature(pdf_path)
            status = get_index_status(index_root, signature)
            db_path = get_document_index_db_path(index_root, signature)
        except PdfIndexError as error:
            print(f"Fehler: {error}")
            raise SystemExit(1)

        print(f"PDF-Index-Status: {pdf_path}")
        print(f"- Exists: {status.exists}")
        print(f"- Needs rebuild: {status.needs_rebuild}")
        print(f"- Chunks: {status.chunk_count}")
        print(f"- DB: {db_path}")
        raise SystemExit(0)

    if command == "index_clear":
        if len(args) < 2:
            print("Fehler: Es wurde kein PDF-Pfad übergeben.")
            raise SystemExit(1)

        pdf_path = normalize_cli_path(args[1])
        try:
            _vault_root, index_root = resolve_pdf_index_context(pdf_path)
            was_deleted = clear_pdf_index(index_root, pdf_path)
        except PdfIndexError as error:
            print(f"Fehler: {error}")
            raise SystemExit(1)

        if was_deleted:
            print(f"PDF-Index geloescht: {pdf_path}")
        else:
            print(f"Kein PDF-Index vorhanden: {pdf_path}")
        raise SystemExit(0)

    if command == "index_note_pdfs":
        if len(args) < 2:
            print("Fehler: Es wurde kein Notizpfad übergeben.")
            raise SystemExit(1)

        note_path = normalize_cli_path(args[1])
        try:
            original_note_text = read_note_text(note_path)
            pdf_paths = collect_pdf_paths_from_note_prompt(note_path)
        except PdfIndexError as error:
            print(f"Fehler: {error}")
            raise SystemExit(1)

        if not pdf_paths:
            print("Keine PDF-Referenzen im Abschnitt ## Prompt gefunden.")
            raise SystemExit(1)

        indexed = 0
        skipped = 0
        print(f"{len(pdf_paths)} PDF-Datei(en) im Prompt gefunden.")

        for pdf_path in pdf_paths:
            try:
                _vault_root, index_root = resolve_pdf_index_context(pdf_path)
                signature = build_pdf_document_signature(pdf_path)
                status = get_index_status(index_root, signature)
                if status.exists and not status.needs_rebuild:
                    print(f"Index bereits aktuell: {pdf_path}")
                    skipped += 1
                    continue

                result = build_pdf_index(index_root, pdf_path)
                print(
                    f"Index erstellt: {pdf_path} "
                    f"(Seiten mit Text: {result.page_count}, Chunks: {result.chunk_count})"
                )
                indexed += 1
            except PdfIndexError as error:
                error_message = f"Fehler bei {pdf_path}: {error}"
                print(error_message)
                if original_note_text:
                    summary_lines = [
                        f"{len(pdf_paths)} PDF-Datei(en) im Prompt gefunden.",
                        f"Neu indexiert: {indexed}",
                        f"Unveraendert: {skipped}",
                        error_message,
                    ]
                    append_info_to_note(note_path, original_note_text, "\n".join(summary_lines), heading="Codex Index")
                raise SystemExit(1)

        summary_text = "\n".join(
            [
                f"{len(pdf_paths)} PDF-Datei(en) im Prompt gefunden.",
                f"Neu indexiert: {indexed}",
                f"Unveraendert: {skipped}",
            ]
        )
        if original_note_text:
            append_info_to_note(note_path, original_note_text, summary_text, heading="Codex Index")

        print(f"Fertig. Neu indexiert: {indexed}, unverändert: {skipped}.")
        raise SystemExit(0)

    if command == "index_note_status":
        if len(args) < 2:
            print("Fehler: Es wurde kein Notizpfad übergeben.")
            raise SystemExit(1)

        note_path = normalize_cli_path(args[1])
        try:
            original_note_text = read_note_text(note_path)
            pdf_paths = collect_pdf_paths_from_note_prompt(note_path)
        except PdfIndexError as error:
            print(f"Fehler: {error}")
            raise SystemExit(1)

        if not pdf_paths:
            print("Keine PDF-Referenzen im Abschnitt ## Prompt gefunden.")
            raise SystemExit(1)

        print(f"{len(pdf_paths)} PDF-Datei(en) im Prompt gefunden.")
        summary_lines = [f"{len(pdf_paths)} PDF-Datei(en) im Prompt gefunden."]

        for pdf_path in pdf_paths:
            try:
                _vault_root, index_root = resolve_pdf_index_context(pdf_path)
                signature = build_pdf_document_signature(pdf_path)
                status = get_index_status(index_root, signature)
                print(f"Status: {pdf_path}")
                print(f"- Exists: {status.exists}")
                print(f"- Needs rebuild: {status.needs_rebuild}")
                print(f"- Chunks: {status.chunk_count}")
                summary_lines.extend(
                    [
                        f"Status: {pdf_path}",
                        f"  Exists: {status.exists}",
                        f"  Needs rebuild: {status.needs_rebuild}",
                        f"  Chunks: {status.chunk_count}",
                    ]
                )
            except PdfIndexError as error:
                print(f"Fehler bei {pdf_path}: {error}")
                raise SystemExit(1)

        append_info_to_note(
            note_path,
            original_note_text,
            "\n".join(summary_lines),
            heading="Codex Index Status",
        )
        raise SystemExit(0)

    if command == "index_note_clear":
        if len(args) < 2:
            print("Fehler: Es wurde kein Notizpfad übergeben.")
            raise SystemExit(1)

        note_path = normalize_cli_path(args[1])
        try:
            original_note_text = read_note_text(note_path)
            pdf_paths = collect_pdf_paths_from_note_prompt(note_path)
        except PdfIndexError as error:
            print(f"Fehler: {error}")
            raise SystemExit(1)

        if not pdf_paths:
            print("Keine PDF-Referenzen im Abschnitt ## Prompt gefunden.")
            raise SystemExit(1)

        deleted = 0
        missing = 0
        print(f"{len(pdf_paths)} PDF-Datei(en) im Prompt gefunden.")
        summary_lines = [f"{len(pdf_paths)} PDF-Datei(en) im Prompt gefunden."]

        for pdf_path in pdf_paths:
            try:
                _vault_root, index_root = resolve_pdf_index_context(pdf_path)
                was_deleted = clear_pdf_index(index_root, pdf_path)
                if was_deleted:
                    print(f"PDF-Index geloescht: {pdf_path}")
                    summary_lines.append(f"Geloescht: {pdf_path}")
                    deleted += 1
                else:
                    print(f"Kein PDF-Index vorhanden: {pdf_path}")
                    summary_lines.append(f"Nicht vorhanden: {pdf_path}")
                    missing += 1
            except PdfIndexError as error:
                print(f"Fehler bei {pdf_path}: {error}")
                raise SystemExit(1)

        summary_lines.extend([f"Geloescht: {deleted}", f"Nicht vorhanden: {missing}"])
        append_info_to_note(
            note_path,
            original_note_text,
            "\n".join(summary_lines),
            heading="Codex Index Clear",
        )
        raise SystemExit(0)

    print(f"Fehler: Unbekannte Funktion: {command}")
    raise SystemExit(1)
