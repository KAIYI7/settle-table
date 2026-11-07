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

    def test_volume_identity_raises_on_unmarked_existing_database(self):
        self.db_path.write_text("existing_db_bytes", encoding="utf-8")
        marker_file = self.data_dir / ".volume_identity"
        self.assertFalse(marker_file.exists())

        with self.assertRaises(RuntimeError) as ctx:
            check_volume_identity(self.db_path, "settletable_data")
        self.assertIn("Unmarked existing dataset detected", str(ctx.exception))

    def test_volume_identity_raises_on_unmarked_existing_photos(self):
        photos_dir = self.data_dir / "receipt_photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        (photos_dir / "existing_photo.jpg").write_bytes(b"photo_bytes")
        marker_file = self.data_dir / ".volume_identity"
        self.assertFalse(marker_file.exists())

        with self.assertRaises(RuntimeError) as ctx:
            check_volume_identity(self.db_path, "settletable_data")
        self.assertIn("Unmarked existing dataset detected", str(ctx.exception))

    def test_volume_identity_raises_on_malformed_json_marker(self):
        marker_file = self.data_dir / ".volume_identity"
        marker_file.write_text("{malformed_json_invalid", encoding="utf-8")

        with self.assertRaises(RuntimeError) as ctx:
            check_volume_identity(self.db_path, "settletable_data")
        self.assertIn("malformed JSON", str(ctx.exception))

    def test_volume_identity_raises_on_unreadable_marker(self):
        from unittest.mock import patch
        marker_file = self.data_dir / ".volume_identity"
        marker_file.write_text(json.dumps({"volume_name": "settletable_data"}), encoding="utf-8")

        with patch.object(Path, "read_text", side_effect=PermissionError("Permission denied")):
            with self.assertRaises(RuntimeError) as ctx:
                check_volume_identity(self.db_path, "settletable_data")
            self.assertIn("unreadable", str(ctx.exception))

    def test_volume_identity_raises_on_missing_volume_name_key(self):
        marker_file = self.data_dir / ".volume_identity"
        marker_file.write_text(json.dumps({"other_key": 123}), encoding="utf-8")

        with self.assertRaises(RuntimeError) as ctx:
            check_volume_identity(self.db_path, "settletable_data")
        self.assertIn("missing 'volume_name'", str(ctx.exception))

    def test_volume_identity_raises_on_unwritable_fresh_volume(self):
        from unittest.mock import patch
        marker_file = self.data_dir / ".volume_identity"
        self.assertFalse(marker_file.exists())

        with patch.object(Path, "write_text", side_effect=PermissionError("Read-only volume")):
            with self.assertRaises(RuntimeError) as ctx:
                check_volume_identity(self.db_path, "settletable_data")
            self.assertIn("Failed to initialize volume identity marker", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
