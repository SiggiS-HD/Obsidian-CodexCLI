import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import get_codex_cmd, get_runtime_tmp_root, get_text_model


FALLBACK_TEXT_MODEL = "gpt-5.4"


@dataclass(frozen=True)
class CodexResult:
    returncode: int
    stdout: str
    stderr: str
    start_error: str | None = None


def _is_unc_path(path: Path) -> bool:
    return str(path).startswith("\\\\")


def _get_run_tmp_root(vault_root: Path) -> Path:
    if _is_unc_path(vault_root):
        # `cmd.exe` kann nicht direkt in einem UNC-cwd starten.
        return Path(tempfile.gettempdir()) / "codexcli" / "tmp"

    return get_runtime_tmp_root(vault_root)


def _is_unsupported_model_error(output_text: str) -> bool:
    lowered = output_text.lower()
    return "invalid_request_error" in lowered and "model is not supported" in lowered


def _build_command(
    configured_model: str | None,
    image_paths: list[Path] | None,
) -> list[str]:
    command: list[str] = [
        get_codex_cmd(),
        "exec",
        "--skip-git-repo-check",
    ]

    if configured_model:
        command.extend(["--model", configured_model])

    if image_paths:
        for image_path in image_paths:
            command.extend(["--image", str(image_path)])

    command.append("-")
    return command


def _should_retry_with_fallback_model(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode == 0:
        return False

    combined_output = f"{result.stdout}\n{result.stderr}"
    return _is_unsupported_model_error(combined_output)


def run_codex(
    prompt: str,
    *,
    image_paths: list[Path] | None = None,
    vault_root: Path | None = None,
) -> CodexResult:
    configured_model = get_text_model()
    command = _build_command(configured_model, image_paths)

    run_kwargs = {
        "input": prompt,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }

    try:
        if vault_root is not None:
            runtime_tmp_root = _get_run_tmp_root(vault_root)
            runtime_tmp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="codex-run-", dir=runtime_tmp_root) as run_dir:
                result = subprocess.run(
                    command,
                    cwd=run_dir,
                    **run_kwargs,
                )
                if _should_retry_with_fallback_model(result):
                    fallback_command = _build_command(FALLBACK_TEXT_MODEL, image_paths)
                    result = subprocess.run(
                        fallback_command,
                        cwd=run_dir,
                        **run_kwargs,
                    )
        else:
            result = subprocess.run(
                command,
                **run_kwargs,
            )
            if _should_retry_with_fallback_model(result):
                fallback_command = _build_command(FALLBACK_TEXT_MODEL, image_paths)
                result = subprocess.run(
                    fallback_command,
                    **run_kwargs,
                )
    except Exception as error:
        return CodexResult(returncode=1, stdout="", stderr="", start_error=str(error))

    return CodexResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
