"""Tests for SettleTable quiescent backup, verified restore, and failure-injection defense."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from settletable import authority as auth
from tools.backup_restore import (
    compute_sha256,
    perform_quiescent_backup,
    perform_verified_restore,
)


class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.patcher_url = patch('tools.backup_restore.urllib.request.urlopen', side_effect=urllib.error.URLError('connection refused'))
        self.patcher_url.start()
        self.patcher_docker = patch('tools.backup_restore.shutil.which', return_value=None)
        self.patcher_docker.start()

        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=scratch)
        self.base = Path(self.temp_dir.name)
        self.src_db = self.base / 'live.sqlite'
        self.src_photos = self.base / 'live_photos'
        self.src_photos.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.base / 'backups'
        self.restore_db = self.base / 'restored.sqlite'
        self.restore_photos = self.base / 'restored_photos'

        self.authority = auth.Authority(self.src_db, storage_dir=self.src_photos)
        boot = self.authority.bootstrap('meal-backup-test', (
            auth.Participant('O', 'Organizer', True),
            auth.Participant('D', 'Diner', False),
        ))
        self.org_cred = boot.sessions[0].credential

        # Store a receipt photo
        img_bytes = b'\xff\xd8\xff\xe0' + b'fake_jpeg_content_for_testing' * 32
        self.photo_meta = self.authority.store_receipt_photo(
            self.org_cred, 'meal-backup-test', img_bytes, 'image/jpeg', 800, 600
        )

    def tearDown(self):
        self.patcher_docker.stop()
        self.patcher_url.stop()
        self.authority.close()
        self.temp_dir.cleanup()

    def test_quiescent_backup_and_verified_restore_roundtrip(self):
        # 1. Perform quiescent backup
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        self.assertTrue(manifest_path.exists())

        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '1.1')
        self.assertEqual(manifest['type'], 'settletable-quiescent-backup')
        self.assertEqual(manifest['photo_count'], 1)
        self.assertIn(self.photo_meta['filename'], manifest['photos'])

        # 2. Restore to new destination
        res = perform_verified_restore(manifest_path, self.restore_db, self.restore_photos, confirm_stopped=True)
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['restored_photos_count'], 1)

        # 3. Verify restored data via Authority
        restored_auth = auth.Authority(self.restore_db, storage_dir=self.restore_photos)
        try:
            snap = restored_auth.snapshot(self.org_cred, 'meal-backup-test')
            self.assertTrue(snap.has_receipt_photo)
            self.assertEqual(snap.receipt_photo['filename'], self.photo_meta['filename'])
            self.assertEqual(snap.receipt_photo['byte_size'], self.photo_meta['byte_size'])

            # Verify get_receipt_photo reads from disk and verifies sha256
            photo_bytes, photo_meta = restored_auth.get_receipt_photo(self.org_cred, 'meal-backup-test')
            self.assertEqual(photo_meta['sha256'], self.photo_meta['sha256'])
            self.assertEqual(hashlib.sha256(photo_bytes).hexdigest(), self.photo_meta['sha256'])

            # Verify photo file on disk
            restored_photo_file = self.restore_photos / self.photo_meta['filename']
            self.assertTrue(restored_photo_file.exists())
            self.assertEqual(compute_sha256(restored_photo_file), self.photo_meta['sha256'])
        finally:
            restored_auth.close()

    def test_restore_rejects_corrupted_backup_database(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        backup_db = manifest_path.parent / manifest['database']['filename']

        # Tamper with backup database bytes
        data = bytearray(backup_db.read_bytes())
        data[42] = (data[42] + 1) % 256
        backup_db.write_bytes(bytes(data))

        with self.assertRaises(ValueError) as ctx:
            perform_verified_restore(manifest_path, self.restore_db, self.restore_photos, confirm_stopped=True)
        self.assertIn('checksum mismatch', str(ctx.exception).lower())

    def test_restore_rejects_corrupted_photo_asset(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        photo_file = manifest_path.parent / manifest['receipt_photos_dir'] / self.photo_meta['filename']

        # Tamper with photo file
        photo_file.write_bytes(b'corrupted_tampered_bytes')

        with self.assertRaises(ValueError) as ctx:
            perform_verified_restore(manifest_path, self.restore_db, self.restore_photos, confirm_stopped=True)
        self.assertIn('checksum mismatch', str(ctx.exception).lower())

    def test_backup_fails_if_referenced_photo_is_missing_on_disk(self):
        # Delete photo from disk while DB still references it
        photo_path = self.src_photos / self.photo_meta['filename']
        photo_path.unlink()

        with self.assertRaises(FileNotFoundError) as ctx:
            perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        self.assertIn('missing from disk', str(ctx.exception).lower())

    def test_restore_requires_confirm_stopped(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        with self.assertRaises(RuntimeError) as ctx:
            perform_verified_restore(manifest_path, self.restore_db, self.restore_photos, confirm_stopped=False)
        self.assertIn('must be stopped', str(ctx.exception).lower())
        self.assertIn('--confirm-stopped', str(ctx.exception))

    def test_restore_detects_active_healthz_endpoint(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        from unittest.mock import MagicMock, patch
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        with patch('tools.backup_restore.urllib.request.urlopen', return_value=mock_resp):
            with self.assertRaises(RuntimeError) as ctx:
                perform_verified_restore(
                    manifest_path, self.restore_db, self.restore_photos,
                    confirm_stopped=True, check_url='http://127.0.0.1:8000/healthz',
                )
            self.assertIn('active application detected', str(ctx.exception).lower())

    def test_restore_rejects_active_locked_destination_database(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)

        # Create destination DB and hold a write lock (simulating running SettleTable process)
        self.restore_db.parent.mkdir(parents=True, exist_ok=True)
        active_conn = sqlite3.connect(self.restore_db)
        active_conn.execute("PRAGMA journal_mode=WAL;")
        active_conn.execute("CREATE TABLE dummy (id INTEGER);")
        active_conn.execute("BEGIN IMMEDIATE;")

        try:
            with self.assertRaises(RuntimeError) as ctx:
                perform_verified_restore(manifest_path, self.restore_db, self.restore_photos, confirm_stopped=True)
            self.assertIn('locked by a running process', str(ctx.exception).lower())
        finally:
            active_conn.execute("ROLLBACK;")
            active_conn.close()

    def test_restore_prunes_orphaned_destination_photos(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        # Create destination with an extra old photo not in backup
        self.restore_photos.mkdir(parents=True, exist_ok=True)
        orphaned = self.restore_photos / 'orphaned_extra.jpg'
        orphaned.write_bytes(b'old_orphaned_data')

        res = perform_verified_restore(manifest_path, self.restore_db, self.restore_photos, confirm_stopped=True)
        self.assertEqual(res['status'], 'ok')
        self.assertFalse((self.restore_photos / 'orphaned_extra.jpg').exists())
        self.assertTrue((self.restore_photos / self.photo_meta['filename']).exists())
        self.assertEqual(res['restored_photos_count'], 1)
        # Check previous dataset archive retained the orphaned file
        self.assertIsNotNone(res['previous_dataset_archive'])
        archive_path = Path(res['previous_dataset_archive'])
        self.assertTrue((archive_path / self.restore_photos.name / 'orphaned_extra.jpg').exists())

    def test_staged_restore_failure_injection_rolls_back_destination(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        # Establish existing destination state
        self.restore_db.parent.mkdir(parents=True, exist_ok=True)
        self.restore_db.write_text('existing_pre_restore_db')
        self.restore_photos.mkdir(parents=True, exist_ok=True)
        pre_photo = self.restore_photos / 'pre_existing.jpg'
        pre_photo.write_bytes(b'existing_pre_restore_photo')

        from unittest.mock import patch
        from tools import backup_restore
        real_compute_sha = backup_restore.compute_sha256

        def faulty_sha(path):
            p = Path(path).resolve()
            if p == self.restore_db.resolve():
                raise RuntimeError("Simulated post-cutover corruption")
            return real_compute_sha(path)

        with patch('tools.backup_restore.compute_sha256', side_effect=faulty_sha):
            with self.assertRaises(RuntimeError) as ctx:
                perform_verified_restore(
                    manifest_path, self.restore_db, self.restore_photos,
                    confirm_stopped=True, check_docker=False
                )
            self.assertIn('destination rolled back to previous dataset', str(ctx.exception).lower())

        # Verify destination was restored to previous state
        self.assertTrue(self.restore_db.exists())
        self.assertEqual(self.restore_db.read_text(), 'existing_pre_restore_db')
        self.assertTrue(pre_photo.exists())
        self.assertEqual(pre_photo.read_bytes(), b'existing_pre_restore_photo')

    def test_restore_rejects_extraneous_unmanifested_photos_in_backup(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        photo_dir = manifest_path.parent / manifest['receipt_photos_dir']
        extra_file = photo_dir / 'untracked_rogue.jpg'
        extra_file.write_bytes(b'rogue')
        try:
            with self.assertRaises(ValueError) as ctx:
                perform_verified_restore(manifest_path, self.restore_db, self.restore_photos, confirm_stopped=True)
            self.assertIn('extraneous receipt photo', str(ctx.exception).lower())
        finally:
            if extra_file.exists():
                extra_file.unlink()

    def test_restore_cleans_stale_wal_and_shm(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        self.restore_db.parent.mkdir(parents=True, exist_ok=True)
        wal_file = self.restore_db.with_suffix('.sqlite-wal')
        shm_file = self.restore_db.with_suffix('.sqlite-shm')
        wal_file.write_bytes(b'stale_wal_bytes')
        shm_file.write_bytes(b'stale_shm_bytes')

        res = perform_verified_restore(manifest_path, self.restore_db, self.restore_photos, confirm_stopped=True)
        self.assertEqual(res['status'], 'ok')
        self.assertFalse(wal_file.exists())
        self.assertFalse(shm_file.exists())

    def test_backup_restore_cli_flag_compatibility_and_directory_manifest(self):
        import subprocess, sys
        # 1. Test backup CLI with canonical flags and aliases
        cmd_backup = [
            sys.executable, "tools/backup_restore.py", "backup",
            "--db", str(self.src_db),
            "--storage-dir", str(self.src_photos),
            "--backup-dir", str(self.backup_dir),
        ]
        res = subprocess.run(cmd_backup, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Backup failed: {res.stderr}")
        self.assertIn("Backup completed successfully", res.stdout)

        # 2. Test restore CLI passing directory to --manifest and using --dest-storage-dir
        cmd_restore = [
            sys.executable, "tools/backup_restore.py", "restore",
            "--manifest", str(self.backup_dir),
            "--dest-db", str(self.restore_db),
            "--dest-storage-dir", str(self.restore_photos),
            "--confirm-stopped",
            "--skip-health-check",
            "--skip-docker-check",
        ]
        res_restore = subprocess.run(cmd_restore, capture_output=True, text=True)
        self.assertEqual(res_restore.returncode, 0, f"Restore failed: {res_restore.stderr}")
        self.assertIn("Restoration completed successfully", res_restore.stdout)

        # Verify restored DB integrity
        conn = sqlite3.connect(self.restore_db)
        integrity = conn.execute("PRAGMA integrity_check;").fetchone()
        conn.close()
        self.assertEqual(integrity[0], "ok")

    def test_quiescent_backup_with_offsite_copy_and_verification(self):
        offsite_dir = self.base / 'offsite_backups'
        manifest_path = perform_quiescent_backup(
            self.src_db, self.src_photos, self.backup_dir, offsite_dir=offsite_dir
        )
        self.assertTrue(manifest_path.exists())

        # Verify offsite files exist and match
        offsite_manifest = offsite_dir / manifest_path.name
        self.assertTrue(offsite_manifest.exists())
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        offsite_db = offsite_dir / manifest['database']['filename']
        self.assertTrue(offsite_db.exists())
        self.assertEqual(compute_sha256(offsite_db), manifest['database']['sha256'])

        photo_fn = self.photo_meta['filename']
        offsite_photo = offsite_dir / manifest['receipt_photos_dir'] / photo_fn
        self.assertTrue(offsite_photo.exists())
        self.assertEqual(compute_sha256(offsite_photo), manifest['photos'][photo_fn]['sha256'])

        # Verify disaster restore directly from the offsite copy
        offsite_restore_db = self.base / 'offsite_restored.sqlite'
        offsite_restore_photos = self.base / 'offsite_restored_photos'
        res = perform_verified_restore(
            offsite_manifest, offsite_restore_db, offsite_restore_photos, confirm_stopped=True
        )
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['restored_photos_count'], 1)

    def test_backup_cli_with_offsite_dir_flag(self):
        import subprocess, sys
        offsite_dir = self.base / 'cli_offsite_backups'
        cmd_backup = [
            sys.executable, "tools/backup_restore.py", "backup",
            "--db", str(self.src_db),
            "--photos", str(self.src_photos),
            "--out-dir", str(self.backup_dir),
            "--copy-to", str(offsite_dir),
        ]
        res = subprocess.run(cmd_backup, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Backup with offsite copy failed: {res.stderr}")
        self.assertIn("Offsite Copy:", res.stdout)
        self.assertIn("Verified", res.stdout)
        self.assertTrue(any(offsite_dir.glob("manifest_*.json")))


if __name__ == '__main__':
    unittest.main()
