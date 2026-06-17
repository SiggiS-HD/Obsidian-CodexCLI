import base64
import json
import unittest
from unittest.mock import patch

from app.image_client import generate_png_image


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class ImageClientTests(unittest.TestCase):
    def test_generate_png_image_requires_api_key(self) -> None:
        with patch("app.image_client.get_openai_api_key", return_value=None):
            result = generate_png_image("Erzeuge ein Diagramm")

        self.assertIsNone(result.image_bytes)
        self.assertIsNotNone(result.error)
        self.assertIn("OPENAI_API_KEY", result.error or "")

    def test_generate_png_image_success_decodes_b64_and_sets_size_from_aspect(self) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\nDATA"
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout=0):
            captured["timeout"] = timeout
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeHttpResponse(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    ]
                }
            )

        with (
            patch("app.image_client.get_openai_api_key", return_value="test-key"),
            patch("app.image_client.get_openai_base_url", return_value="https://api.openai.com/v1"),
            patch("app.image_client.get_image_model", return_value="gpt-image-1"),
            patch("app.image_client.get_image_quality", return_value="high"),
            patch("app.image_client.get_image_timeout_seconds", return_value=42),
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            result = generate_png_image("Erzeuge ein Diagramm", aspect_ratio="16:9")

        self.assertIsNone(result.error)
        self.assertEqual(result.image_bytes, image_bytes)
        self.assertEqual(captured["timeout"], 42)
        self.assertEqual(captured["url"], "https://api.openai.com/v1/images/generations")
        payload = captured["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(payload.get("size"), "auto")
        self.assertEqual(payload.get("prompt"), "Erzeuge ein Diagramm")

    def test_generate_png_image_timeout_returns_readable_error(self) -> None:
        with (
            patch("app.image_client.get_openai_api_key", return_value="test-key"),
            patch("urllib.request.urlopen", side_effect=TimeoutError()),
        ):
            result = generate_png_image("Erzeuge ein Diagramm")

        self.assertIsNone(result.image_bytes)
        self.assertIsNotNone(result.error)
        self.assertIn("Zeitueberschreitung", result.error or "")
