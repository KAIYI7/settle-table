"""Tests for verify_volume_target pre-flight tool."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.verify_volume_target import get_env_volume


class VerifyVolumeTargetTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=scratch)
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_env_volume_parses_cleanly(self):
        env_file = self.base / ".env"
        env_file.write_text(
            "# Comment\nSETTLETABLE_DATA_VOLUME=settletable_synthetic_data\nOTHER=1\n",
            encoding="utf-8",
        )
        self.assertEqual(get_env_volume(env_file), "settletable_synthetic_data")

    def test_get_env_volume_returns_none_if_missing(self):
        env_file = self.base / ".env_missing"
        self.assertIsNone(get_env_volume(env_file))

        env_file_empty = self.base / ".env_empty"
        env_file_empty.write_text("OTHER=1\n", encoding="utf-8")
        self.assertIsNone(get_env_volume(env_file_empty))


if __name__ == "__main__":
    unittest.main()
