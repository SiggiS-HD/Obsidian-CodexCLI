import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import (
    get_image_model,
    get_image_quality,
    get_image_timeout_seconds,
    get_openai_api_key,
    get_openai_base_url,
)


@dataclass(frozen=True)
class ImageGenerationResult:
    image_bytes: bytes | None
    error: str | None = None


def generate_png_image(prompt: str, *, aspect_ratio: str | None = None) -> ImageGenerationResult:
    api_key = get_openai_api_key()
    if not api_key:
        return ImageGenerationResult(
            image_bytes=None,
            error="Bildgenerierung nicht moeglich: OPENAI_API_KEY ist nicht gesetzt.",
        )

    payload: dict[str, str] = {
        "model": get_image_model(),
        "prompt": prompt,
        "quality": get_image_quality(),
    }
    size = _aspect_to_size(aspect_ratio)
    if size:
        payload["size"] = size

    body = json.dumps(payload).encode("utf-8")
    endpoint = get_openai_base_url().rstrip("/") + "/images/generations"
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=get_image_timeout_seconds()) as response:
            response_body = response.read()
    except urllib.error.HTTPError as error:
        detail = _read_http_error_detail(error)
        return ImageGenerationResult(
            image_bytes=None,
            error=f"Bildgenerierung fehlgeschlagen (HTTP {error.code}): {detail}",
        )
    except urllib.error.URLError as error:
        return ImageGenerationResult(
            image_bytes=None,
            error=f"Bildgenerierung fehlgeschlagen (Netzwerkfehler): {error.reason}",
        )
    except TimeoutError:
        return ImageGenerationResult(
            image_bytes=None,
            error="Bildgenerierung fehlgeschlagen: Zeitueberschreitung.",
        )
    except Exception as error:
        return ImageGenerationResult(
            image_bytes=None,
            error=f"Bildgenerierung fehlgeschlagen: {error}",
        )

    try:
        payload_json = json.loads(response_body.decode("utf-8", errors="replace"))
        b64_value = payload_json["data"][0]["b64_json"]
        image_bytes = base64.b64decode(b64_value)
    except Exception as error:
        return ImageGenerationResult(
            image_bytes=None,
            error=f"Bildgenerierung fehlgeschlagen: ungueltige API-Antwort ({error}).",
        )

    if not image_bytes:
        return ImageGenerationResult(
            image_bytes=None,
            error="Bildgenerierung fehlgeschlagen: API lieferte leere Bilddaten.",
        )

    return ImageGenerationResult(image_bytes=image_bytes)


def _aspect_to_size(aspect_ratio: str | None) -> str | None:
    mapping = {
        "1:1": "1024x1024",
        # API supports: 1024x1024, 1024x1536, 1536x1024, auto.
        # 4:3/16:9 are approximated via auto because no exact size exists.
        "4:3": "auto",
        "16:9": "auto",
    }
    if not aspect_ratio:
        return None
    return mapping.get(aspect_ratio.strip())


def _read_http_error_detail(error: urllib.error.HTTPError) -> str:
    try:
        body = error.read().decode("utf-8", errors="replace")
    except Exception:
        return "Keine Details von der API erhalten."

    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            error_obj = payload.get("error")
            if isinstance(error_obj, dict):
                message = error_obj.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
    except Exception:
        pass

    return body.strip() or "Keine Details von der API erhalten."
