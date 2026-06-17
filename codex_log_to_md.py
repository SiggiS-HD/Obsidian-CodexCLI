#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "docs/codex_chat"
PRICING_LAST_UPDATED = "2026-05-16"
PRICING_SOURCE_URL = "https://developers.openai.com/api/docs/pricing"

# Standard API pricing per 1M tokens.
# Update reference: 2026-05-16, based on official OpenAI pricing/model pages.
MODEL_PRICING_PER_1M: dict[str, dict[str, float | None]] = {
    "gpt-5.4": {"input": 2.50, "cached_input": 0.25, "output": 15.00},
    "gpt-5.4-pro": {"input": 20.00, "cached_input": None, "output": 120.00},
    "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.50},
    "gpt-5.4-nano": {"input": 0.20, "cached_input": 0.02, "output": 1.25},
    "gpt-5": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "cached_input": 0.005, "output": 0.40},
    "gpt-5.2": {"input": 1.75, "cached_input": 0.175, "output": 14.00},
    "gpt-5.2-pro": {"input": 21.00, "cached_input": None, "output": 168.00},
    "gpt-5.1": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "o3": {"input": 2.00, "cached_input": 0.50, "output": 8.00},
    "o3-pro": {"input": 20.00, "cached_input": None, "output": 80.00},
    "o3-mini": {"input": 1.10, "cached_input": 0.55, "output": 4.40},
    "o4-mini": {"input": 1.10, "cached_input": 0.275, "output": 4.40},
    "o1": {"input": 15.00, "cached_input": 7.50, "output": 60.00},
    "o1-pro": {"input": 150.00, "cached_input": None, "output": 600.00},
    "o1-mini": {"input": 1.10, "cached_input": 0.55, "output": 4.40},
}


