from pathlib import Path

from app.codex_client import run_codex
from app.file_context import detect_vault_root
from app.markdown_sections import (
    SECTION_CHAT,
    SECTION_SUMMARY,
    build_summary_prompt,
    extract_section,
    normalize_latex_delimiters_outside_code,
    normalize_math_symbols_outside_code,
    normalize_newlines,
    replace_section,
)


def update_summary(note_path: Path) -> int:
    if not note_path.exists():
        print(f"Fehler: Datei nicht gefunden: {note_path}")
        return 1

    try:
        original_text = note_path.read_text(encoding="utf-8")
        original_text = normalize_newlines(original_text)
    except Exception as error:
        print(f"Fehler beim Lesen der Datei: {error}")
        return 1

    chat_text = extract_section(original_text, SECTION_CHAT)
    old_summary = extract_section(original_text, SECTION_SUMMARY)
    prompt = build_summary_prompt(chat_text, old_summary)

    result = run_codex(prompt, vault_root=detect_vault_root(note_path))

    if result.start_error:
        print(f"Codex konnte nicht gestartet werden: {result.start_error}")
        return 1

    if result.returncode != 0:
        error_message = result.stderr.strip() or result.stdout.strip() or "Unbekannter Fehler"
        print(error_message)
        return result.returncode

    summary_text = normalize_latex_delimiters_outside_code(result.stdout.strip())
    summary_text = normalize_math_symbols_outside_code(summary_text)

    if not summary_text:
        print("Codex hat keine Zusammenfassung geliefert.")
        return 1

    updated_text = replace_section(original_text, SECTION_SUMMARY, summary_text)
    note_path.write_text(updated_text, encoding="utf-8")
    print("Laufende Zusammenfassung wurde aktualisiert.")
    return 0
