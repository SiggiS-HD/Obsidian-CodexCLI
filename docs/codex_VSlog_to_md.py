#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "codex_chat"


def format_unix_ms(timestamp_ms: Any) -> str | None:
    if not isinstance(timestamp_ms, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exportiert Codex-Session-Logs im JSONL-Format nach Markdown."
    )
    parser.add_argument(
        "--log-root",
        type=Path,
        default=Path.home() / ".codex" / "sessions",
        help="Wurzelverzeichnis der Codex-Session-Logs",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help="Optional: genau eine JSONL-Datei exportieren",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Zielordner für erzeugte Markdown-Dateien",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "readable", "text-only"],
        default="text-only",
        help="Exportmodus",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Nur Sessions eines bestimmten Tages exportieren, Format: YYYY-MM-DD",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Erzeugt alle Markdown-Dateien neu, auch wenn sie aktuell sind.",
    )
    return parser.parse_args()


def should_export(src: Path, dst: Path, force: bool) -> bool:
    if force or not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def parse_date_filter(date_str: str | None) -> tuple[str, str, str] | None:
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"Ungültiges Datumsformat für --date: {date_str}. Erwartet: YYYY-MM-DD") from exc
    return (f"{dt.year:04d}", f"{dt.month:02d}", f"{dt.day:02d}")


def session_matches_date(jsonl_file: Path, date_parts: tuple[str, str, str] | None) -> bool:
    if date_parts is None:
        return True
    year, month, day = date_parts
    parts = jsonl_file.parts
    return year in parts and month in parts and day in parts


def role_title(role: str) -> str:
    role_map = {
        "user": "Benutzer",
        "assistant": "Codex",
        "system": "System",
        "tool": "Tool",
        "developer": "Developer",
    }
    return role_map.get(role.lower(), role.capitalize() if role else "Eintrag")


def looks_technical(text: str) -> bool:
    if not text.strip():
        return False
    indicators = [
        "```", "{", "}", "[", "]", '"role"', '"content"', '"tool_name"',
        "function", "import ", "from ", "Traceback", "Exception", "Error:",
        "stderr", "stdout", "<|", "json", "apply_patch", "BEGIN", "END"
    ]
    score = sum(1 for token in indicators if token in text)
    long_dense_line = any(len(line) > 160 for line in text.splitlines())
    many_symbols = len(re.findall(r"[{}\[\]<>_=:/\\]", text)) > 40
    return score >= 2 or long_dense_line or many_symbols


