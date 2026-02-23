from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.config import AppConfig, save_config


class ConfigPersistenceTests(unittest.TestCase):
    def test_save_config_removes_stale_env_file_when_no_env_overrides_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_root = Path(tmpdir)
            with patch("utils.config.config_dir", return_value=cfg_root):
                disabled = AppConfig(enable_ai_suggestions=False)
                save_config(disabled)
                dot_env = cfg_root / ".env"
                self.assertTrue(dot_env.exists())
                self.assertIn("ENABLE_AI_SUGGESTIONS=false", dot_env.read_text(encoding="utf-8"))

                enabled = AppConfig(enable_ai_suggestions=True)
                save_config(enabled)
                self.assertFalse(dot_env.exists())

    def test_save_config_persists_duckduckgo_disable_and_low_bandwidth_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_root = Path(tmpdir)
            with patch("utils.config.config_dir", return_value=cfg_root):
                cfg = AppConfig(enable_duckduckgo_search=False, low_bandwidth_mode=True)
                save_config(cfg)
                dot_env = cfg_root / ".env"
                self.assertTrue(dot_env.exists())
                env_text = dot_env.read_text(encoding="utf-8")
                self.assertIn("ENABLE_DUCKDUCKGO_SEARCH=false", env_text)
                self.assertIn("LOW_BANDWIDTH_MODE=true", env_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
