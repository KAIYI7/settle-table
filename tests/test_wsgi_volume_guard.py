"""Tests for SettleTable WSGI volume identity marker and cross-volume protection."""
import json
from pathlib import Path
import tempfile
import unittest

from settletable.wsgi import check_volume_identity


class WsgiVolumeGuardTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=scratch)
        self.base = Path(self.temp_dir.name)
        self.data_dir = self.base / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "settletable.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_volume_identity_initializes_marker_when_missing(self):
        marker_file = self.data_dir / ".volume_identity"
        self.assertFalse(marker_file.exists())

        check_volume_identity(self.db_path, "settletable_data")
        self.assertTrue(marker_file.exists())

        data = json.loads(marker_file.read_text(encoding="utf-8"))
        self.assertEqual(data["volume_name"], "settletable_data")
        self.assertIn("initialized_at", data)

    def test_volume_identity_accepts_matching_marker(self):
        marker_file = self.data_dir / ".volume_identity"
        marker_file.write_text(json.dumps({"volume_name": "settletable_data"}), encoding="utf-8")

        # Must not raise
        check_volume_identity(self.db_path, "settletable_data")

    def test_volume_identity_raises_on_mismatch(self):
        marker_file = self.data_dir / ".volume_identity"
        marker_file.write_text(json.dumps({"volume_name": "settletable_synthetic_data"}), encoding="utf-8")

        with self.assertRaises(RuntimeError) as ctx:
            check_volume_identity(self.db_path, "settletable_data")

        err = str(ctx.exception)
        self.assertIn("Volume identity mismatch", err)
        self.assertIn("settletable_data", err)
        self.assertIn("settletable_synthetic_data", err)

    def test_volume_identity_noop_when_env_unset(self):
        marker_file = self.data_dir / ".volume_identity"
        check_volume_identity(self.db_path, None)
        self.assertFalse(marker_file.exists())

        check_volume_identity(self.db_path, "")
        self.assertFalse(marker_file.exists())

    def test_create_app_enforces_volume_identity_from_environment(self):
        import os
        from unittest.mock import patch
        from settletable.wsgi import create_app

        marker_file = self.data_dir / ".volume_identity"
        marker_file.write_text(json.dumps({"volume_name": "settletable_synthetic_data"}), encoding="utf-8")

        with patch.dict(os.environ, {
            "SETTLETABLE_DB_PATH": str(self.db_path),
            "SETTLETABLE_DATA_VOLUME": "settletable_data",
        }):
            with self.assertRaises(RuntimeError) as ctx:
                create_app()
            self.assertIn("Volume identity mismatch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
