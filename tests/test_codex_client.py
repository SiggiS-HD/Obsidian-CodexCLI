import unittest
from pathlib import Path
from unittest.mock import patch

from app.codex_client import run_codex
from app.config import get_text_model


class CodexClientTests(unittest.TestCase):
    @patch("subprocess.run")
    @patch("app.codex_client.get_text_model", return_value=None)
    @patch("app.codex_client.get_codex_cmd", return_value="codex.cmd")
    def test_run_codex_uses_codex_cli_default_when_no_text_model_is_configured(
        self,
        _mock_get_codex_cmd,
        _mock_get_text_model,
        mock_subprocess_run,
    ) -> None:
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "ok"
        mock_subprocess_run.return_value.stderr = ""

        run_codex("hello")

        args, kwargs = mock_subprocess_run.call_args
        command = args[0]
        self.assertEqual(command[:3], ["codex.cmd", "exec", "--skip-git-repo-check"])
        self.assertNotIn("--model", command)
        self.assertEqual(command[-1], "-")
        self.assertEqual(kwargs["input"], "hello")
        self.assertNotIn("cwd", kwargs)

    @patch("subprocess.run")
    @patch("app.codex_client.get_text_model", return_value="gpt-5.5")
    @patch("app.codex_client.get_codex_cmd", return_value="codex.cmd")
    def test_run_codex_with_env_override_model_adds_model_flag(
        self,
        _mock_get_codex_cmd,
        _mock_get_text_model,
        mock_subprocess_run,
    ) -> None:
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "ok"
        mock_subprocess_run.return_value.stderr = ""

        run_codex("hello")

        args, _kwargs = mock_subprocess_run.call_args
        command = args[0]
        self.assertIn("--model", command)
        model_index = command.index("--model")
        self.assertEqual(command[model_index + 1], "gpt-5.5")

    @patch("subprocess.run")
    @patch("app.codex_client.get_text_model", return_value="gpt-5.4")
    @patch("app.codex_client.get_codex_cmd", return_value="codex.cmd")
    def test_run_codex_with_images_keeps_model_and_image_flags(
        self,
        _mock_get_codex_cmd,
        _mock_get_text_model,
        mock_subprocess_run,
    ) -> None:
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "ok"
        mock_subprocess_run.return_value.stderr = ""

        run_codex("hello", image_paths=[Path("a.png"), Path("b.png")])

        args, _kwargs = mock_subprocess_run.call_args
        command = args[0]
        self.assertIn("--model", command)
        self.assertEqual(command.count("--image"), 2)
        self.assertIn("a.png", command)
        self.assertIn("b.png", command)
        self.assertEqual(command[-1], "-")

    @patch("subprocess.run")
    @patch("app.codex_client.get_text_model", return_value=None)
    @patch("app.codex_client.get_codex_cmd", return_value="codex.cmd")
    def test_run_codex_uses_temporary_cwd_under_dot_codexcli_when_vault_root_is_given(
        self,
        _mock_get_codex_cmd,
        _mock_get_text_model,
        mock_subprocess_run,
    ) -> None:
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "ok"
        mock_subprocess_run.return_value.stderr = ""

        with unittest.mock.patch("tempfile.TemporaryDirectory") as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = r"D:\Ideas\.codexcli\tmp\codex-run-123"
            mock_tempdir.return_value.__exit__.return_value = False

            run_codex("hello", vault_root=Path(r"D:\Ideas"))

        args, kwargs = mock_subprocess_run.call_args
        command = args[0]
        self.assertEqual(command[:3], ["codex.cmd", "exec", "--skip-git-repo-check"])
        self.assertEqual(kwargs["cwd"], r"D:\Ideas\.codexcli\tmp\codex-run-123")
        self.assertEqual(kwargs["input"], "hello")
        tempdir_kwargs = mock_tempdir.call_args.kwargs
        self.assertEqual(tempdir_kwargs["prefix"], "codex-run-")
        self.assertEqual(Path(tempdir_kwargs["dir"]), Path(r"D:\Ideas\.codexcli\tmp"))


class ConfigTextModelTests(unittest.TestCase):
    @patch.dict("os.environ", {"CODEXCLI_TEXT_MODEL": "gpt-5.5"}, clear=False)
    @patch("app.config.TEXT_MODEL_FORCED", "gpt-5.4")
    def test_forced_text_model_overrides_env(self) -> None:
        self.assertEqual(get_text_model(), "gpt-5.4")

    @patch.dict("os.environ", {"CODEXCLI_TEXT_MODEL": "gpt-5.5"}, clear=False)
    @patch("app.config.TEXT_MODEL_FORCED", None)
    def test_env_text_model_is_used_when_forced_is_unset(self) -> None:
        self.assertEqual(get_text_model(), "gpt-5.5")

    @patch.dict("os.environ", {}, clear=True)
    @patch("app.config.TEXT_MODEL_FORCED", None)
    def test_codex_cli_default_is_used_when_forced_and_env_are_unset(self) -> None:
        self.assertIsNone(get_text_model())
