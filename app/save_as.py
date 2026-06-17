import re
from dataclasses import dataclass
from pathlib import Path


DELIMITER_PREFIX = "<<CODEXCLI_SAVE_AS_CONTENT"


class SaveAsError(RuntimeError):
    pass


class ExportChatAsError(RuntimeError):
    pass


_TRAILING_MARKDOWN_PUNCTUATION = ").,;:!?)]}>"


@dataclass(frozen=True)
class SaveAsDirective:
    raw_target: str
    relative_target: str
    output_path: Path
    wikilink: str
    aspect_ratio: str | None = None


@dataclass(frozen=True)
class ExportChatAsDirective:
    raw_target: str
    relative_target: str
    output_path: Path
    wikilink: str


def get_save_as_delimiter(directive: SaveAsDirective) -> str:
    # Use a per-target delimiter to avoid accidental collisions with normal content.
    # Keep it simple and ASCII-only.
    return f"{DELIMITER_PREFIX}:{directive.output_path.stem}>>"


def extract_save_as_directive(prompt_text: str) -> tuple[str, SaveAsDirective | None]:
    """Extract a single SAVE_AS directive from prompt_text.

    Returns (cleaned_prompt_text, directive).

    Supported forms:
    - "... SAVE_AS: exports/file.md"
    - "... SAVE_AS: 'exports/file with spaces.md'"
    - "... SAVE_AS: \"exports/file with spaces.md\""
    """

    pattern = re.compile(
        r"(?i)\bSAVE_AS(?:\s*:\s*|\s+)(?P<target>\"[^\"]+\"|'[^']+'|\S+)",
    )
    match = pattern.search(prompt_text)
    if not match:
        return prompt_text, None

    raw_target = match.group("target").strip()
    # Remove the directive from the prompt (once).
    cleaned = pattern.sub("", prompt_text, count=1)
    cleaned = _cleanup_prompt_whitespace(cleaned)

    unquoted = raw_target
    if (unquoted.startswith("\"") and unquoted.endswith("\"")) or (
        unquoted.startswith("'") and unquoted.endswith("'")
    ):
        unquoted = unquoted[1:-1].strip()

    return cleaned, SaveAsDirective(
        raw_target=raw_target,
        relative_target=unquoted,
        output_path=Path("."),
        wikilink="",
        aspect_ratio=None,
    )


def extract_aspect_directive(prompt_text: str) -> tuple[str, str | None]:
    """Extract optional ASPECT directive from prompt_text.

    Supported forms:
    - "... ASPECT: 16:9"
    - "... ASPECT 4:3"
    """

    pattern = re.compile(
        r"(?i)\bASPECT(?:\s*:\s*|\s+)(?P<aspect>16:9|4:3|1:1)\b",
    )
    match = pattern.search(prompt_text)
    if not match:
        return prompt_text, None

    aspect = match.group("aspect")
    cleaned = pattern.sub("", prompt_text, count=1)
    cleaned = _cleanup_prompt_whitespace(cleaned)
    return cleaned, aspect


def extract_export_chat_as_directive(prompt_text: str) -> tuple[str, ExportChatAsDirective | None]:
    """Extract a single EXPORT_CHAT_AS directive from prompt_text.

    Returns (cleaned_prompt_text, directive).

    Supported forms:
    - "EXPORT_CHAT_AS: exports/chat.md"
    - "EXPORT_CHAT_AS: 'exports/chat with spaces.md'"
    - "EXPORT_CHAT_AS: \"exports/chat with spaces.md\""
    """

    pattern = re.compile(
        r"(?i)\bEXPORT_CHAT_AS(?:\s*:\s*|\s+)(?P<target>\"[^\"]+\"|'[^']+'|\S+)",
    )
    match = pattern.search(prompt_text)
    if not match:
        return prompt_text, None

    raw_target = match.group("target").strip()
    cleaned = pattern.sub("", prompt_text, count=1)
    cleaned = _cleanup_prompt_whitespace(cleaned)

    unquoted = raw_target
    if (unquoted.startswith('"') and unquoted.endswith('"')) or (
        unquoted.startswith("'") and unquoted.endswith("'")
    ):
        unquoted = unquoted[1:-1].strip()

    return cleaned, ExportChatAsDirective(
        raw_target=raw_target,
        relative_target=unquoted,
        output_path=Path("."),
        wikilink="",
    )


def finalize_save_as_directive(note_path: Path, directive: SaveAsDirective) -> SaveAsDirective:
    relative_target = directive.relative_target.replace("\\", "/").strip()
    if not relative_target:
        raise SaveAsError("SAVE_AS: Zielpfad ist leer.")

    lowered = relative_target.lower()
    if lowered.startswith("\\\\"):
        raise SaveAsError("SAVE_AS: UNC-Pfade sind nicht erlaubt. Bitte nur relative Pfade verwenden.")
    if re.match(r"^[A-Za-z]:\\", relative_target) or re.match(r"^[A-Za-z]:/", relative_target):
        raise SaveAsError("SAVE_AS: Absolute Windows-Pfade sind nicht erlaubt. Bitte nur relative Pfade verwenden.")
    if relative_target.startswith("/"):
        raise SaveAsError("SAVE_AS: Absolute Pfade sind nicht erlaubt. Bitte nur relative Pfade verwenden.")

    parts = [part for part in relative_target.split("/") if part]
    if any(part == ".." for part in parts):
        raise SaveAsError("SAVE_AS: '..' ist nicht erlaubt (Path Traversal).")

    output_path = (note_path.parent / Path(*parts)).resolve()
    note_dir = note_path.parent.resolve()

    try:
        output_path.relative_to(note_dir)
    except Exception as error:
        raise SaveAsError("SAVE_AS: Zielpfad liegt nicht innerhalb des Note-Ordners.") from error

    suffix = output_path.suffix.lower()
    if suffix not in {".md", ".png"}:
        raise SaveAsError("SAVE_AS: Dateiendung muss .md oder .png sein.")

    if suffix == ".png":
        wikilink = f"[[{output_path.name}]]"
    else:
        wikilink = f"[[{output_path.stem}]]"

    return SaveAsDirective(
        raw_target=directive.raw_target,
        relative_target=relative_target,
        output_path=output_path,
        wikilink=wikilink,
        aspect_ratio=directive.aspect_ratio,
    )


