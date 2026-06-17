from pathlib import Path

from app.codex_client import run_codex
from app.file_context import FileContextError, collect_prompt_context_v2, detect_vault_root
from app.image_client import generate_png_image
from app.markdown_sections import (
    SECTION_CHAT,
    SECTION_PROMPT,
    append_chat_block,
    append_error_to_note,
    build_codex_prompt,
    extract_section,
    normalize_newlines,
    replace_section,
    render_chat_text_for_export,
)
from app.save_as import (
    ExportChatAsError,
    SaveAsDirective,
    SaveAsError,
    build_save_as_codex_instruction,
    extract_aspect_directive,
    extract_export_chat_as_directive,
    extract_save_as_directive,
    finalize_export_chat_as_directive,
    finalize_save_as_directive,
    is_image_save_as,
    parse_save_as_codex_output,
)


def append_response(note_path: Path) -> int:
    if not note_path.exists():
        print(f"Fehler: Datei nicht gefunden: {note_path}")
        return 1

    try:
        original_text = note_path.read_text(encoding="utf-8")
        original_text = normalize_newlines(original_text)
    except Exception as error:
        print(f"Fehler beim Lesen der Datei: {error}")
        return 1

    prompt_text = extract_section(original_text, SECTION_PROMPT)

    if not prompt_text.strip():
        append_error_to_note(
            note_path,
            original_text,
            "Der Abschnitt ## Prompt ist leer. Bitte dort zuerst eine Frage oder Anweisung eintragen.",
        )
        return 1

    display_prompt_text, export_chat_as = extract_export_chat_as_directive(prompt_text)
    display_prompt_text, save_as = extract_save_as_directive(display_prompt_text)

    if export_chat_as is not None and save_as is not None:
        append_error_to_note(
            note_path,
            original_text,
            "EXPORT_CHAT_AS und SAVE_AS koennen nicht kombiniert werden. Bitte nur eine Direktive verwenden.",
        )
        return 1

    if export_chat_as is not None:
        try:
            export_chat_as = finalize_export_chat_as_directive(note_path, export_chat_as)
        except ExportChatAsError as error:
            append_error_to_note(note_path, original_text, str(error))
            return 1

        chat_text = extract_section(original_text, SECTION_CHAT)
        export_text = render_chat_text_for_export(chat_text)
        if not export_text.strip():
            append_error_to_note(
                note_path,
                original_text,
                "EXPORT_CHAT_AS: Der Abschnitt ## Unterhaltung ist leer. Es gibt nichts zu exportieren.",
            )
            return 1

        try:
            export_chat_as.output_path.parent.mkdir(parents=True, exist_ok=True)
            export_chat_as.output_path.write_text(export_text, encoding="utf-8")
        except Exception as error:
            append_error_to_note(
                note_path,
                original_text,
                f"EXPORT_CHAT_AS: Fehler beim Schreiben der Datei: {export_chat_as.output_path}: {error}",
            )
            return 1

        updated_text = append_chat_block(original_text, display_prompt_text, export_chat_as.wikilink)
        updated_text = replace_section(updated_text, SECTION_PROMPT, "")
        note_path.write_text(updated_text, encoding="utf-8")
        print(f"Chat wurde exportiert nach {export_chat_as.output_path}, {SECTION_PROMPT} wurde geleert.")
        return 0

    if save_as is not None:
        display_prompt_text, aspect_ratio = extract_aspect_directive(display_prompt_text)
        save_as = SaveAsDirective(
            raw_target=save_as.raw_target,
            relative_target=save_as.relative_target,
            output_path=save_as.output_path,
            wikilink=save_as.wikilink,
            aspect_ratio=aspect_ratio,
        )
        if not display_prompt_text.strip():
            append_error_to_note(
                note_path,
                original_text,
                "SAVE_AS: Der Prompt ist leer (nur Direktive gefunden). Bitte ergänze eine Anweisung, z.B. 'Fasse den Inhalt zusammen. SAVE_AS: exports/x.md'.",
            )
            return 1
        try:
            save_as = finalize_save_as_directive(note_path, save_as)
        except SaveAsError as error:
            append_error_to_note(note_path, original_text, str(error))
            return 1

        if is_image_save_as(save_as):
            image_result = generate_png_image(display_prompt_text, aspect_ratio=save_as.aspect_ratio)
            if image_result.error:
                append_error_to_note(note_path, original_text, image_result.error)
                return 1

            try:
                save_as.output_path.parent.mkdir(parents=True, exist_ok=True)
                save_as.output_path.write_bytes(image_result.image_bytes or b"")
            except Exception as error:
                append_error_to_note(
                    note_path,
                    original_text,
                    f"SAVE_AS: Fehler beim Schreiben der Datei: {save_as.output_path}: {error}",
                )
                return 1

            updated_text = append_chat_block(original_text, display_prompt_text, save_as.wikilink)
            updated_text = replace_section(updated_text, SECTION_PROMPT, "")
            note_path.write_text(updated_text, encoding="utf-8")
            print(f"Bild wurde gespeichert nach {save_as.output_path}, {SECTION_PROMPT} wurde geleert.")
            return 0

    codex_prompt_text = display_prompt_text
    if save_as is not None:
        codex_prompt_text = display_prompt_text + build_save_as_codex_instruction(save_as)

    try:
        collected_context = collect_prompt_context_v2(display_prompt_text, note_path)
    except FileContextError as error:
        append_error_to_note(note_path, original_text, str(error))
        return 1

    note_text_for_codex = replace_section(original_text, SECTION_PROMPT, codex_prompt_text)
    if collected_context.data_mode_active:
        codex_prompt = build_codex_prompt(
            note_text_for_codex,
            instruction_context=collected_context.instruction_context_block,
            data_context=collected_context.data_context_block,
        )
    else:
        codex_prompt = build_codex_prompt(note_text_for_codex, file_context=collected_context.file_context_block)
    result = run_codex(
        codex_prompt,
        image_paths=collected_context.image_paths,
        vault_root=detect_vault_root(note_path),
    )

    if result.start_error:
        append_error_to_note(note_path, original_text, f"Codex konnte nicht gestartet werden: {result.start_error}")
        return 1

    if result.returncode != 0:
        error_message = result.stderr.strip() or result.stdout.strip() or "Unbekannter Fehler"
        if collected_context.image_paths:
            error_message = (
                "Codex-Aufruf mit Bildinput ist fehlgeschlagen. "
                "Moegliche Ursache: Modell/Account/CLI unterstuetzt keine Bildinputs. "
                f"Details: {error_message}"
            )
        append_error_to_note(note_path, original_text, error_message)
        return result.returncode

    raw_response_text = result.stdout.strip()

    if not raw_response_text:
        append_error_to_note(note_path, original_text, "Codex hat keine Ausgabe geliefert.")
        return 1

    response_text = raw_response_text
    if save_as is not None:
        try:
            response_text, file_content = parse_save_as_codex_output(raw_response_text, save_as)
        except SaveAsError as error:
            append_error_to_note(note_path, original_text, str(error))
            return 1

        try:
            save_as.output_path.parent.mkdir(parents=True, exist_ok=True)
            save_as.output_path.write_text(file_content, encoding="utf-8")
        except Exception as error:
            append_error_to_note(
                note_path,
                original_text,
                f"SAVE_AS: Fehler beim Schreiben der Datei: {save_as.output_path}: {error}",
            )
            return 1

    updated_text = append_chat_block(original_text, display_prompt_text, response_text)
    updated_text = replace_section(updated_text, SECTION_PROMPT, "")

    note_path.write_text(updated_text, encoding="utf-8")
    print(f"Antwort wurde angehängt, {SECTION_PROMPT} wurde geleert.")
    return 0