def clean_text_for_readability(text: str) -> str:
    if not text.strip():
        return ""
    text = re.sub(r"```.*?```", "[Codeblock ausgeblendet]", text, flags=re.DOTALL)
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue
        if stripped.startswith("{") or stripped.startswith("}") or stripped.startswith('"'):
            continue
        if len(stripped) > 180 and len(re.findall(r"[{}\[\]<>_=:/\\]", stripped)) > 25:
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def extract_text_from_content(content: Any) -> str:
    """Extrahiert Text robust aus Codex-Content-Blöcken."""
    parts: list[str] = []

    def visit(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            if node.strip():
                parts.append(node.strip())
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if isinstance(node, dict):
            # häufige Felder im Codex-Format
            for key in ("text", "input_text", "output_text", "content"):
                value = node.get(key)
                if isinstance(value, (str, list, dict)):
                    visit(value)
            # manche Blöcke enthalten verschachtelte "items"
            if "items" in node:
                visit(node["items"])
            return

    visit(content)
    # Duplikate unmittelbar reduzieren
    merged = "\n".join(p for p in parts if p.strip()).strip()
    merged = re.sub(r"\n{3,}", "\n\n", merged)
    return merged


def normalize_entry(obj: dict[str, Any]) -> tuple[str | None, str, str, dict[str, Any]]:
    """
    Liefert: (role, text, entry_type, meta)
    Unterstützt sowohl flache Logs als auch payload-basierte Codex-Logs.
    """
    entry_type = str(obj.get("type", ""))
    meta: dict[str, Any] = {}

    # Format 1: flach
    if "role" in obj or "content" in obj:
        role = obj.get("role")
        text = extract_text_from_content(obj.get("content", ""))
        meta = {k: obj.get(k) for k in ("type", "name", "tool_name", "model") if obj.get(k)}
        return (str(role) if role else None, text, entry_type, meta)

    # Format 2: payload-basiert
    payload = obj.get("payload")
    if isinstance(payload, dict):
        role = payload.get("role")
        payload_type = str(payload.get("type", ""))
        text = extract_text_from_content(payload.get("content", ""))

        if not text and "text" in payload:
            text = extract_text_from_content(payload.get("text"))

        meta = {
            "outer_type": entry_type,
            "payload_type": payload_type,
        }
        if payload.get("name"):
            meta["name"] = payload.get("name")
        if payload.get("model"):
            meta["model"] = payload.get("model")

        return (str(role) if role else None, text, payload_type or entry_type, meta)

    return (None, "", entry_type, {})


def merge_nested_state(target: dict[str, Any], path: list[Any], value: Any) -> None:
    if not path:
        if isinstance(value, dict):
            target.update(value)
        return

    key = path[0]
    if len(path) == 1:
        current = target.get(key)
        if key == "response" and isinstance(current, list) and isinstance(value, list):
            current.extend(value)
        else:
            target[key] = value
        return

    child = target.get(key)
    if not isinstance(child, dict):
        child = {}
        target[key] = child
    merge_nested_state(child, path[1:], value)


def extract_text_from_response_items(items: list[Any]) -> str:
    parts: list[str] = []

    for item in items:
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue

        kind = item.get("kind")
        if kind in {"thinking", "mcpServersStarting", "toolInvocationSerialized"}:
            continue
        if kind == "inlineReference":
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                parts.append(f"`{name.strip()}`")
            continue

        text = ""
        if isinstance(item.get("value"), str):
            text = item["value"]
        if not text.strip():
            text = extract_text_from_content(item)
        if text.strip():
            parts.append(text.strip())

    merged = " ".join(parts).strip()
    merged = re.sub(r"\s+\n", "\n", merged)
    merged = re.sub(r"\n{3,}", "\n\n", merged)
    return merged


def extract_user_text_from_rendered_message(rendered: Any) -> str:
    text = extract_text_from_content(rendered)
    match = re.search(r"<userRequest>\s*(.*?)\s*</userRequest>", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def normalize_user_key(text: str) -> str:
    normalized = text.strip()
    normalized = normalized.replace("„", '"').replace("“", '"').replace("‚", "'").replace("’", "'")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def get_request_user_text(request: dict[str, Any]) -> str:
    message = request.get("message", {})
    user_text = ""
    if isinstance(message, dict):
        user_text = extract_text_from_content(message.get("text") or message.get("parts") or message)
    if user_text.strip():
        return user_text.strip()

    result = request.get("result")
    if isinstance(result, dict):
        metadata = result.get("metadata", {})
        if isinstance(metadata, dict):
            return extract_user_text_from_rendered_message(metadata.get("renderedUserMessage"))

    return ""


def request_sort_key(request: dict[str, Any]) -> tuple[int, str]:
    timestamp = request.get("timestamp")
    if isinstance(timestamp, (int, float)):
        return (int(timestamp), str(request.get("requestId", "")))
    return (0, str(request.get("requestId", "")))


def extract_entries_from_vscode_request_objects(
    requests: list[dict[str, Any]],
) -> list[tuple[str | None, str, str, dict[str, Any]]]:
    entries: list[tuple[str | None, str, str, dict[str, Any]]] = []

    for request in sorted(requests, key=request_sort_key):
        user_text = get_request_user_text(request)

        user_timestamp = format_unix_ms(request.get("timestamp"))
        if user_text.strip():
            entries.append((
                "user",
                user_text,
                "request",
                {
                    "request_id": request.get("requestId"),
                    "timestamp": user_timestamp,
                },
            ))

        response = request.get("response")
        assistant_text = ""
        if isinstance(response, list):
            assistant_text = extract_text_from_response_items(response)
        elif isinstance(response, dict):
            assistant_text = extract_text_from_content(response)

        completed_at = None
        model_state = request.get("modelState")
        if isinstance(model_state, dict):
            completed_at = format_unix_ms(model_state.get("completedAt"))
        if not completed_at:
            completed_at = user_timestamp

        if assistant_text.strip():
            entries.append((
                "assistant",
                assistant_text,
                "response",
                {
                    "request_id": request.get("requestId"),
                    "timestamp": completed_at,
                },
            ))

    return entries


def extract_entries_from_vscode_session(jsonl_file: Path) -> list[tuple[str | None, str, str, dict[str, Any]]]:
    snapshot_requests: dict[str, dict[str, Any]] = {}
    indexed_requests: dict[int, dict[str, Any]] = {}

    with jsonl_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            path = obj.get("k")
            value = obj.get("v")

            if path == ["requests"] and isinstance(value, list):
                for request in value:
                    if isinstance(request, dict):
                        request_id = request.get("requestId")
                        if isinstance(request_id, str) and request_id:
                            snapshot_requests[request_id] = request
                continue

            if (
                isinstance(path, list)
                and len(path) >= 2
                and path[0] == "requests"
                and isinstance(path[1], int)
            ):
                merge_nested_state(indexed_requests.setdefault(path[1], {}), path[2:], value)

    if len(snapshot_requests) > 1:
        snapshot_objects = list(snapshot_requests.values())
        indexed_by_user: dict[str, dict[str, Any]] = {}

        for idx in sorted(indexed_requests):
            indexed_request = indexed_requests[idx]
            user_text = get_request_user_text(indexed_request)
            if not user_text:
                continue
            user_key = normalize_user_key(user_text)
            candidate = indexed_by_user.get(user_key)
            candidate_response = extract_text_from_response_items(candidate.get("response", [])) if candidate else ""
            indexed_response = extract_text_from_response_items(indexed_request.get("response", []))
            if candidate is None or len(indexed_response) > len(candidate_response):
                indexed_by_user[user_key] = indexed_request

        for request in snapshot_objects:
            user_text = get_request_user_text(request)
            user_key = normalize_user_key(user_text)
            indexed_request = indexed_by_user.get(user_key)
            if not indexed_request:
                continue

            snapshot_response = extract_text_from_response_items(request.get("response", []))
            indexed_response = extract_text_from_response_items(indexed_request.get("response", []))
            if len(indexed_response) > len(snapshot_response):
                request["response"] = indexed_request.get("response")

            snapshot_state = request.get("modelState")
            indexed_state = indexed_request.get("modelState")
            if (
                isinstance(indexed_state, dict)
                and indexed_state.get("completedAt")
                and (
                    not isinstance(snapshot_state, dict)
                    or not snapshot_state.get("completedAt")
                )
            ):
                request["modelState"] = indexed_state

            if "result" not in request and "result" in indexed_request:
                request["result"] = indexed_request["result"]

        return extract_entries_from_vscode_request_objects(snapshot_objects)

    indexed_request_objects: list[dict[str, Any]] = []
    for idx in sorted(indexed_requests):
        request = indexed_requests[idx]
        result = request.get("result")
        if isinstance(result, dict):
            metadata = result.get("metadata", {})
            if isinstance(metadata, dict):
                request["requestId"] = request.get("requestId") or f"indexed-{idx}"
                request["timestamp"] = request.get("timestamp")
                request["result"] = result
        indexed_request_objects.append(request)

    return extract_entries_from_vscode_request_objects(indexed_request_objects)


def export_session(jsonl_file: Path, output_dir: Path, mode: str) -> Path:
    out_file = output_dir / f"{jsonl_file.stem}.md"
    output_dir.mkdir(parents=True, exist_ok=True)

    lines_out: list[str] = []
    lines_out.append(f"# Codex-Session: {jsonl_file.stem}")
    lines_out.append("")
    lines_out.append(f"- Quelle: `{jsonl_file}`")
    lines_out.append(f"- Exportiert am: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines_out.append(f"- Modus: `{mode}`")
    lines_out.append("")

    kept = 0

    try:
        vscode_entries = extract_entries_from_vscode_session(jsonl_file)
        if vscode_entries:
            parsed_entries = vscode_entries
        else:
            parsed_entries = []
            with jsonl_file.open("r", encoding="utf-8") as f:
                for idx, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        if mode == "full":
                            parsed_entries.append((None, line, f"Eintrag {idx}", {}))
                        continue

                    parsed_entries.append(normalize_entry(obj))

        for role, content, entry_type, meta in parsed_entries:
            if mode == "full" and role is None and not content.strip() and entry_type.startswith("Eintrag "):
                title = entry_type
                lines_out.append(f"## {title}")
                lines_out.append("")
                lines_out.append("```text")
                lines_out.append(content)
                lines_out.append("```")
                lines_out.append("")
                kept += 1
                continue

            # Nur sinnvolle Rollen exportieren
            if mode == "text-only":
                if role not in {"user", "assistant"}:
                    continue
            elif mode == "readable":
                if role in {"system", "developer", "tool"} and looks_technical(content):
                    continue

            if mode in {"readable", "text-only"}:
                cleaned_content = clean_text_for_readability(content)
                if cleaned_content.strip():
                    content = cleaned_content

            if not content.strip():
                continue

            if mode == "text-only" and role not in {"user", "assistant"} and looks_technical(content):
                continue

            title = role_title(role or entry_type or "Eintrag")
            timestamp = meta.get("timestamp") if meta else None
            if timestamp:
                title = f"{title} ({timestamp})"
            lines_out.append(f"## {title}")

            if mode == "full" and meta:
                meta_text = ", ".join(f"{k}={v}" for k, v in meta.items() if v)
                if meta_text:
                    lines_out.append("")
                    lines_out.append(f"_Meta: {meta_text}_")

            lines_out.append("")

            if mode == "full" and looks_technical(content):
                lines_out.append("```text")
                lines_out.append(content)
                lines_out.append("```")
            else:
                lines_out.append(content)

            lines_out.append("")
            kept += 1

    except Exception as exc:
        lines_out.append("## Fehler")
        lines_out.append("")
        lines_out.append(f"Beim Lesen der Session trat ein Fehler auf: `{exc}`")
        lines_out.append("")

    if kept == 0:
        lines_out.append("## Hinweis")
        lines_out.append("")
        lines_out.append("Es wurden keine passenden Benutzer-/Codex-Texte gefunden.")
        lines_out.append("Versuche ggf. `--mode readable` oder `--mode full`.")
        lines_out.append("")

    out_file.write_text("\n".join(lines_out), encoding="utf-8")
    return out_file


def main() -> int:
    args = parse_args()
    output_dir: Path = args.output
    date_parts = parse_date_filter(args.date)

    if args.input_file:
        jsonl_files = [args.input_file]
    else:
        log_root: Path = args.log_root
        if not log_root.exists():
            print(f"Log-Verzeichnis nicht gefunden: {log_root}")
            return 1
        jsonl_files = sorted(
            f for f in log_root.rglob("rollout-*.jsonl")
            if session_matches_date(f, date_parts)
        )

    if not jsonl_files:
        if args.date:
            print(f"Keine Codex-Session-Logs gefunden für Datum: {args.date}")
        else:
            print("Keine Codex-Session-Logs gefunden.")
        return 0

    exported = 0
    skipped = 0

    for jsonl_file in jsonl_files:
        out_file = output_dir / f"{jsonl_file.stem}.md"
        if should_export(jsonl_file, out_file, args.force):
            export_session(jsonl_file, output_dir, args.mode)
            exported += 1
        else:
            skipped += 1

    print(f"Export abgeschlossen. Neu exportiert: {exported}, übersprungen: {skipped}")
    print(f"Zielordner: {output_dir}")
    print(f"Modus: {args.mode}")
    if args.date:
        print(f"Datum: {args.date}")
    if args.input_file:
        print(f"Eingabedatei: {args.input_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
