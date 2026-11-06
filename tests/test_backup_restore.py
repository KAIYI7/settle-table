"""Tests for SettleTable quiescent backup, verified restore, and failure-injection defense."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from settletable import authority as auth
from tools.backup_restore import (
    compute_sha256,
    perform_quiescent_backup,
    perform_verified_restore,
)


class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
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
        res = perform_verified_restore(manifest_path, self.restore_db, self.restore_photos)
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
            perform_verified_restore(manifest_path, self.restore_db, self.restore_photos)
        self.assertIn('checksum mismatch', str(ctx.exception).lower())

    def test_restore_rejects_corrupted_photo_asset(self):
        manifest_path = perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        photo_file = manifest_path.parent / manifest['receipt_photos_dir'] / self.photo_meta['filename']

        # Tamper with photo file
        photo_file.write_bytes(b'corrupted_tampered_bytes')

        with self.assertRaises(ValueError) as ctx:
            perform_verified_restore(manifest_path, self.restore_db, self.restore_photos)
        self.assertIn('checksum mismatch', str(ctx.exception).lower())

    def test_backup_fails_if_referenced_photo_is_missing_on_disk(self):
        # Delete photo from disk while DB still references it
        photo_path = self.src_photos / self.photo_meta['filename']
        photo_path.unlink()

        with self.assertRaises(FileNotFoundError) as ctx:
            perform_quiescent_backup(self.src_db, self.src_photos, self.backup_dir)
        self.assertIn('missing from disk', str(ctx.exception).lower())

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
                perform_verified_restore(manifest_path, self.restore_db, self.restore_photos)
            self.assertIn('locked by a running process', str(ctx.exception).lower())
        finally:
            active_conn.execute("ROLLBACK;")
            active_conn.close()


if __name__ == '__main__':
    unittest.main()