def format_unix_ms(timestamp_ms: Any) -> str | None:
    if not isinstance(timestamp_ms, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


def format_rate(numerator: Any, seconds: float | None) -> str | None:
    if not isinstance(numerator, (int, float)) or not seconds or seconds <= 0:
        return None
    return f"{numerator / seconds:.2f}"


def format_usd(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return f"${value:.6f}"


def resolve_model_pricing(model_name: str | None) -> tuple[str, dict[str, float | None]] | tuple[None, None]:
    if not isinstance(model_name, str) or not model_name.strip():
        return (None, None)

    normalized = model_name.strip().lower()
    if normalized in MODEL_PRICING_PER_1M:
        return (normalized, MODEL_PRICING_PER_1M[normalized])

    for base_model in sorted(MODEL_PRICING_PER_1M, key=len, reverse=True):
        if normalized == base_model or normalized.startswith(base_model + "-"):
            return (base_model, MODEL_PRICING_PER_1M[base_model])

    return (None, None)


def estimate_session_cost(
    model_name: str | None,
    input_tokens: Any,
    cached_input_tokens: Any,
    output_tokens: Any,
    reasoning_output_tokens: Any,
) -> dict[str, Any]:
    pricing_model, pricing = resolve_model_pricing(model_name)
    if pricing is None:
        return {}

    if not isinstance(input_tokens, (int, float)) or not isinstance(output_tokens, (int, float)):
        return {}

    cached_tokens = cached_input_tokens if isinstance(cached_input_tokens, (int, float)) else 0
    cached_tokens = max(0, min(int(cached_tokens), int(input_tokens)))
    uncached_tokens = int(input_tokens) - cached_tokens

    billable_output_tokens = int(output_tokens)
    if isinstance(reasoning_output_tokens, (int, float)):
        billable_output_tokens += int(reasoning_output_tokens)

    input_rate = pricing.get("input")
    cached_input_rate = pricing.get("cached_input")
    output_rate = pricing.get("output")
    if not isinstance(input_rate, (int, float)) or not isinstance(output_rate, (int, float)):
        return {}

    input_cost = uncached_tokens / 1_000_000 * float(input_rate)
    cached_input_cost = None
    if cached_tokens:
        if isinstance(cached_input_rate, (int, float)):
            cached_input_cost = cached_tokens / 1_000_000 * float(cached_input_rate)
        else:
            input_cost += cached_tokens / 1_000_000 * float(input_rate)

    output_cost = billable_output_tokens / 1_000_000 * float(output_rate)
    total_cost = input_cost + output_cost + (cached_input_cost or 0.0)

    return {
        "pricing_model": pricing_model,
        "pricing_input_per_1m": float(input_rate),
        "pricing_cached_input_per_1m": float(cached_input_rate) if isinstance(cached_input_rate, (int, float)) else None,
        "pricing_output_per_1m": float(output_rate),
        "billable_uncached_input_tokens": uncached_tokens,
        "billable_cached_input_tokens": cached_tokens,
        "billable_output_tokens": billable_output_tokens,
        "estimated_input_cost_usd": input_cost,
        "estimated_cached_input_cost_usd": cached_input_cost,
        "estimated_output_cost_usd": output_cost,
        "estimated_total_cost_usd": total_cost,
        "pricing_source_url": PRICING_SOURCE_URL,
        "pricing_last_updated": PRICING_LAST_UPDATED,
    }


def extract_session_metrics(jsonl_file: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    last_token_info: dict[str, Any] | None = None
    started_at_ts: int | float | None = None
    completed_at_ts: int | float | None = None
    duration_ms: int | float | None = None
    session_model: str | None = None
    model_provider: str | None = None

    with jsonl_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") == "session_meta":
                payload = obj.get("payload")
                if isinstance(payload, dict):
                    provider = payload.get("model_provider")
                    if isinstance(provider, str) and provider.strip():
                        model_provider = provider.strip()
                continue

            if obj.get("type") == "turn_context":
                payload = obj.get("payload")
                if isinstance(payload, dict):
                    model = payload.get("model")
                    if isinstance(model, str) and model.strip():
                        session_model = model.strip()
                continue

            if obj.get("type") != "event_msg":
                continue

            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue

            payload_type = payload.get("type")
            if payload_type == "task_started":
                started_at = payload.get("started_at")
                if isinstance(started_at, (int, float)):
                    started_at_ts = started_at
            elif payload_type == "task_complete":
                completed_at = payload.get("completed_at")
                if isinstance(completed_at, (int, float)):
                    completed_at_ts = completed_at
                payload_duration_ms = payload.get("duration_ms")
                if isinstance(payload_duration_ms, (int, float)):
                    duration_ms = payload_duration_ms
            elif payload_type == "token_count":
                info = payload.get("info")
                if isinstance(info, dict):
                    last_token_info = info

    if isinstance(duration_ms, (int, float)):
        metrics["duration_ms"] = duration_ms
    elif (
        isinstance(started_at_ts, (int, float))
        and isinstance(completed_at_ts, (int, float))
        and completed_at_ts >= started_at_ts
    ):
        metrics["duration_ms"] = (completed_at_ts - started_at_ts) * 1000

    if isinstance(started_at_ts, (int, float)):
        metrics["started_at"] = int(started_at_ts)
    if isinstance(completed_at_ts, (int, float)):
        metrics["completed_at"] = int(completed_at_ts)
    if session_model:
        metrics["session_model"] = session_model
    if model_provider:
        metrics["model_provider"] = model_provider

    if last_token_info:
        total_usage = last_token_info.get("total_token_usage")
        last_usage = last_token_info.get("last_token_usage")
        if isinstance(total_usage, dict):
            metrics["total_token_usage"] = total_usage
        if isinstance(last_usage, dict):
            metrics["last_token_usage"] = last_usage
        model_context_window = last_token_info.get("model_context_window")
        if isinstance(model_context_window, (int, float)):
            metrics["model_context_window"] = int(model_context_window)

    return metrics


def detect_session_originator_slug(jsonl_file: Path) -> str:
    source_value: Any = None
    originator_value: Any = None

    with jsonl_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue

            if source_value is None and "source" in payload:
                source_value = payload.get("source")
            if originator_value is None and "originator" in payload:
                originator_value = payload.get("originator")

            if source_value is not None and originator_value is not None:
                break

    originator_text = originator_value.strip().lower() if isinstance(originator_value, str) else ""
    source_text = source_value.strip().lower() if isinstance(source_value, str) else ""
    normalized_originator = re.sub(r"[^a-z0-9]+", "_", originator_text).strip("_")

    if normalized_originator == "codex_vscode":
        return "codex_vscode"
    if normalized_originator == "codex_desktop":
        return "codex_desktop"
    if normalized_originator == "codex_exec":
        return "codex_obsidian"
    if source_text == "vscode":
        return "codex_vscode"
    if source_text == "exec":
        return "codex_obsidian"
    return "codex_unknown"


def build_output_markdown_path(jsonl_file: Path, output_dir: Path) -> Path:
    originator_slug = detect_session_originator_slug(jsonl_file)
    return output_dir / f"{originator_slug}_{jsonl_file.stem}.md"


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
    out_file = build_output_markdown_path(jsonl_file, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines_out: list[str] = []
    lines_out.append(f"# Codex-Session: {jsonl_file.stem}")
    lines_out.append("")
    lines_out.append(f"- Quelle: `{jsonl_file}`")
    lines_out.append(f"- Exportiert am: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines_out.append(f"- Modus: `{mode}`")

    session_metrics = extract_session_metrics(jsonl_file)
    duration_ms = session_metrics.get("duration_ms")
    duration_seconds = duration_ms / 1000 if isinstance(duration_ms, (int, float)) else None
    total_usage = session_metrics.get("total_token_usage", {})
    if not isinstance(total_usage, dict):
        total_usage = {}

    input_tokens = total_usage.get("input_tokens")
    cached_input_tokens = total_usage.get("cached_input_tokens")
    output_tokens = total_usage.get("output_tokens")
    reasoning_output_tokens = total_usage.get("reasoning_output_tokens")
    total_tokens = total_usage.get("total_tokens")
    model_context_window = session_metrics.get("model_context_window")
    session_model = session_metrics.get("session_model")
    model_provider = session_metrics.get("model_provider")
    cost_estimate = estimate_session_cost(
        session_model,
        input_tokens,
        cached_input_tokens,
        output_tokens,
        reasoning_output_tokens,
    )

    metrics_rows: list[tuple[str, Any]] = []
    if session_model:
        metrics_rows.append(("Modell", session_model))
    if model_provider:
        metrics_rows.append(("Provider", model_provider))
    if duration_seconds is not None:
        metrics_rows.append(("Dauer E2E (s)", f"{duration_seconds:.3f}"))
    if isinstance(input_tokens, (int, float)):
        metrics_rows.append(("Input-Tokens", int(input_tokens)))
    if isinstance(cached_input_tokens, (int, float)):
        metrics_rows.append(("Cached Input-Tokens", int(cached_input_tokens)))
    if isinstance(output_tokens, (int, float)):
        metrics_rows.append(("Output-Tokens", int(output_tokens)))
    if isinstance(reasoning_output_tokens, (int, float)):
        metrics_rows.append(("Reasoning Output-Tokens", int(reasoning_output_tokens)))
    if isinstance(total_tokens, (int, float)):
        metrics_rows.append(("Total Tokens", int(total_tokens)))
    if isinstance(model_context_window, (int, float)):
        metrics_rows.append(("Context Window", int(model_context_window)))

    output_tps = format_rate(output_tokens, duration_seconds)
    if output_tps is not None:
        metrics_rows.append(("Output-Tokens/s (E2E)", output_tps))

    visible_plus_reasoning = None
    if isinstance(output_tokens, (int, float)):
        visible_plus_reasoning = output_tokens
        if isinstance(reasoning_output_tokens, (int, float)):
            visible_plus_reasoning += reasoning_output_tokens
    combined_output_tps = format_rate(visible_plus_reasoning, duration_seconds)
    if combined_output_tps is not None:
        metrics_rows.append(("Output+Reasoning-Tokens/s (E2E)", combined_output_tps))

    total_tps = format_rate(total_tokens, duration_seconds)
    if total_tps is not None:
        metrics_rows.append(("Total Tokens/s (E2E)", total_tps))

    if cost_estimate:
        pricing_model = cost_estimate.get("pricing_model")
        if pricing_model:
            metrics_rows.append(("Kostenbasis Modell", pricing_model))

        input_cost = format_usd(cost_estimate.get("estimated_input_cost_usd"))
        if input_cost is not None:
            metrics_rows.append(("Geschaetzte Input-Kosten", input_cost))

        cached_input_cost = format_usd(cost_estimate.get("estimated_cached_input_cost_usd"))
        if cached_input_cost is not None:
            metrics_rows.append(("Geschaetzte Cached-Input-Kosten", cached_input_cost))

        output_cost = format_usd(cost_estimate.get("estimated_output_cost_usd"))
        if output_cost is not None:
            metrics_rows.append(("Geschaetzte Output-Kosten", output_cost))

        total_cost = format_usd(cost_estimate.get("estimated_total_cost_usd"))
        if total_cost is not None:
            metrics_rows.append(("Geschaetzte Gesamtkosten", total_cost))

        metrics_rows.append(("Preisstand", cost_estimate["pricing_last_updated"]))

    if metrics_rows:
        lines_out.append("")
        lines_out.append("## Laufzeit & Token")
        lines_out.append("")
        lines_out.append("| Kennzahl | Wert |")
        lines_out.append("| --- | ---: |")
        for label, value in metrics_rows:
            lines_out.append(f"| {label} | {value} |")
        if cost_estimate:
            lines_out.append("")
            lines_out.append(
                "_Kostenschaetzung auf Basis der OpenAI API Standardpreise. "
                "Cached Input wird rabattiert berechnet; `reasoning_output_tokens` werden als Output-Tokens mitgerechnet. "
                f"Quelle: {cost_estimate['pricing_source_url']}_"
            )
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
        out_file = build_output_markdown_path(jsonl_file, output_dir)
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
