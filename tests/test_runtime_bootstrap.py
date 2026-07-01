import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.runtime_bootstrap import ensure_preferred_python


class RuntimeBootstrapTests(unittest.TestCase):
    @patch("app.runtime_bootstrap.subprocess.run")
    @patch("app.runtime_bootstrap.Path.cwd", return_value=Path(r"C:\tmp"))
    @patch("app.runtime_bootstrap.Path.exists")
    @patch("app.runtime_bootstrap.Path.resolve")
    @patch.dict(
        os.environ,
        {
            "LOCALAPPDATA": r"C:\Users\siggi\AppData\Local",
            "CODEXCLI_VENV": "Siggiverse",
        },
        clear=False,
    )
    def test_unc_repo_relaunches_into_vault_specific_local_venv(
        self,
        mock_resolve,
        mock_exists,
        _mock_cwd,
        mock_subprocess_run,
    ) -> None:
        repo_root = Path(r"\\CL10NAS\lyt\Test\.AddOn\CodexCLI")
        expected_python = Path(r"C:\Users\siggi\AppData\Local\Test\CodexCLI\.venv\Scripts\python.exe")

        def resolve_side_effect() -> Path:
            if mock_resolve.call_count == 1:
                return repo_root / "tests" / "test_runtime_bootstrap.py"
            return Path(__file__)

        mock_resolve.side_effect = resolve_side_effect
        mock_exists.return_value = True
        mock_subprocess_run.return_value.returncode = 0

        with patch("sys.executable", r"C:\Users\siggi\AppData\Local\Siggiverse\CodexCLI\.venv\Scripts\python.exe"):
            with self.assertRaises(SystemExit) as exit_context:
                ensure_preferred_python(["diag"])

        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(mock_subprocess_run.call_count, 1)

        relaunch_call = mock_subprocess_run.call_args
        self.assertEqual(
            relaunch_call.args[0],
            [str(expected_python), str(repo_root / "main.py"), "diag"],
        )
        self.assertEqual(relaunch_call.kwargs["cwd"], r"C:\tmp")
        self.assertEqual(relaunch_call.kwargs["env"]["CODEXCLI_VENV"], "Test")
        self.assertEqual(
            relaunch_call.kwargs["env"]["CODEXCLI_VENV_SOURCE"],
            "vault-name-from-unc-path-python",
        )
        self.assertEqual(relaunch_call.kwargs["env"]["CODEXCLI_RELAUNCHED"], "1")
        self.assertEqual(
            relaunch_call.kwargs["env"]["CODEXCLI_EXPECTED_PYTHON"],
            str(expected_python),
        )
