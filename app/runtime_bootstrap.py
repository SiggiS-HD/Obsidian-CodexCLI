import os
import shutil
import subprocess
import sys
from pathlib import Path


def _is_unc_path(path: Path) -> bool:
    return str(path).startswith("\\\\")


def _derive_vault_name(repo_root: Path) -> str | None:
    if repo_root.name != "CodexCLI":
        return None

    addon_dir = repo_root.parent
    if addon_dir.name != ".AddOn":
        return None

    vault_name = addon_dir.parent.name
    return vault_name or None


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(os.path.normpath(str(right)))


def _bootstrap_local_venv(local_venv_path: Path, requirements_path: Path) -> None:
    local_venv_path.parent.mkdir(parents=True, exist_ok=True)

    launcher: list[str] | None = None
    if shutil.which("py"):
        launcher = ["py", "-3.12"]
    elif shutil.which("python"):
        launcher = ["python"]
    elif sys.executable:
        launcher = [sys.executable]

    if launcher is None:
        raise RuntimeError('Konnte weder "py" noch "python" finden.')

    subprocess.run([*launcher, "-m", "venv", str(local_venv_path)], check=True)

    python_exe = local_venv_path / "Scripts" / "python.exe"
    if not python_exe.exists():
        raise RuntimeError(f"venv wurde erstellt, aber python.exe fehlt: {python_exe}")

    subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    if not requirements_path.exists():
        raise RuntimeError(f"requirements.txt nicht gefunden: {requirements_path}")

    subprocess.run([str(python_exe), "-m", "pip", "install", "-r", str(requirements_path)], check=True)


def ensure_preferred_python(argv: list[str]) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if not _is_unc_path(repo_root):
        return

    vault_name = _derive_vault_name(repo_root)
    if not vault_name:
        return

    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_appdata:
        return

    local_venv_path = Path(local_appdata) / vault_name / "CodexCLI" / ".venv"
    expected_python = local_venv_path / "Scripts" / "python.exe"
    current_python = Path(sys.executable)

    os.environ["CODEXCLI_VENV"] = vault_name
    os.environ["CODEXCLI_VENV_SOURCE"] = "vault-name-from-unc-path-python"
    os.environ["CODEXCLI_EXPECTED_PYTHON"] = str(expected_python)

    if not expected_python.exists():
        print(f'[CodexCLI] Hinweis: Lokale UNC-venv fehlt. Bootstrappe "{local_venv_path}"...')
        try:
            _bootstrap_local_venv(local_venv_path, repo_root / "requirements.txt")
        except subprocess.CalledProcessError as error:
            os.environ["CODEXCLI_RELAUNCH_STATUS"] = "bootstrap-failed"
            raise SystemExit(error.returncode) from error
        except Exception as error:
            os.environ["CODEXCLI_RELAUNCH_STATUS"] = "bootstrap-failed"
            print(f"[CodexCLI] ERROR: {error}")
            raise SystemExit(2) from error

    if _same_path(current_python, expected_python):
        os.environ["CODEXCLI_RELAUNCH_STATUS"] = "already-using-expected-python"
        return

    if os.environ.get("CODEXCLI_RELAUNCHED") == "1":
        os.environ["CODEXCLI_RELAUNCH_STATUS"] = "relaunch-guard-active"
        return

    env = os.environ.copy()
    env["CODEXCLI_VENV"] = vault_name
    env["CODEXCLI_VENV_SOURCE"] = "vault-name-from-unc-path-python"
    env["CODEXCLI_EXPECTED_PYTHON"] = str(expected_python)
    env["CODEXCLI_RELAUNCHED"] = "1"
    env["CODEXCLI_RELAUNCH_STATUS"] = "relaunching-into-expected-python"

    result = subprocess.run([str(expected_python), str(repo_root / "main.py"), *argv], env=env, cwd=str(Path.cwd()))
    raise SystemExit(result.returncode)