def is_image_save_as(directive: SaveAsDirective) -> bool:
    return directive.output_path.suffix.lower() == ".png"


def finalize_export_chat_as_directive(note_path: Path, directive: ExportChatAsDirective) -> ExportChatAsDirective:
    relative_target = directive.relative_target.replace("\\", "/").strip()
    relative_target = relative_target.strip("\ufeff\u200b")
    if not relative_target:
        raise ExportChatAsError("EXPORT_CHAT_AS: Zielpfad ist leer.")

    # Users often end directives with punctuation (e.g. '.md.' or '.md)') in free text.
    if not relative_target.lower().endswith(".md"):
        cleaned = relative_target.rstrip(_TRAILING_MARKDOWN_PUNCTUATION).strip()
        if cleaned and cleaned.lower().endswith(".md"):
            relative_target = cleaned

    lowered = relative_target.lower()
    if lowered.startswith("\\\\"):
        raise ExportChatAsError(
            "EXPORT_CHAT_AS: UNC-Pfade sind nicht erlaubt. Bitte nur relative Pfade verwenden."
        )
    if re.match(r"^[A-Za-z]:\\", relative_target) or re.match(r"^[A-Za-z]:/", relative_target):
        raise ExportChatAsError(
            "EXPORT_CHAT_AS: Absolute Windows-Pfade sind nicht erlaubt. Bitte nur relative Pfade verwenden."
        )
    if relative_target.startswith("/"):
        raise ExportChatAsError(
            "EXPORT_CHAT_AS: Absolute Pfade sind nicht erlaubt. Bitte nur relative Pfade verwenden."
        )

    parts = [part for part in relative_target.split("/") if part]
    if any(part == ".." for part in parts):
        raise ExportChatAsError("EXPORT_CHAT_AS: '..' ist nicht erlaubt (Path Traversal).")

    output_path = (note_path.parent / Path(*parts)).resolve()
    note_dir = note_path.parent.resolve()

    try:
        output_path.relative_to(note_dir)
    except Exception as error:
        raise ExportChatAsError("EXPORT_CHAT_AS: Zielpfad liegt nicht innerhalb des Note-Ordners.") from error

    if output_path.suffix.lower() != ".md":
        raise ExportChatAsError(
            f"EXPORT_CHAT_AS: Dateiendung muss .md sein (erhalten: {directive.relative_target!r})."
        )

    wikilink = f"[[{output_path.stem}]]"

    return ExportChatAsDirective(
        raw_target=directive.raw_target,
        relative_target=relative_target,
        output_path=output_path,
        wikilink=wikilink,
    )


def build_save_as_codex_instruction(directive: SaveAsDirective) -> str:
    """Instruction appended to the model prompt so we can parse the output reliably."""

    delimiter = get_save_as_delimiter(directive)

    return (
        "\n\n"
        "WICHTIG: Dieser Lauf verwendet SAVE_AS (Dateiausgabe).\n"
        "Gib deine Antwort exakt in diesem Format aus:\n"
        f"1) Erste nicht-leere Zeile: {directive.wikilink}\n"
        f"2) Dann eine Zeile mit exakt: {delimiter}\n"
        "3) Danach kommt der komplette Inhalt, der in die Zieldatei geschrieben werden soll (Markdown).\n"
        "Keine weiteren Erklaerungen, keine Code-Fences.\n"
    )


def parse_save_as_codex_output(output: str, directive: SaveAsDirective) -> tuple[str, str]:
    """Return (note_response_text, file_content)."""

    text = output.strip()
    delimiter = get_save_as_delimiter(directive)
    if delimiter not in text:
        raise SaveAsError(
            "SAVE_AS: Codex-Ausgabe hat nicht das erwartete Format (Delimiter fehlt)."
        )

    header, content = text.split(delimiter, maxsplit=1)
    header = header.strip()
    content = content.strip()

    # First non-empty line should be the wikilink.
    first_line = ""
    for line in header.splitlines():
        if line.strip():
            first_line = line.strip()
            break

    if not first_line:
        raise SaveAsError("SAVE_AS: Codex-Ausgabe enthaelt keinen WikiLink-Kopf.")

    if first_line != directive.wikilink:
        raise SaveAsError(
            f"SAVE_AS: Codex-Ausgabe enthaelt nicht den erwarteten WikiLink. Erwartet: {directive.wikilink}"
        )

    if not content:
        raise SaveAsError("SAVE_AS: Dateiinhalte sind leer.")

    return directive.wikilink, content


def _cleanup_prompt_whitespace(text: str) -> str:
    # Keep it conservative: remove doubled spaces caused by directive removal.
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Remove empty lines at end.
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()
