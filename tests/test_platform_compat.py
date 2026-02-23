from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


def _import_config_module():
    """Import utils.config even if python-dotenv is not installed locally."""
    sys.modules.pop("utils.config", None)
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None)
    with mock.patch.dict(sys.modules, {"dotenv": fake_dotenv}):
        return importlib.import_module("utils.config")


class ConfigPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config_mod = _import_config_module()

    def test_config_dir_windows_uses_appdata(self) -> None:
        with (
            mock.patch.object(self.config_mod.sys, "platform", "win32"),
            mock.patch.dict(os.environ, {"APPDATA": "C:/Users/test/AppData/Roaming"}, clear=False),
        ):
            self.assertEqual(
                self.config_mod.config_dir(),
                Path("C:/Users/test/AppData/Roaming") / self.config_mod.APP_NAME,
            )

    def test_config_dir_macos_uses_application_support(self) -> None:
        fake_home = Path("/Users/tester")
        with (
            mock.patch.object(self.config_mod.sys, "platform", "darwin"),
            mock.patch.object(self.config_mod.Path, "home", return_value=fake_home),
        ):
            self.assertEqual(
                self.config_mod.config_dir(),
                fake_home / "Library" / "Application Support" / self.config_mod.APP_NAME,
            )

    def test_data_dir_windows_uses_localappdata(self) -> None:
        with (
            mock.patch.object(self.config_mod.sys, "platform", "win32"),
            mock.patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/test/AppData/Local"}, clear=False),
        ):
            self.assertEqual(
                self.config_mod.data_dir(),
                Path("C:/Users/test/AppData/Local") / self.config_mod.APP_NAME,
            )

    def test_data_dir_macos_uses_application_support(self) -> None:
        fake_home = Path("/Users/tester")
        with (
            mock.patch.object(self.config_mod.sys, "platform", "darwin"),
            mock.patch.object(self.config_mod.Path, "home", return_value=fake_home),
        ):
            self.assertEqual(
                self.config_mod.data_dir(),
                fake_home / "Library" / "Application Support" / self.config_mod.APP_NAME,
            )


class LauncherPlatformTests(unittest.TestCase):
    def test_get_python_uses_windows_venv_layout(self) -> None:
        import vigilant

        with tempfile.TemporaryDirectory() as tmp:
            venv_dir = Path(tmp) / "venv"
            win_python = venv_dir / "Scripts" / "python.exe"
            win_python.parent.mkdir(parents=True, exist_ok=True)
            win_python.write_text("", encoding="utf-8")

            with (
                mock.patch.object(vigilant, "VENV_DIR", venv_dir),
                mock.patch.object(vigilant.sys, "platform", "win32"),
            ):
                self.assertEqual(vigilant.get_python(), str(win_python))

    def test_get_python_uses_posix_venv_layout(self) -> None:
        import vigilant

        with tempfile.TemporaryDirectory() as tmp:
            venv_dir = Path(tmp) / "venv"
            posix_python = venv_dir / "bin" / "python"
            posix_python.parent.mkdir(parents=True, exist_ok=True)
            posix_python.write_text("", encoding="utf-8")

            with (
                mock.patch.object(vigilant, "VENV_DIR", venv_dir),
                mock.patch.object(vigilant.sys, "platform", "darwin"),
            ):
                self.assertEqual(vigilant.get_python(), str(posix_python))

    def test_start_web_background_windows_uses_detached_process_flags(self) -> None:
        import vigilant

        fake_proc = types.SimpleNamespace(pid=3210)
        with (
            mock.patch.object(vigilant, "get_python", return_value="python"),
            mock.patch.object(vigilant.sys, "platform", "win32"),
            mock.patch.object(vigilant.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, create=True),
            mock.patch.object(vigilant.subprocess, "DETACHED_PROCESS", 0x008, create=True),
            mock.patch.object(vigilant.subprocess, "Popen", return_value=fake_proc) as popen_mock,
            mock.patch.object(vigilant, "save_pid") as save_pid_mock,
        ):
            pid = vigilant.start_web(background=True)

        self.assertEqual(pid, 3210)
        save_pid_mock.assert_called_once_with("web", 3210)
        kwargs = popen_mock.call_args.kwargs
        self.assertIn("creationflags", kwargs)
        self.assertEqual(kwargs["stdout"], vigilant.subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], vigilant.subprocess.DEVNULL)

    def test_start_web_background_macos_uses_new_session(self) -> None:
        import vigilant

        fake_proc = types.SimpleNamespace(pid=6543)
        with (
            mock.patch.object(vigilant, "get_python", return_value="python"),
            mock.patch.object(vigilant.sys, "platform", "darwin"),
            mock.patch.object(vigilant.subprocess, "Popen", return_value=fake_proc) as popen_mock,
            mock.patch.object(vigilant, "save_pid") as save_pid_mock,
        ):
            pid = vigilant.start_web(background=True)

        self.assertEqual(pid, 6543)
        save_pid_mock.assert_called_once_with("web", 6543)
        kwargs = popen_mock.call_args.kwargs
        self.assertTrue(kwargs.get("start_new_session"))
        self.assertEqual(kwargs["stdout"], vigilant.subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], vigilant.subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
