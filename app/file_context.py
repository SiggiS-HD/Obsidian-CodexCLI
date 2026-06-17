import csv
import io
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.config import (
    PDF_OCR_DPI,
    PDF_OCR_MAX_PAGES,
    get_index_root,
    get_pdf_ocr_lang,
    get_pdf_ocr_poppler_path,
    get_pdf_ocr_tesseract_cmd,
)
from app.pdf_index import (
    PdfIndexError,
    build_pdf_document_signature,
    format_retrieved_chunks_for_prompt,
    retrieve_pdf_chunks,
)

SUPPORTED_TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".pdf"}
SUPPORTED_IMAGE_EXTENSIONS = {".png"}
KNOWN_BUT_UNSUPPORTED_EXTENSIONS: set[str] = set()
MAX_FILE_BYTES = 50_000
MAX_TOTAL_FILE_BYTES = 150_000

MAX_PNG_ATTACHMENTS = 4

MAX_PDF_PAGES = 20
MAX_PDF_TEXT_CHARS = 20_000

MAX_CSV_ROWS = 50
MAX_CSV_COLS = 20
MAX_CSV_CELL_CHARS = 200


class FileContextError(Exception):
    pass


def _looks_like_poppler_pdftoppm(executable_path: str) -> bool:
    lowered = (executable_path or "").lower()
    return "poppler" in lowered and "pdftoppm" in lowered


def _build_ocr_no_text_hints(poppler_path: str | None) -> str:
    hints: list[str] = []

    if poppler_path:
        hints.append(f"Hinweis: CODEXCLI_POPPLER_PATH ist gesetzt: {poppler_path}.")
        return " ".join(hints)

    hints.append(
        "Hinweis: CODEXCLI_POPPLER_PATH ist nicht gesetzt; pdf2image nutzt 'pdftoppm' aus dem PATH."
    )

    if os.name != "nt":
        return " ".join(hints)

    pdftoppm_first = shutil.which("pdftoppm")
    if pdftoppm_first:
        hints.append(f"Hinweis: Erstes 'pdftoppm' im PATH: {pdftoppm_first}.")
        lowered = pdftoppm_first.lower()
        if ("xpdf" in lowered or "miktex" in lowered) and not _looks_like_poppler_pdftoppm(pdftoppm_first):
            hints.append(
                "Hinweis: Das sieht nicht nach Poppler aus (Xpdf/MiKTeX kann Poppler ueberschattet). "
                "Setze CODEXCLI_POPPLER_PATH auf den Poppler-Ordner '...\\Library\\bin'."
            )

    try:
        where_out = subprocess.check_output(["where", "pdftoppm"], text=True, stderr=subprocess.STDOUT)
        candidates = [line.strip() for line in where_out.splitlines() if line.strip()]
        poppler_candidates = [c for c in candidates if _looks_like_poppler_pdftoppm(c)]
        if poppler_candidates:
            suggested_dir = str(Path(poppler_candidates[0]).parent)
            hints.append(f"Hinweis: Poppler-Treffer gefunden; geeigneter CODEXCLI_POPPLER_PATH: {suggested_dir}.")
    except Exception:
        pass

    return " ".join(hints)


def is_unc_path(path: Path) -> bool:
    return str(path).startswith("\\\\")


