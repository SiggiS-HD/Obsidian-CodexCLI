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

    @patch("subprocess.run")
    @patch("app.codex_client.get_text_model", return_value=None)
    @patch("app.codex_client.get_codex_cmd", return_value="codex.cmd")
    @patch("app.codex_client.tempfile.gettempdir", return_value=r"C:\Temp")
    def test_run_codex_uses_local_temp_cwd_for_unc_vault_root(
        self,
        _mock_gettempdir,
        _mock_get_codex_cmd,
        _mock_get_text_model,
        mock_subprocess_run,
    ) -> None:
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "ok"
        mock_subprocess_run.return_value.stderr = ""

        with unittest.mock.patch("tempfile.TemporaryDirectory") as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = r"C:\Temp\codexcli\tmp\codex-run-123"
            mock_tempdir.return_value.__exit__.return_value = False

            run_codex("hello", vault_root=Path(r"\\CL10NAS\lyt\Siggiverse"))

        _args, kwargs = mock_subprocess_run.call_args
        self.assertEqual(kwargs["cwd"], r"C:\Temp\codexcli\tmp\codex-run-123")
        tempdir_kwargs = mock_tempdir.call_args.kwargs
        self.assertEqual(tempdir_kwargs["prefix"], "codex-run-")
        self.assertEqual(Path(tempdir_kwargs["dir"]), Path(r"C:\Temp\codexcli\tmp"))

    @patch("subprocess.run")
    @patch("app.codex_client.get_text_model", return_value="gpt-5.3-codex")
    @patch("app.codex_client.get_codex_cmd", return_value="codex.cmd")
    def test_run_codex_retries_with_fallback_model_when_model_is_not_supported(
        self,
        _mock_get_codex_cmd,
        _mock_get_text_model,
        mock_subprocess_run,
    ) -> None:
        unsupported_result = unittest.mock.Mock(
            returncode=1,
            stdout="",
            stderr=(
                "ERROR: {\"type\":\"error\",\"status\":400,\"error\":{"
                "\"type\":\"invalid_request_error\","
                "\"message\":\"The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account.\"}}"
            ),
        )
        success_result = unittest.mock.Mock(returncode=0, stdout="ok", stderr="")
        mock_subprocess_run.side_effect = [unsupported_result, success_result]

        result = run_codex("hello")

        self.assertEqual(mock_subprocess_run.call_count, 2)
        first_command = mock_subprocess_run.call_args_list[0].args[0]
        second_command = mock_subprocess_run.call_args_list[1].args[0]
        self.assertIn("--model", first_command)
        self.assertIn("gpt-5.3-codex", first_command)
        self.assertIn("--model", second_command)
        fallback_model_index = second_command.index("--model")
        self.assertEqual(second_command[fallback_model_index + 1], "gpt-5.4")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok")

    @patch("subprocess.run")
    @patch("app.codex_client.get_text_model", return_value="gpt-5.3-codex")
    @patch("app.codex_client.get_codex_cmd", return_value="codex.cmd")
    def test_run_codex_retries_with_fallback_model_when_model_error_is_in_stdout(
        self,
        _mock_get_codex_cmd,
        _mock_get_text_model,
        mock_subprocess_run,
    ) -> None:
        unsupported_result = unittest.mock.Mock(
            returncode=1,
            stdout=(
                "ERROR: {\"type\":\"error\",\"status\":400,\"error\":{"
                "\"type\":\"invalid_request_error\","
                "\"message\":\"The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account.\"}}"
            ),
            stderr="",
        )
        success_result = unittest.mock.Mock(returncode=0, stdout="ok", stderr="")
        mock_subprocess_run.side_effect = [unsupported_result, success_result]

        result = run_codex("hello")

        self.assertEqual(mock_subprocess_run.call_count, 2)
        second_command = mock_subprocess_run.call_args_list[1].args[0]
        fallback_model_index = second_command.index("--model")
        self.assertEqual(second_command[fallback_model_index + 1], "gpt-5.4")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok")

    @patch("subprocess.run")
    @patch("app.codex_client.get_text_model", return_value=None)
    @patch("app.codex_client.get_codex_cmd", return_value="codex.cmd")
    def test_run_codex_retries_with_fallback_model_when_default_cli_model_is_not_supported(
        self,
        _mock_get_codex_cmd,
        _mock_get_text_model,
        mock_subprocess_run,
    ) -> None:
        unsupported_result = unittest.mock.Mock(
            returncode=1,
            stdout=(
                "ERROR: {\"type\":\"error\",\"status\":400,\"error\":{"
                "\"type\":\"invalid_request_error\","
                "\"message\":\"The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account.\"}}"
            ),
            stderr="",
        )
        success_result = unittest.mock.Mock(returncode=0, stdout="ok", stderr="")
        mock_subprocess_run.side_effect = [unsupported_result, success_result]

        result = run_codex("hello")

        self.assertEqual(mock_subprocess_run.call_count, 2)
        first_command = mock_subprocess_run.call_args_list[0].args[0]
        second_command = mock_subprocess_run.call_args_list[1].args[0]
        self.assertNotIn("--model", first_command)
        fallback_model_index = second_command.index("--model")
        self.assertEqual(second_command[fallback_model_index + 1], "gpt-5.4")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok")


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
