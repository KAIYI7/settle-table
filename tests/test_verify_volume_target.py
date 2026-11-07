"""Tests for verify_volume_target pre-flight tool."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.verify_volume_target import (
    get_env_volume,
    validate_configuration,
    validate_marker_integrity,
    validate_storage_permissions,
)


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

    def test_validate_configuration_mode_real_fail_closed(self):
        # Must accept settletable_data
        validate_configuration("settletable_data", "settletable_data", "real")

        # Must reject custom volume
        with self.assertRaises(ValueError) as ctx:
            validate_configuration("custom_volume", "custom_volume", "real")
        self.assertIn("mode 'real' strictly requires volume 'settletable_data'", str(ctx.exception))

        # Must reject settletable_synthetic_data
        with self.assertRaises(ValueError) as ctx:
            validate_configuration("settletable_synthetic_data", "settletable_synthetic_data", "real")
        self.assertIn("mode 'real' strictly requires volume 'settletable_data'", str(ctx.exception))

    def test_validate_configuration_mode_synthetic_fail_closed(self):
        # Must accept settletable_synthetic_data
        validate_configuration("settletable_synthetic_data", "settletable_synthetic_data", "synthetic")

        # Must reject custom volume
        with self.assertRaises(ValueError) as ctx:
            validate_configuration("custom_volume", "custom_volume", "synthetic")
        self.assertIn("mode 'synthetic' strictly requires volume 'settletable_synthetic_data'", str(ctx.exception))

        # Must reject settletable_data
        with self.assertRaises(ValueError) as ctx:
            validate_configuration("settletable_data", "settletable_data", "synthetic")
        self.assertIn("mode 'synthetic' strictly requires volume 'settletable_synthetic_data'", str(ctx.exception))

    def test_validate_configuration_mode_auto_fail_closed(self):
        # Must accept standard volumes
        validate_configuration("settletable_data", "settletable_data", "auto")
        validate_configuration("settletable_synthetic_data", "settletable_synthetic_data", "auto")

        # Must reject custom volume in auto mode
        with self.assertRaises(ValueError) as ctx:
            validate_configuration("custom_volume", "custom_volume", "auto")
        self.assertIn("Unexpected volume 'custom_volume'", str(ctx.exception))

    def test_validate_configuration_detects_conflict_between_env_and_compose(self):
        with self.assertRaises(ValueError) as ctx:
            validate_configuration("settletable_synthetic_data", "settletable_data", "auto")
        self.assertIn("Configuration conflict", str(ctx.exception))

    def test_validate_storage_permissions_enforces_non_root_and_writability(self):
        valid_info = {
            "uid": 10001,
            "gid": 10001,
            "stat_uid": 10001,
            "stat_gid": 10001,
            "data_writable": True,
            "photos_writable": True,
        }
        validate_storage_permissions(valid_info)

        # Container user mismatch
        with self.assertRaises(PermissionError) as ctx:
            validate_storage_permissions({**valid_info, "uid": 0})
        self.assertIn("Container user mismatch", str(ctx.exception))

        # Storage directory ownership mismatch
        with self.assertRaises(PermissionError) as ctx:
            validate_storage_permissions({**valid_info, "stat_uid": 0})
        self.assertIn("Storage directory ownership mismatch", str(ctx.exception))

        # Root data directory unwritable
        with self.assertRaises(PermissionError) as ctx:
            validate_storage_permissions({**valid_info, "data_writable": False})
        self.assertIn("not writable", str(ctx.exception))

        # Photos directory unwritable
        with self.assertRaises(PermissionError) as ctx:
            validate_storage_permissions({**valid_info, "photos_writable": False})
        self.assertIn("photos directory", str(ctx.exception))

    def test_validate_marker_integrity_enforces_fail_closed(self):
        # Clean matching marker passes
        validate_marker_integrity("settletable_data", {
            "marker": {"volume_name": "settletable_data", "initialized_at": "2026-11-08"},
            "db_exists": True,
        })

        # Fresh volume without marker or db passes
        validate_marker_integrity("settletable_data", {
            "marker": None,
            "db_exists": False,
        })

        # Marker mismatch raises
        with self.assertRaises(RuntimeError) as ctx:
            validate_marker_integrity("settletable_data", {
                "marker": {"volume_name": "settletable_synthetic_data"},
                "db_exists": True,
            })
        self.assertIn("Volume marker mismatch", str(ctx.exception))

        # Corrupt marker error raises
        with self.assertRaises(RuntimeError) as ctx:
            validate_marker_integrity("settletable_data", {
                "marker": {"error": "JSONDecodeError"},
                "db_exists": True,
            })
        self.assertIn("Corrupt or unreadable volume marker", str(ctx.exception))

        # Missing volume_name key raises
        with self.assertRaises(RuntimeError) as ctx:
            validate_marker_integrity("settletable_data", {
                "marker": {"other": 123},
                "db_exists": True,
            })
        self.assertIn("missing 'volume_name'", str(ctx.exception))

        # Unmarked existing database raises
        with self.assertRaises(RuntimeError) as ctx:
            validate_marker_integrity("settletable_data", {
                "marker": None,
                "db_exists": True,
            })
        self.assertIn("Unmarked existing database detected", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
