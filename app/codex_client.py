import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import get_codex_cmd, get_runtime_tmp_root, get_text_model


@dataclass(frozen=True)
class CodexResult:
    returncode: int
    stdout: str
    stderr: str
    start_error: str | None = None


def run_codex(
    prompt: str,
    *,
    image_paths: list[Path] | None = None,
    vault_root: Path | None = None,
) -> CodexResult:
    configured_model = get_text_model()

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

    run_kwargs = {
        "input": prompt,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }

    try:
        if vault_root is not None:
            runtime_tmp_root = get_runtime_tmp_root(vault_root)
            runtime_tmp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="codex-run-", dir=runtime_tmp_root) as run_dir:
                result = subprocess.run(
                    command,
                    cwd=run_dir,
                    **run_kwargs,
                )
        else:
            result = subprocess.run(
                command,
                **run_kwargs,
            )
    except Exception as error:
        return CodexResult(returncode=1, stdout="", stderr="", start_error=str(error))

    return CodexResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