def safe_resolve(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except Exception:
        return path


@dataclass(frozen=True)
class PromptReference:
    raw_target: str
    kind: str
    position: int


@dataclass(frozen=True)
class ResolvedFileContext:
    path: Path
    file_type: str
    content: str
    source_label: str
    meta_lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CollectedPromptContext:
    file_context_block: str
    image_paths: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class CollectedPromptContextV2:
        """Collected context with optional `### Daten` split.

        - If data_mode_active is False, file_context_block contains the legacy combined block and
            instruction_context_block/data_context_block are empty.
        - If data_mode_active is True, instruction_context_block and data_context_block are populated and
            file_context_block is empty.
        """

        file_context_block: str
        instruction_context_block: str
        data_context_block: str
        image_paths: list[Path] = field(default_factory=list)
        data_mode_active: bool = False


def collect_prompt_context(prompt_text: str, note_path: Path) -> CollectedPromptContext:
    references = extract_prompt_references(prompt_text)

    if not references:
        return CollectedPromptContext(file_context_block="", image_paths=[])

    contexts: list[ResolvedFileContext] = []
    image_paths: list[Path] = []
    seen_paths: set[Path] = set()
    total_bytes = 0

    for context in resolve_prompt_contexts(references, note_path):
        if context.path in seen_paths:
            continue

        suffix = context.path.suffix.lower()
        if suffix in SUPPORTED_IMAGE_EXTENSIONS:
            if len(image_paths) >= MAX_PNG_ATTACHMENTS:
                raise FileContextError(
                    f"Zu viele PNG-Dateien im Prompt (Limit {MAX_PNG_ATTACHMENTS})."
                )

            seen_paths.add(context.path)
            image_paths.append(context.path)
            continue

        if suffix == ".pdf":
            content, meta_lines = render_pdf_retrieval_for_prompt(context.path, prompt_text, note_path)
            prompt_bytes = len(content.encode("utf-8", errors="replace"))

            if total_bytes + prompt_bytes > MAX_TOTAL_FILE_BYTES:
                raise FileContextError(
                    "Die Summe der referenzierten Dateien ist zu gross fuer den Prompt "
                    f"(Limit {MAX_TOTAL_FILE_BYTES} Bytes)."
                )

            total_bytes += prompt_bytes
            seen_paths.add(context.path)

            contexts.append(
                ResolvedFileContext(
                    path=context.path,
                    file_type=suffix,
                    content=content,
                    source_label=context.source_label,
                    meta_lines=meta_lines,
                )
            )
            continue

        file_bytes, file_size, was_truncated = read_file_bytes_for_prompt(context.path, suffix)
        prompt_bytes = len(file_bytes)

        if total_bytes + prompt_bytes > MAX_TOTAL_FILE_BYTES:
            raise FileContextError(
                "Die Summe der referenzierten Dateien ist zu gross fuer den Prompt "
                f"(Limit {MAX_TOTAL_FILE_BYTES} Bytes)."
            )

        total_bytes += prompt_bytes
        seen_paths.add(context.path)

        content, meta_lines = render_file_content_for_prompt(file_bytes, suffix)
        if was_truncated:
            meta_lines = [*meta_lines, f"- Hinweis: Datei wurde fuer den Prompt nach {MAX_FILE_BYTES} Bytes abgeschnitten."]

        contexts.append(
            ResolvedFileContext(
                path=context.path,
                file_type=suffix,
                content=content,
                source_label=context.source_label,
                meta_lines=meta_lines,
            )
        )

    return CollectedPromptContext(file_context_block=build_file_context_block(contexts), image_paths=image_paths)


_DATA_SECTION_HEADING_RE = re.compile(r"(?m)^###\s*Daten\s*$", flags=re.IGNORECASE)


def split_prompt_by_data_section(prompt_text: str) -> tuple[str, str, bool]:
    """Split a prompt (body of `## Prompt`) into instruction-area and data-area.

    Returns: (instruction_area_text, data_area_text, data_mode_active)
    """

    if not prompt_text:
        return "", "", False

    text = prompt_text.replace("\r\n", "\n").replace("\r", "\n")
    match = _DATA_SECTION_HEADING_RE.search(text)
    if not match:
        return text, "", False

    instruction_area = text[: match.start()].rstrip()
    after = match.end()
    if after < len(text) and text[after] == "\n":
        after += 1
    data_area = text[after:].strip()
    return instruction_area, data_area, True


def collect_prompt_context_v2(prompt_text: str, note_path: Path) -> CollectedPromptContextV2:
    """Collect prompt context with Phase-8 `### Daten` support.

    - References above `### Daten` are treated as instruction sources.
    - References under `### Daten` are treated as data sources.
    - `.png` is always treated as data (image attachment), regardless of where it appears.
    """

    instruction_area, data_area, data_mode_active = split_prompt_by_data_section(prompt_text)
    if not data_mode_active:
        legacy = collect_prompt_context(prompt_text, note_path)
        return CollectedPromptContextV2(
            file_context_block=legacy.file_context_block,
            instruction_context_block="",
            data_context_block="",
            image_paths=legacy.image_paths,
            data_mode_active=False,
        )

    instruction_refs = extract_prompt_references(instruction_area)
    data_refs = extract_prompt_references(data_area)

    if not instruction_refs and not data_refs:
        return CollectedPromptContextV2(
            file_context_block="",
            instruction_context_block="",
            data_context_block="",
            image_paths=[],
            data_mode_active=True,
        )

    instruction_contexts: list[ResolvedFileContext] = []
    data_contexts: list[ResolvedFileContext] = []
    image_paths: list[Path] = []
    seen_paths: set[Path] = set()
    total_bytes = 0

    def add_pending(pending: PendingContext, desired_role: str) -> None:
        nonlocal total_bytes

        if pending.path in seen_paths:
            return

        suffix = pending.path.suffix.lower()
        role = desired_role
        if suffix in SUPPORTED_IMAGE_EXTENSIONS:
            role = "data"

        if suffix in SUPPORTED_IMAGE_EXTENSIONS:
            if len(image_paths) >= MAX_PNG_ATTACHMENTS:
                raise FileContextError(
                    f"Zu viele PNG-Dateien im Prompt (Limit {MAX_PNG_ATTACHMENTS})."
                )

            seen_paths.add(pending.path)
            image_paths.append(pending.path)
            return

        if suffix == ".pdf":
            content, meta_lines = render_pdf_retrieval_for_prompt(pending.path, prompt_text, note_path)
            prompt_bytes = len(content.encode("utf-8", errors="replace"))

            if total_bytes + prompt_bytes > MAX_TOTAL_FILE_BYTES:
                raise FileContextError(
                    "Die Summe der referenzierten Dateien ist zu gross fuer den Prompt "
                    f"(Limit {MAX_TOTAL_FILE_BYTES} Bytes)."
                )

            total_bytes += prompt_bytes
            seen_paths.add(pending.path)

            resolved = ResolvedFileContext(
                path=pending.path,
                file_type=suffix,
                content=content,
                source_label=pending.source_label,
                meta_lines=meta_lines,
            )
            if role == "instruction":
                instruction_contexts.append(resolved)
            else:
                data_contexts.append(resolved)
            return

        file_bytes, _file_size, was_truncated = read_file_bytes_for_prompt(pending.path, suffix)
        prompt_bytes = len(file_bytes)

        if total_bytes + prompt_bytes > MAX_TOTAL_FILE_BYTES:
            raise FileContextError(
                "Die Summe der referenzierten Dateien ist zu gross fuer den Prompt "
                f"(Limit {MAX_TOTAL_FILE_BYTES} Bytes)."
            )

        total_bytes += prompt_bytes
        seen_paths.add(pending.path)

        content, meta_lines = render_file_content_for_prompt(file_bytes, suffix)
        if was_truncated:
            meta_lines = [
                *meta_lines,
                f"- Hinweis: Datei wurde fuer den Prompt nach {MAX_FILE_BYTES} Bytes abgeschnitten.",
            ]

        resolved = ResolvedFileContext(
            path=pending.path,
            file_type=suffix,
            content=content,
            source_label=pending.source_label,
            meta_lines=meta_lines,
        )
        if role == "instruction":
            instruction_contexts.append(resolved)
        else:
            data_contexts.append(resolved)

    def process_reference(reference: PromptReference, desired_role: str) -> None:
        for pending in resolve_prompt_contexts([reference], note_path):
            add_pending(pending, desired_role)

    for reference in instruction_refs:
        process_reference(reference, desired_role="instruction")

    for reference in data_refs:
        process_reference(reference, desired_role="data")

    instruction_block = build_file_context_block_with_heading("Zusätzliche Anweisungsquellen:", instruction_contexts)
    data_block = build_data_context_block(data_contexts, image_paths)

    return CollectedPromptContextV2(
        file_context_block="",
        instruction_context_block=instruction_block,
        data_context_block=data_block,
        image_paths=image_paths,
        data_mode_active=True,
    )


def collect_file_context_block(prompt_text: str, note_path: Path) -> str:
    return collect_prompt_context(prompt_text, note_path).file_context_block


def build_file_context_block_with_heading(heading: str, contexts: list[ResolvedFileContext]) -> str:
    if not contexts:
        return ""

    blocks: list[str] = []
    for index, context in enumerate(contexts, start=1):
        content = context.content if context.content else "(Datei ist leer.)"

        extra_meta = []
        if context.meta_lines:
            extra_meta = list(context.meta_lines)

        blocks.append(
            "\n".join(
                [
                    f"Quelle {index}:",
                    f"- Herkunft: {context.source_label}",
                    f"- Pfad: {context.path}",
                    f"- Typ: {context.file_type}",
                    *extra_meta,
                    "- Inhalt:",
                    content,
                ]
            )
        )

    return heading + "\n\n" + "\n\n".join(blocks)


def build_data_context_block(contexts: list[ResolvedFileContext], image_paths: list[Path]) -> str:
    parts: list[str] = []

    text_part = build_file_context_block_with_heading(
        "Zusätzliche Datenquellen (untrusted input):",
        contexts,
    )
    if text_part:
        parts.append(text_part)

    if image_paths:
        image_lines = [
            "Bild-Datenquellen (PNG Attachments):",
            *[f"- Pfad: {path}" for path in image_paths],
        ]
        parts.append("\n".join(image_lines))

    return "\n\n".join(parts).strip()


@dataclass(frozen=True)
class PendingContext:
    path: Path
    source_label: str


def resolve_prompt_contexts(references: list[PromptReference], note_path: Path) -> list[PendingContext]:
    contexts: list[PendingContext] = []

    for reference in references:
        resolved_path = resolve_reference(reference, note_path)
        source_label = "Direkt aus ## Prompt"

        if should_expand_as_moc(reference, resolved_path):
            contexts.extend(expand_moc_file(resolved_path, note_path))
            continue

        contexts.append(PendingContext(path=resolved_path, source_label=source_label))

    return contexts


def should_expand_as_moc(reference: PromptReference, resolved_path: Path) -> bool:
    return resolved_path.suffix.lower() == ".md" and is_moc_file(resolved_path)


def expand_moc_file(moc_path: Path, note_path: Path) -> list[PendingContext]:
    moc_text = moc_path.read_text(encoding="utf-8")
    entries = parse_moc_entries(moc_text)
    contexts: list[PendingContext] = []

    for index, entry in enumerate(entries, start=1):
        reference = extract_single_moc_reference(entry, moc_path)
        resolved_path = resolve_reference(reference, note_path, base_path=moc_path)
        if resolved_path.suffix.lower() == ".md" and is_potential_moc_content(resolved_path):
            raise FileContextError(f"Verschachtelte MOC-Dateien werden noch nicht unterstuetzt: {resolved_path}")

        contexts.append(
            PendingContext(
                path=resolved_path,
                source_label=f"MOC {moc_path.name}, Position {index}",
            )
        )

    return contexts


def parse_moc_entries(moc_text: str) -> list[str]:
    entries: list[str] = []
    for line in moc_text.splitlines():
        match = re.match(r"^\s*(\d+)\.\s+(.+?)\s*$", line)
        if not match:
            continue

        if line[: len(line) - len(line.lstrip())]:
            raise FileContextError("Unterlisten in MOC-Dateien werden noch nicht unterstuetzt.")

        entries.append(match.group(2))

    return entries


def extract_single_moc_reference(entry_text: str, moc_path: Path) -> PromptReference:
    references = extract_prompt_references(entry_text)
    if len(references) != 1:
        raise FileContextError(
            f"Ungueltiger MOC-Eintrag in {moc_path.name}: Es wird genau eine Dateireferenz pro Listeneintrag erwartet."
        )

    reference = references[0]
    if reference.kind == "absolute_path":
        raise FileContextError(
            f"Ungueltiger MOC-Eintrag in {moc_path.name}: Absolute Pfade werden in MOC-Dateien im ersten Schnitt nicht unterstuetzt."
        )

    extra_text = remove_reference_markup(entry_text, reference).strip()
    if extra_text:
        raise FileContextError(
            f"Ungueltiger MOC-Eintrag in {moc_path.name}: Pro Listeneintrag ist nur eine Dateireferenz erlaubt."
        )

    return reference


def remove_reference_markup(entry_text: str, reference: PromptReference) -> str:
    if reference.kind == "wikilink":
        return re.sub(r"\[\[[^\]]+\]\]", "", entry_text, count=1)

    if reference.kind == "markdown_link":
        return re.sub(r"\[[^\]]+\]\([^)]+\)", "", entry_text, count=1)

    return entry_text


def is_potential_moc_content(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False

    return is_moc_text(text)


def is_moc_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False

    return is_moc_text(text)


def is_moc_text(text: str) -> bool:
    first_heading = extract_first_markdown_heading(text)
    if first_heading is None:
        return False

    if not re.search(r"\bMOC\b", first_heading, flags=re.IGNORECASE):
        return False

    return bool(re.search(r"(?m)^\s*\d+\.\s+", text))


def extract_first_markdown_heading(text: str) -> str | None:
    lines = text.splitlines()
    index = 0

    # Optional YAML front matter at the very top.
    if index < len(lines) and lines[index].strip() == "---":
        index += 1
        while index < len(lines) and lines[index].strip() != "---":
            index += 1
        if index < len(lines) and lines[index].strip() == "---":
            index += 1

    while index < len(lines) and not lines[index].strip():
        index += 1

    heading_match = None
    while index < len(lines) and heading_match is None:
        heading_match = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", lines[index])
        if heading_match is None and lines[index].strip():
            return None
        index += 1

    if heading_match is None:
        return None

    return heading_match.group(1).strip()


def extract_prompt_references(prompt_text: str) -> list[PromptReference]:
    references: list[PromptReference] = []
    occupied_ranges: list[tuple[int, int]] = []

    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", prompt_text):
        references.append(
            PromptReference(
                raw_target=match.group(1).strip(),
                kind="markdown_link",
                position=match.start(),
            )
        )
        occupied_ranges.append(match.span())

    for match in re.finditer(r"\[\[([^\]]+)\]\]", prompt_text):
        references.append(
            PromptReference(
                raw_target=match.group(1).strip(),
                kind="wikilink",
                position=match.start(),
            )
        )
        occupied_ranges.append(match.span())

    unc_path_pattern = r"(?P<path>\\\\[^\r\n<>:\"|?*]+?\.(?:md|txt|csv|pdf|png))"
    for match in re.finditer(unc_path_pattern, prompt_text, flags=re.IGNORECASE):
        if any(start <= match.start() < end for start, end in occupied_ranges):
            continue

        references.append(
            PromptReference(
                raw_target=match.group("path").strip(),
                kind="unc_path",
                position=match.start(),
            )
        )

    absolute_path_pattern = r"(?P<path>[A-Za-z]:\\[^\r\n<>:\"|?*]+?\.(?:md|txt|csv|pdf|png))"
    for match in re.finditer(absolute_path_pattern, prompt_text, flags=re.IGNORECASE):
        if any(start <= match.start() < end for start, end in occupied_ranges):
            continue

        references.append(
            PromptReference(
                raw_target=match.group("path").strip(),
                kind="absolute_path",
                position=match.start(),
            )
        )

    references.sort(key=lambda item: item.position)
    return references


def resolve_reference(reference: PromptReference, note_path: Path, base_path: Path | None = None) -> Path:
    base_path = base_path or note_path

    if reference.kind == "wikilink":
        return resolve_wikilink(reference.raw_target, note_path)

    target_path = normalize_path_target(reference.raw_target, base_path)
    return validate_resolved_path(target_path)


def normalize_path_target(raw_target: str, note_path: Path) -> Path:
    target = raw_target.strip().strip('"').strip("'")
    candidate = Path(target)

    if candidate.is_absolute():
        return safe_resolve(candidate)

    return safe_resolve(note_path.parent / candidate)


def resolve_wikilink(raw_target: str, note_path: Path) -> Path:
    target = raw_target.split("|", maxsplit=1)[0].split("#", maxsplit=1)[0].strip()
    if not target:
        raise FileContextError("Leerer Obsidian-WikiLink im Abschnitt ## Prompt.")

    vault_root = detect_vault_root(note_path)
    candidate = Path(target.replace("/", "\\"))
    candidate_text = str(candidate)
    candidate_lower = candidate_text.lower()
    allowed_wikilink_extensions = {".md", ".png", ".pdf"}

    # Obsidian WikiLinks typically omit the extension, but filenames can contain dots.
    # Example: [[Urologe_3_14.4.2026]] should resolve to Urologe_3_14.4.2026.md (not treat ".2026" as extension).
    if candidate.suffix.lower() in allowed_wikilink_extensions:
        pass
    elif not (candidate_lower.endswith(".md") or candidate_lower.endswith(".png") or candidate_lower.endswith(".pdf")):
        suffix = candidate.suffix
        suffix_body = suffix[1:] if suffix.startswith(".") else suffix
        looks_like_extension = bool(suffix_body) and any(char.isalpha() for char in suffix_body)
        if looks_like_extension:
            raise FileContextError(f"WikiLink verweist auf einen nicht unterstuetzten Dateityp: {raw_target}")

        matches_without_extension: list[Path] = []
        for extension in [".md", ".pdf", ".png"]:
            extension_candidate = (vault_root / Path(candidate_text + extension)).resolve()
            if extension_candidate.exists() and is_within_root(extension_candidate, vault_root):
                matches_without_extension.append(extension_candidate)

        if len(matches_without_extension) == 1:
            return validate_resolved_path(matches_without_extension[0])
        if len(matches_without_extension) > 1:
            formatted_matches = ", ".join(str(path) for path in matches_without_extension[:5])
            raise FileContextError(
                f"WikiLink ist mehrdeutig: [[{raw_target}]]. Gefundene Dateien: {formatted_matches}"
            )

        candidate = Path(candidate_text + ".md")

    direct_candidate = (vault_root / candidate).resolve()
    if direct_candidate.exists() and is_within_root(direct_candidate, vault_root):
        return validate_resolved_path(direct_candidate)

    if len(candidate.parts) > 1:
        raise FileContextError(f"WikiLink konnte nicht aufgeloest werden: [[{raw_target}]]")

    matches = sorted(
        path.resolve()
        for path in vault_root.rglob(candidate.name)
        if is_within_root(path.resolve(), vault_root)
    )
    if not matches:
        raise FileContextError(f"WikiLink konnte nicht aufgeloest werden: [[{raw_target}]]")

    if len(matches) > 1:
        formatted_matches = ", ".join(str(path) for path in matches[:5])
        raise FileContextError(
            f"WikiLink ist mehrdeutig: [[{raw_target}]]. Gefundene Dateien: {formatted_matches}"
        )

    return validate_resolved_path(matches[0].resolve())


def detect_vault_root(note_path: Path) -> Path:
    note_directory = note_path.parent.resolve()

    for directory in [note_directory, *note_directory.parents]:
        if (directory / ".obsidian").is_dir():
            return directory

    return note_directory


def is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_resolved_path(path: Path) -> Path:
    suffix = path.suffix.lower()
    if suffix in KNOWN_BUT_UNSUPPORTED_EXTENSIONS:
        raise FileContextError(f"Dateityp ist bekannt, wird aber noch nicht unterstuetzt: {path}")

    if suffix not in SUPPORTED_TEXT_EXTENSIONS and suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        raise FileContextError(f"Nicht unterstuetzter Dateityp: {path}")

    try:
        exists = path.exists()
    except OSError as error:
        if is_unc_path(path):
            raise FileContextError(f"NAS/UNC-Pfad nicht erreichbar: {path} ({error})") from error
        raise FileContextError(f"Dateipfad konnte nicht geprueft werden: {path} ({error})") from error

    if not exists:
        if is_unc_path(path):
            raise FileContextError(f"NAS/UNC-Pfad nicht erreichbar oder Datei nicht gefunden: {path}")
        raise FileContextError(f"Datei nicht gefunden: {path}")

    try:
        if not path.is_file():
            raise FileContextError(f"Pfad ist keine Datei: {path}")
    except OSError as error:
        if is_unc_path(path):
            raise FileContextError(f"NAS/UNC-Pfad nicht erreichbar: {path} ({error})") from error
        raise FileContextError(f"Dateipfad konnte nicht geprueft werden: {path} ({error})") from error

    try:
        path.read_bytes()
    except OSError as error:
        if is_unc_path(path):
            raise FileContextError(f"NAS/UNC-Pfad nicht erreichbar: {path} ({error})") from error
        raise FileContextError(f"Datei ist nicht lesbar: {path} ({error})") from error
    except Exception as error:
        raise FileContextError(f"Datei ist nicht lesbar: {path} ({error})") from error

    return path


def read_file_bytes_for_prompt(path: Path, suffix: str) -> tuple[bytes, int, bool]:
    if suffix != ".csv":
        file_bytes = path.read_bytes()
        file_size = len(file_bytes)
        if file_size > MAX_FILE_BYTES:
            raise FileContextError(
                f"Datei ist zu gross fuer den Prompt: {path} ({file_size} Bytes, Limit {MAX_FILE_BYTES} Bytes)."
            )
        return file_bytes, file_size, False

    file_size: int | None = None
    try:
        file_size = path.stat().st_size
    except Exception:
        file_size = None

    try:
        with path.open("rb") as handle:
            file_bytes = handle.read(MAX_FILE_BYTES)
    except Exception as error:
        raise FileContextError(f"Fehler beim Lesen der Datei: {path} ({error})") from error

    if file_size is None:
        # Best-effort: if we couldn't stat(), we assume truncation is unknown.
        return file_bytes, len(file_bytes), False

    return file_bytes, file_size, file_size > MAX_FILE_BYTES


def render_file_content_for_prompt(file_bytes: bytes, suffix: str) -> tuple[str, list[str]]:
    if suffix == ".csv":
        return render_csv_preview(file_bytes)

    text = file_bytes.decode("utf-8", errors="replace").strip()
    return (text, [])


def render_pdf_text_for_prompt(path: Path) -> tuple[str, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise FileContextError(
            "PDF-Unterstuetzung ist nicht installiert. Bitte installiere 'pypdf' in der .venv (requirements.txt)."
        ) from error

    try:
        with path.open("rb") as handle:
            reader = PdfReader(handle)
            total_pages = len(reader.pages)

            pages_examined = min(total_pages, MAX_PDF_PAGES)
            remaining_chars = MAX_PDF_TEXT_CHARS
            extracted_chars = 0
            truncated_by_chars = False

            parts: list[str] = []
            for page_index in range(pages_examined):
                if remaining_chars <= 0:
                    truncated_by_chars = True
                    break

                page = reader.pages[page_index]
                page_text = page.extract_text() or ""
                page_text = page_text.replace("\r\n", "\n").replace("\r", "\n").strip()
                if not page_text:
                    continue

                if len(page_text) > remaining_chars:
                    page_text = page_text[: max(0, remaining_chars - 3)].rstrip() + "..."
                    truncated_by_chars = True

                parts.append(f"Seite {page_index + 1}:\n{page_text}")

                extracted_chars += len(page_text)
                remaining_chars = MAX_PDF_TEXT_CHARS - extracted_chars
                if truncated_by_chars:
                    break

    except FileContextError:
        raise
    except Exception as error:
        raise FileContextError(f"Fehler beim Lesen/Parsen der PDF-Datei: {path} ({error})") from error

    content = "\n\n".join(parts).strip()
    used_extractor = "pypdf"

    if not content:
        # Fallback: pdfminer.six can sometimes extract text when pypdf returns empty.
        try:
            from pdfminer.high_level import extract_text as pdfminer_extract_text
        except ImportError as error:
            raise FileContextError(
                "PDF enthaelt keinen extrahierbaren Text. "
                "Hinweis: Wenn es ein Scan (nur Bild) ist, wird OCR benoetigt (nicht implementiert). "
                "Optionaler Fallback ist verfuegbar, aber nicht installiert: 'pdfminer.six'. "
                f"Datei: {path}"
            ) from error

        used_extractor = "pdfminer.six (Fallback)"
        remaining_chars = MAX_PDF_TEXT_CHARS
        extracted_chars = 0
        truncated_by_chars = False
        parts = []

        for page_index in range(pages_examined):
            if remaining_chars <= 0:
                truncated_by_chars = True
                break

            try:
                page_text = pdfminer_extract_text(str(path), page_numbers=[page_index], maxpages=1) or ""
            except Exception as error:
                raise FileContextError(
                    f"Fehler beim Extrahieren des PDF-Texts (Fallback) fuer Seite {page_index + 1}: {path} ({error})"
                ) from error

            page_text = page_text.replace("\r\n", "\n").replace("\r", "\n").strip()
            if not page_text:
                continue

            if len(page_text) > remaining_chars:
                page_text = page_text[: max(0, remaining_chars - 3)].rstrip() + "..."
                truncated_by_chars = True

            parts.append(f"Seite {page_index + 1}:\n{page_text}")
            extracted_chars += len(page_text)
            remaining_chars = MAX_PDF_TEXT_CHARS - extracted_chars
            if truncated_by_chars:
                break

        content = "\n\n".join(parts).strip()

    ocr_meta: list[str] = []
    if not content:
        content, ocr_meta = render_pdf_ocr_text_for_prompt(path, pages_examined)
        used_extractor = "OCR (tesseract)"
        extracted_chars = len(content)

    meta_lines = [
        f"- Seiten: {total_pages}",
        f"- Begrenzung: max {MAX_PDF_PAGES} Seiten, max {MAX_PDF_TEXT_CHARS} Zeichen",
        f"- Vorschau: {pages_examined}/{total_pages} Seiten, {extracted_chars}/{MAX_PDF_TEXT_CHARS} Zeichen",
        f"- Extraktion: {used_extractor}",
    ]

    if used_extractor.startswith("OCR"):
        meta_lines.extend(ocr_meta)

    if total_pages > MAX_PDF_PAGES:
        meta_lines.append(f"- Hinweis: PDF wurde fuer den Prompt nach {MAX_PDF_PAGES} Seiten begrenzt.")

    if truncated_by_chars:
        meta_lines.append(f"- Hinweis: PDF-Text wurde fuer den Prompt nach {MAX_PDF_TEXT_CHARS} Zeichen begrenzt.")

    return content, meta_lines


def render_pdf_retrieval_for_prompt(
    pdf_path: Path,
    prompt_text: str,
    note_path: Path,
) -> tuple[str, list[str]]:
    vault_root = detect_vault_root(note_path)
    index_root = get_index_root(vault_root)

    try:
        signature = build_pdf_document_signature(pdf_path)
        chunks = retrieve_pdf_chunks(index_root, signature, prompt_text)
        return format_retrieved_chunks_for_prompt(pdf_path, chunks)
    except PdfIndexError as error:
        raise FileContextError(str(error)) from error


def render_pdf_ocr_text_for_prompt(path: Path, pages_examined: int) -> tuple[str, list[str]]:
    """OCR fallback for PDFs without extractable text.

    Uses external tools (Poppler + Tesseract). This is intentionally limited to a
    small number of pages to avoid long runtimes and prompt blow-ups.
    """

    try:
        from pdf2image import convert_from_path
    except ImportError as error:
        raise FileContextError(
            "PDF enthaelt keinen extrahierbaren Text und wirkt wie ein Scan (nur Bild). "
            "OCR wird automatisch versucht, ist aber nicht installiert: Bitte installiere 'pdf2image' und 'Pillow'. "
            f"Datei: {path}"
        ) from error

    try:
        import pytesseract
        from pytesseract import TesseractNotFoundError
    except ImportError as error:
        raise FileContextError(
            "PDF enthaelt keinen extrahierbaren Text und wirkt wie ein Scan (nur Bild). "
            "OCR wird automatisch versucht, ist aber nicht installiert: Bitte installiere 'pytesseract'. "
            f"Datei: {path}"
        ) from error

    tesseract_cmd = get_pdf_ocr_tesseract_cmd()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    poppler_path = get_pdf_ocr_poppler_path()
    lang = get_pdf_ocr_lang()

    ocr_pages = min(PDF_OCR_MAX_PAGES, pages_examined)
    if ocr_pages <= 0:
        ocr_pages = min(PDF_OCR_MAX_PAGES, MAX_PDF_PAGES)

    with tempfile.TemporaryDirectory(prefix="codexcli-ocr-") as temp_dir:
        try:
            images = convert_from_path(
                str(path),
                dpi=PDF_OCR_DPI,
                first_page=1,
                last_page=ocr_pages,
                poppler_path=poppler_path,
                output_folder=temp_dir,
            )
        except Exception as error:
            hint = (
                "Hinweis: Fuer OCR wird Poppler benoetigt (pdftoppm). "
                "Optional kann der Pfad per CODEXCLI_POPPLER_PATH gesetzt werden."
            )
            raise FileContextError(f"OCR konnte PDF-Seiten nicht rendern: {path} ({error}). {hint}") from error

        remaining_chars = MAX_PDF_TEXT_CHARS
        extracted_chars = 0
        truncated_by_chars = False
        parts: list[str] = []

        for page_index, image in enumerate(images, start=1):
            if remaining_chars <= 0:
                truncated_by_chars = True
                break

            try:
                page_text = pytesseract.image_to_string(image, lang=lang) or ""
            except TesseractNotFoundError as error:
                hint = (
                    "Hinweis: Tesseract OCR ist nicht installiert oder nicht im PATH. "
                    "Optional kann der Pfad per CODEXCLI_TESSERACT_CMD gesetzt werden."
                )
                raise FileContextError(f"OCR konnte nicht gestartet werden: {error}. {hint}") from error
            except Exception as error:
                raise FileContextError(f"Fehler bei OCR fuer Seite {page_index}: {path} ({error})") from error

            page_text = page_text.replace("\r\n", "\n").replace("\r", "\n").strip()
            if not page_text:
                continue

            if len(page_text) > remaining_chars:
                page_text = page_text[: max(0, remaining_chars - 3)].rstrip() + "..."
                truncated_by_chars = True

            parts.append(f"Seite {page_index}:\n{page_text}")
            extracted_chars += len(page_text)
            remaining_chars = MAX_PDF_TEXT_CHARS - extracted_chars
            if truncated_by_chars:
                break

    content = "\n\n".join(parts).strip()
    if not content:
        hint = _build_ocr_no_text_hints(poppler_path)
        hint_suffix = f" {hint}" if hint else ""
        raise FileContextError(
            "PDF enthaelt keinen extrahierbaren Text (Textextraktion leer, OCR lieferte keinen Text). "
            "Bei Scan-PDFs kann das z.B. an schlechter Bildqualitaet liegen. "
            f"Datei: {path}." + hint_suffix
        )

    meta_lines = [
        f"- OCR: max {PDF_OCR_MAX_PAGES} Seiten, genutzt {len(images)} Seiten",
        f"- OCR: {PDF_OCR_DPI} dpi",
        f"- OCR: Sprache {lang}",
    ]
    return content, meta_lines


def render_csv_preview(file_bytes: bytes) -> tuple[str, list[str]]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    if not text.strip():
        return "(CSV ist leer.)", ["- Zeilen: 0", f"- Begrenzung: max {MAX_CSV_ROWS} Zeilen, max {MAX_CSV_COLS} Spalten"]

    sample = text[:4096]
    dialect = csv.excel
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
    except Exception:
        dialect = csv.excel

    rows_preview: list[list[str]] = []
    total_rows = 0
    max_cols_seen = 0
    parse_failed: str | None = None

    try:
        reader = csv.reader(io.StringIO(text), dialect)
        for row in reader:
            total_rows += 1
            max_cols_seen = max(max_cols_seen, len(row))
            if len(rows_preview) < MAX_CSV_ROWS:
                rows_preview.append([normalize_csv_cell(cell) for cell in row[:MAX_CSV_COLS]])
    except csv.Error as error:
        parse_failed = str(error)

    if parse_failed is not None:
        lines = [line.rstrip("\r") for line in text.splitlines() if line.strip()]
        preview_lines = lines[:MAX_CSV_ROWS]
        total_rows = len(lines)
        max_cols_seen = 0
        content = "CSV konnte nicht sauber geparst werden; Rohvorschau:\n\n" + "```\n" + "\n".join(preview_lines) + "\n```"
        meta = [
            f"- Zeilen: {total_rows}",
            f"- Begrenzung: max {MAX_CSV_ROWS} Zeilen (Rohvorschau)",
        ]
        return content.strip(), meta

    content = build_markdown_table(rows_preview)
    meta_lines = [
        f"- Zeilen: {total_rows}",
        f"- Begrenzung: max {MAX_CSV_ROWS} Zeilen, max {MAX_CSV_COLS} Spalten",
        f"- Vorschau: {min(total_rows, MAX_CSV_ROWS)}/{total_rows} Zeilen, {min(max_cols_seen, MAX_CSV_COLS)}/{max_cols_seen} Spalten",
    ]
    return content.strip(), meta_lines


def normalize_csv_cell(value: str) -> str:
    normalized = (value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(normalized) > MAX_CSV_CELL_CHARS:
        normalized = normalized[: MAX_CSV_CELL_CHARS - 3].rstrip() + "..."
    return normalized


def escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def build_markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return "(CSV ist leer.)"

    max_cols = max(len(row) for row in rows)
    cols = min(max_cols, MAX_CSV_COLS)

    if len(rows) == 1:
        header = [f"col{index + 1}" for index in range(cols)]
        data_rows = [rows[0]]
    else:
        header = rows[0]
        data_rows = rows[1:]

    header = (header + [""] * cols)[:cols]

    lines: list[str] = []
    lines.append("| " + " | ".join(escape_markdown_cell(cell) for cell in header) + " |")
    lines.append("| " + " | ".join(["---"] * cols) + " |")

    for row in data_rows:
        row = (row + [""] * cols)[:cols]
        lines.append("| " + " | ".join(escape_markdown_cell(cell) for cell in row) + " |")

    return "\n".join(lines)


def build_file_context_block(contexts: list[ResolvedFileContext]) -> str:
    blocks: list[str] = []

    for index, context in enumerate(contexts, start=1):
        content = context.content if context.content else "(Datei ist leer.)"

        extra_meta = []
        if context.meta_lines:
            extra_meta = list(context.meta_lines)

        blocks.append(
            "\n".join(
                [
                    f"Quelle {index}:",
                    f"- Herkunft: {context.source_label}",
                    f"- Pfad: {context.path}",
                    f"- Typ: {context.file_type}",
                    *extra_meta,
                    "- Inhalt:",
                    content,
                ]
            )
        )

    return "Zusätzliche Dateiquellen:\n\n" + "\n\n".join(blocks)
