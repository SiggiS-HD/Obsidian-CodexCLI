import os
from pathlib import Path

APP_NAME = "Obsidian Codex connector"


# Codex CLI
# - Default: expect `codex.cmd` in PATH (typical npm global install on Windows).
# - Override: set `CODEXCLI_CODEX_CMD` to an absolute path (more robust for Obsidian/cmd environments).
CODEX_CMD_ENV = "CODEXCLI_CODEX_CMD"
CODEX_CMD_DEFAULT = "codex.cmd"
TEXT_MODEL_ENV = "CODEXCLI_TEXT_MODEL"
TEXT_MODEL_FORCED: str | None = None


# PDF OCR (used automatically when a PDF contains no extractable text layer)
PDF_OCR_MAX_PAGES = 2
PDF_OCR_DPI = 150
PDF_OCR_LANG_DEFAULT = "deu+eng"

PDF_OCR_LANG_ENV = "CODEXCLI_OCR_LANG"
PDF_OCR_TESSERACT_CMD_ENV = "CODEXCLI_TESSERACT_CMD"
PDF_OCR_POPPLER_PATH_ENV = "CODEXCLI_POPPLER_PATH"


# OpenAI image generation (used for SAVE_AS: *.png)
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_BASE_URL_ENV = "CODEXCLI_OPENAI_BASE_URL"
OPENAI_BASE_URL_DEFAULT = "https://api.openai.com/v1"

IMAGE_MODEL_ENV = "CODEXCLI_IMAGE_MODEL"
IMAGE_MODEL_DEFAULT = "gpt-image-1"
IMAGE_QUALITY_ENV = "CODEXCLI_IMAGE_QUALITY"
IMAGE_QUALITY_DEFAULT = "high"
IMAGE_TIMEOUT_SECONDS_ENV = "CODEXCLI_IMAGE_TIMEOUT_SECONDS"
IMAGE_TIMEOUT_SECONDS_DEFAULT = 120


# PDF RAG / index cache
INDEX_ROOT_ENV = "CODEXCLI_INDEX_ROOT"
INDEX_ROOT_DIRNAME = ".codexcli"
INDEX_SUBDIR = "index"
RUNTIME_TMP_SUBDIR = "tmp"
RAG_MAX_INDEX_TEXT_CHARS = 700_000


def get_env(name: str) -> str | None:
	value = os.environ.get(name)
	return value.strip() if value and value.strip() else None


def get_codex_cmd() -> str:
	return get_env(CODEX_CMD_ENV) or CODEX_CMD_DEFAULT


def get_text_model() -> str | None:
	return TEXT_MODEL_FORCED or get_env(TEXT_MODEL_ENV)


# Backward-compatible constant used by older imports.
CODEX_CMD = get_codex_cmd()


def get_pdf_ocr_lang() -> str:
	return get_env(PDF_OCR_LANG_ENV) or PDF_OCR_LANG_DEFAULT


def get_pdf_ocr_tesseract_cmd() -> str | None:
	return get_env(PDF_OCR_TESSERACT_CMD_ENV)


def get_pdf_ocr_poppler_path() -> str | None:
	return get_env(PDF_OCR_POPPLER_PATH_ENV)


def get_openai_api_key() -> str | None:
	return get_env(OPENAI_API_KEY_ENV)


def get_openai_base_url() -> str:
	return get_env(OPENAI_BASE_URL_ENV) or OPENAI_BASE_URL_DEFAULT


def get_image_model() -> str:
	return get_env(IMAGE_MODEL_ENV) or IMAGE_MODEL_DEFAULT


def get_image_quality() -> str:
	return get_env(IMAGE_QUALITY_ENV) or IMAGE_QUALITY_DEFAULT


def get_image_timeout_seconds() -> int:
	raw = get_env(IMAGE_TIMEOUT_SECONDS_ENV)
	if not raw:
		return IMAGE_TIMEOUT_SECONDS_DEFAULT
	try:
		seconds = int(raw)
	except ValueError:
		return IMAGE_TIMEOUT_SECONDS_DEFAULT
	return seconds if seconds > 0 else IMAGE_TIMEOUT_SECONDS_DEFAULT


def get_index_root(vault_root: str | Path) -> Path:
	override = get_env(INDEX_ROOT_ENV)
	if override:
		return Path(override).expanduser()

	return Path(vault_root) / INDEX_ROOT_DIRNAME / INDEX_SUBDIR


def get_runtime_tmp_root(vault_root: str | Path) -> Path:
	return Path(vault_root) / INDEX_ROOT_DIRNAME / RUNTIME_TMP_SUBDIR
