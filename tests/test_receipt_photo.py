"""Tests for SettleTable Receipt Photo Retention and Notion Export."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from settletable.authority import (
    Authority,
    AuthorityError,
    Participant,
    Receipt,
    ReceiptItem,
    ReplaceReceipt,
    ReviewReceipt,
    SetOwnQuantity,
    Finalize,
)
from settletable.notion.client import MockNotionClient, encode_multipart_file
from settletable.notion.exporter import count_notion_blocks, export_finalized_meal, format_compact_meal_blocks
from settletable.notion.models import NotionExportConfig
from settletable.ocr.engine import MAX_IMAGE_BYTES
from settletable.transport import SettleTableApp


def make_minimal_png(width: int = 10, height: int = 10) -> bytes:
    """Generate a minimal valid 10x10 PNG image byte string."""
    import struct
    import zlib
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff)
    ihdr = struct.pack('>I', len(ihdr_data)) + b'IHDR' + ihdr_data + ihdr_crc

    raw_scanlines = b''.join(b'\x00' + (b'\xff\x00\x00' * width) for _ in range(height))
    compressed = zlib.compress(raw_scanlines)
    idat_crc = struct.pack('>I', zlib.crc32(b'IDAT' + compressed) & 0xffffffff)
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + idat_crc

    iend_crc = struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
    iend = struct.pack('>I', 0) + b'IEND' + iend_crc

    return sig + ihdr + idat + iend


class TestReceiptPhotoAuthority(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'settletable.sqlite'
        self.storage_dir = Path(self.temp_dir.name) / 'receipt_photos'
        self.authority = Authority(str(self.db_path), storage_dir=self.storage_dir)

        # Bootstrap meal with organizer Alice and diner Bob
        self.meal_id = 'test-meal-photo-01'
        res = self.authority.bootstrap(self.meal_id, (
            Participant('O', 'Alice', True),
            Participant('D1', 'Bob', False),
        ))
        self.org_cred = res.sessions[0].credential
        self.org_id = 'O'

        # Add Bob
        inv = self.authority.issue_invitation(self.org_cred, self.meal_id, 'D1')
        redeem = self.authority.redeem_invitation(inv.token, self.meal_id)
        self.diner_cred = redeem.credential
        self.diner_id = 'D1'

        self.png_bytes = make_minimal_png(100, 100)

    def tearDown(self):
        self.authority.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_store_receipt_photo_success(self):
        meta = self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        self.assertEqual(meta['meal_id'], self.meal_id)
        self.assertEqual(meta['content_type'], 'image/png')
        self.assertEqual(meta['byte_size'], len(self.png_bytes))
        self.assertEqual(meta['sha256'], hashlib.sha256(self.png_bytes).hexdigest())

        # Verify file exists on disk
        file_path = self.storage_dir / meta['filename']
        self.assertTrue(file_path.is_file())
        self.assertEqual(file_path.read_bytes(), self.png_bytes)

    def test_get_receipt_photo_organizer_access(self):
        meta = self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        data, read_meta = self.authority.get_receipt_photo(self.org_cred, self.meal_id)
        self.assertEqual(data, self.png_bytes)
        self.assertEqual(read_meta['filename'], meta['filename'])

    def test_get_receipt_photo_diner_forbidden(self):
        self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        with self.assertRaises(AuthorityError) as ctx:
            self.authority.get_receipt_photo(self.diner_cred, self.meal_id)
        self.assertEqual(ctx.exception.code, 'forbidden')

    def test_get_receipt_photo_corrupted_hash(self):
        meta = self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        file_path = self.storage_dir / meta['filename']
        # Corrupt one byte in the file without changing length
        corrupted_bytes = bytearray(self.png_bytes)
        corrupted_bytes[-1] ^= 0xFF
        file_path.write_bytes(bytes(corrupted_bytes))

        with self.assertRaises(AuthorityError) as ctx:
            self.authority.get_receipt_photo(self.org_cred, self.meal_id)
        self.assertEqual(ctx.exception.code, 'photo_corrupted')

    def test_get_receipt_photo_truncated_size(self):
        meta = self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        file_path = self.storage_dir / meta['filename']
        # Truncate file
        file_path.write_bytes(self.png_bytes[:10])

        with self.assertRaises(AuthorityError) as ctx:
            self.authority.get_receipt_photo(self.org_cred, self.meal_id)
        self.assertEqual(ctx.exception.code, 'photo_corrupted')

    def test_snapshot_disk_missing_file_recovery(self):
        meta = self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        # Snapshot reports photo present
        snap = self.authority.snapshot(self.org_cred, self.meal_id)
        self.assertTrue(snap.has_receipt_photo)
        self.assertIsNotNone(snap.receipt_photo)

        # Physically delete the file from disk (simulate disk crash/unmounted volume)
        file_path = self.storage_dir / meta['filename']
        file_path.unlink()

        # Snapshot safely recovers: reports photo not present, preventing broken UI links
        recovered_snap = self.authority.snapshot(self.org_cred, self.meal_id)
        self.assertFalse(recovered_snap.has_receipt_photo)
        self.assertIsNone(recovered_snap.receipt_photo)

    def test_store_receipt_photo_diner_forbidden(self):
        with self.assertRaises(AuthorityError) as ctx:
            self.authority.store_receipt_photo(
                self.diner_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
            )
        self.assertEqual(ctx.exception.code, 'forbidden')

    def test_atomic_replacement_unlinks_old_photo(self):
        meta1 = self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        old_file = self.storage_dir / meta1['filename']
        self.assertTrue(old_file.exists())

        png2 = make_minimal_png(120, 120)
        meta2 = self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, png2, 'image/png', 120, 120
        )
        new_file = self.storage_dir / meta2['filename']
        self.assertTrue(new_file.exists())
        self.assertFalse(old_file.exists())  # Old file was cleanly removed

    def test_delete_receipt_photo_success(self):
        meta = self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        file_path = self.storage_dir / meta['filename']
        self.assertTrue(file_path.exists())

        self.authority.delete_receipt_photo(self.org_cred, self.meal_id)
        self.assertFalse(file_path.exists())

        with self.assertRaises(AuthorityError) as ctx:
            self.authority.get_receipt_photo(self.org_cred, self.meal_id)
        self.assertEqual(ctx.exception.code, 'photo_not_found')

    def test_snapshot_metadata_without_embedded_bytes(self):
        # Before photo attached
        snap1 = self.authority.snapshot(self.org_cred, self.meal_id)
        self.assertFalse(snap1.has_receipt_photo)
        self.assertIsNone(snap1.receipt_photo)

        # After photo attached
        self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
        )
        snap2 = self.authority.snapshot(self.org_cred, self.meal_id)
        self.assertTrue(snap2.has_receipt_photo)
        self.assertIsNotNone(snap2.receipt_photo)
        self.assertEqual(snap2.receipt_photo['content_type'], 'image/png')
        self.assertEqual(snap2.receipt_photo['width'], 100)
        self.assertNotIn('data', snap2.receipt_photo)
        self.assertNotIn('bytes', snap2.receipt_photo)

    def test_finalized_meal_immutability(self):
        rcpt = Receipt(
            items=(ReceiptItem("item-1", "Roti Canai", 1, 300),),
            subtotal_sen=300,
            total_sen=300,
        )
        snap0 = self.authority.snapshot(self.org_cred, self.meal_id)
        self.authority.apply(self.org_cred, self.meal_id, ReplaceReceipt("c1", snap0.revision, snap0.financial_revision, rcpt))
        snap1 = self.authority.snapshot(self.org_cred, self.meal_id)
        self.authority.apply(self.org_cred, self.meal_id, ReviewReceipt("c2", snap1.revision, snap1.financial_revision, snap1.receipt_digest))
        snap2 = self.authority.snapshot(self.org_cred, self.meal_id)
        self.authority.apply(self.org_cred, self.meal_id, SetOwnQuantity("c3", "item-1", 1, snap2.items[0].item_revision, snap2.financial_revision))
        snap3 = self.authority.snapshot(self.org_cred, self.meal_id)
        self.authority.apply(self.org_cred, self.meal_id, Finalize("c4", snap3.revision, snap3.financial_revision))

        # Storing or replacing photo on finalized meal must be rejected with 'finalized'
        with self.assertRaises(AuthorityError) as ctx:
            self.authority.store_receipt_photo(
                self.org_cred, self.meal_id, self.png_bytes, 'image/png', 100, 100
            )
        self.assertEqual(ctx.exception.code, 'finalized')

        # Deleting photo on finalized meal must also be rejected
        with self.assertRaises(AuthorityError) as ctx:
            self.authority.delete_receipt_photo(self.org_cred, self.meal_id)
        self.assertEqual(ctx.exception.code, 'finalized')


class TestReceiptPhotoTransport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'settletable.sqlite'
        self.storage_dir = Path(self.temp_dir.name) / 'receipt_photos'
        self.mock_notion_client = MockNotionClient()
        self.app = SettleTableApp(str(self.db_path), storage_dir=self.storage_dir, notion_client=self.mock_notion_client, allow_sync_export=True)

        # Setup meal
        auth = self.app.get_authority()
        self.meal_id = 'transport-photo-meal-01'
        boot = auth.bootstrap(self.meal_id, (
            Participant('O', 'Alice', True),
            Participant('D1', 'Bob', False),
        ))
        self.org_cred = boot.sessions[0].credential
        self.org_id = 'O'

        # Diner
        inv = auth.issue_invitation(self.org_cred, self.meal_id, 'D1')
        redeem = auth.redeem_invitation(inv.token, self.meal_id)
        self.diner_cred = redeem.credential

        self.png_bytes = make_minimal_png(50, 50)

    def tearDown(self):
        self.app.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _call(self, method, path, body=b'', headers=None):
        import io
        hdrs = {
            'HTTP_HOST': 'localhost:8000',
            'HTTP_ORIGIN': 'http://localhost:8000',
            'HTTP_X_SETTLETABLE_ACTION': '1',
        }
        if headers:
            hdrs.update(headers)
        hdrs['CONTENT_LENGTH'] = str(len(body))
        environ = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'wsgi.input': io.BytesIO(body),
            **hdrs,
        }
        status_capture = []
        headers_capture = []

        def start_response(status, response_headers, exc_info=None):
            status_capture.append(status)
            headers_capture.append(response_headers)

        body_bytes = b''.join(self.app(environ, start_response))
        code = int(status_capture[0].split()[0])
        return code, headers_capture[0], body_bytes

    def test_upload_and_get_receipt_photo(self):
        # 1. Upload via POST /receipt/photo
        code, hdrs, body = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo',
            body=self.png_bytes,
            headers={
                'CONTENT_TYPE': 'image/png',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )
        self.assertEqual(code, 200)
        data = json.loads(body.decode('utf-8'))
        self.assertTrue(data['ok'])
        self.assertEqual(data['photo']['byte_size'], len(self.png_bytes))

        # 2. Retrieve via GET /receipt/photo
        code_get, hdrs_get, body_get = self._call(
            'GET',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}'},
        )
        self.assertEqual(code_get, 200)
        self.assertEqual(body_get, self.png_bytes)
        hdr_dict = dict(hdrs_get)
        self.assertEqual(hdr_dict.get('Content-Type'), 'image/png')
        self.assertEqual(hdr_dict.get('X-Content-Type-Options'), 'nosniff')
        self.assertIn('no-store', hdr_dict.get('Cache-Control', ''))

    def test_diner_cannot_upload_or_download_photo(self):
        # Upload rejected
        code, _, _ = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo',
            body=self.png_bytes,
            headers={
                'CONTENT_TYPE': 'image/png',
                'HTTP_AUTHORIZATION': f'Bearer {self.diner_cred}',
            },
        )
        self.assertEqual(code, 403)

        # Upload by organizer
        self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo',
            body=self.png_bytes,
            headers={
                'CONTENT_TYPE': 'image/png',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )

        # Download by diner rejected
        code_get, _, _ = self._call(
            'GET',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.diner_cred}'},
        )
        self.assertEqual(code_get, 403)

    def test_delete_receipt_photo_requires_action_header_and_csrf(self):
        # Upload
        self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo',
            body=self.png_bytes,
            headers={
                'CONTENT_TYPE': 'image/png',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )

        # Missing action header on DELETE
        code_no_act, _, _ = self._call(
            'DELETE',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
                'HTTP_X_SETTLETABLE_ACTION': '',
            },
        )
        self.assertEqual(code_no_act, 400)

        # Origin mismatch on DELETE with cookie auth
        code_bad_origin, _, _ = self._call(
            'DELETE',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={
                'HTTP_COOKIE': f'settletable_session={self.org_cred}',
                'HTTP_ORIGIN': 'http://evil.com',
            },
        )
        self.assertEqual(code_bad_origin, 403)

        # Valid DELETE
        code_del, _, body_del = self._call(
            'DELETE',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}'},
        )
        self.assertEqual(code_del, 200)
        self.assertTrue(json.loads(body_del.decode('utf-8'))['ok'])

    def test_payload_too_large_rejected(self):
        oversized = b'A' * (MAX_IMAGE_BYTES + 1024)
        code, _, body = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo',
            body=oversized,
            headers={
                'CONTENT_TYPE': 'image/png',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )
        self.assertEqual(code, 413)

    def _setup_finalized_meal(self, upload_photo=True):
        auth = self.app.get_authority()
        rcpt = Receipt(
            items=(ReceiptItem('item-1', 'Nasi Lemak', 1, 1000),),
            subtotal_sen=1000,
            total_sen=1000,
            adjustments=(),
        )
        snap0 = auth.snapshot(self.org_cred, self.meal_id)
        auth.apply(self.org_cred, self.meal_id, ReplaceReceipt("c1", snap0.revision, snap0.financial_revision, rcpt))
        snap1 = auth.snapshot(self.org_cred, self.meal_id)
        auth.apply(self.org_cred, self.meal_id, ReviewReceipt("c2", snap1.revision, snap1.financial_revision, snap1.receipt_digest))
        snap2 = auth.snapshot(self.org_cred, self.meal_id)
        auth.apply(self.org_cred, self.meal_id, SetOwnQuantity("c3", "item-1", 1, snap2.items[0].item_revision, snap2.financial_revision))
        snap3 = auth.snapshot(self.org_cred, self.meal_id)
        return auth.apply(self.org_cred, self.meal_id, Finalize("c4", snap3.revision, snap3.financial_revision))

    def test_export_notion_fails_when_photo_requested_but_missing(self):
        # Setup finalized meal without uploading any photo
        self._setup_finalized_meal(upload_photo=False)
        payload = json.dumps({
            'token': 'secret_test_notion_token_12345',
            'parent_id': '11111111-2222-3333-4444-555555555555',
            'include_receipt_photo': True,
        }).encode('utf-8')
        code, _, body = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/export/notion?sync=1',
            body=payload,
            headers={
                'CONTENT_TYPE': 'application/json',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )
        self.assertEqual(code, 404)
        data = json.loads(body.decode('utf-8'))
        self.assertFalse(data['ok'])
        self.assertEqual(data['error'], 'photo_not_found')

        # Verify export was NOT recorded as completed in authority
        auth = self.app.get_authority()
        snap = auth.snapshot(self.org_cred, self.meal_id)
        rec = auth.get_notion_export(self.meal_id, snap.revision)
        self.assertIsNone(rec)

    def test_export_notion_fails_when_photo_corrupted(self):
        auth = self.app.get_authority()
        meta = auth.store_receipt_photo(self.org_cred, self.meal_id, self.png_bytes, 'image/png', 50, 50)
        self._setup_finalized_meal(upload_photo=False)

        # Corrupt file on disk
        target_file = self.storage_dir / meta['filename']
        target_file.write_bytes(b'CORRUPTED_BYTES_WITHOUT_VALID_HASH')

        payload = json.dumps({
            'token': 'secret_test_notion_token_12345',
            'parent_id': '11111111-2222-3333-4444-555555555555',
            'include_receipt_photo': True,
        }).encode('utf-8')
        code, _, body = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/export/notion?sync=1',
            body=payload,
            headers={
                'CONTENT_TYPE': 'application/json',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )
        self.assertEqual(code, 500)
        data = json.loads(body.decode('utf-8'))
        self.assertFalse(data['ok'])
        self.assertEqual(data['error'], 'photo_corrupted')

    def test_export_notion_upgrade_text_only_in_place(self):
        auth = self.app.get_authority()
        auth.store_receipt_photo(self.org_cred, self.meal_id, self.png_bytes, 'image/png', 50, 50)
        self._setup_finalized_meal(upload_photo=False)

        # 1. First export: text-only (include_receipt_photo=False)
        payload1 = json.dumps({
            'token': 'secret_test_notion_token_12345',
            'parent_id': '11111111-2222-3333-4444-555555555555',
            'include_receipt_photo': False,
        }).encode('utf-8')
        code1, _, body1 = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/export/notion?sync=1',
            body=payload1,
            headers={
                'CONTENT_TYPE': 'application/json',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )
        self.assertEqual(code1, 200)
        data1 = json.loads(body1.decode('utf-8'))
        self.assertTrue(data1['ok'])
        page_id = data1['export']['page_id']
        self.assertIsNotNone(page_id)

        # Check export record in DB: has photo=0
        snap = auth.snapshot(self.org_cred, self.meal_id)
        rec1 = auth.get_notion_export(self.meal_id, snap.revision)
        self.assertEqual(rec1['status'], 'completed')
        self.assertTrue(rec1['export_digest'].endswith(':photo=0'))

        # Check mock client: page has no image block
        mock_cli = self.app.get_notion_client()
        blocks1 = mock_cli.blocks[page_id]
        self.assertEqual(len([b for b in blocks1 if b.get('type') == 'image']), 0)

        # 2. Second export: organizer now requests include_receipt_photo=True
        payload2 = json.dumps({
            'token': 'secret_test_notion_token_12345',
            'parent_id': '11111111-2222-3333-4444-555555555555',
            'include_receipt_photo': True,
        }).encode('utf-8')
        code2, _, body2 = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/export/notion?sync=1',
            body=payload2,
            headers={
                'CONTENT_TYPE': 'application/json',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )
        self.assertEqual(code2, 200)
        data2 = json.loads(body2.decode('utf-8'))
        self.assertTrue(data2['ok'])
        self.assertEqual(data2['export']['page_id'], page_id, "Must upgrade existing page in-place, not create duplicate")
        self.assertEqual(data2['export']['status'], 'completed')

        # Check export record in DB: upgraded to photo=1
        rec2 = auth.get_notion_export(self.meal_id, snap.revision)
        self.assertEqual(rec2['status'], 'completed')
        self.assertTrue(rec2['export_digest'].endswith(':photo=1'))

        # Check mock client: image block was appended in-place
        blocks2 = mock_cli.blocks[page_id]
        self.assertEqual(len([b for b in blocks2 if b.get('type') == 'image']), 1)

        # 3. Third export: include_receipt_photo=True again -> idempotent no-op (already_exported)
        code3, _, body3 = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/export/notion?sync=1',
            body=payload2,
            headers={
                'CONTENT_TYPE': 'application/json',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )
        self.assertEqual(code3, 200)
        data3 = json.loads(body3.decode('utf-8'))
        self.assertTrue(data3['ok'])
        self.assertEqual(data3['export']['status'], 'already_exported')
        self.assertEqual(data3['export']['page_id'], page_id)

        # 4. Fourth export: include_receipt_photo=False -> idempotent no-op (already_exported)
        code4, _, body4 = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/export/notion?sync=1',
            body=payload1,
            headers={
                'CONTENT_TYPE': 'application/json',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            },
        )
        self.assertEqual(code4, 200)
        data4 = json.loads(body4.decode('utf-8'))
        self.assertTrue(data4['ok'])
        self.assertEqual(data4['export']['status'], 'already_exported')
        self.assertEqual(data4['export']['page_id'], page_id)


class TestNotionPhotoExport(unittest.TestCase):
    def setUp(self):
        self.png_bytes = make_minimal_png(50, 50)
        self.mock_client = MockNotionClient()
        self.meal_id = 'notion-photo-meal-01'
        self.snapshot = {
            'finalized': True,
            'revision': 5,
            'financial_revision': 3,
            'calculation_digest': 'abc12345',
            'receipt': {
                'merchant': 'Restoran Ali',
                'subtotal_sen': 1500,
                'total_sen': 1500,
                'adjustments': [],
                'items': [
                    {'id': 'item-1', 'label': 'Nasi Lemak', 'quantity': 1, 'line_sen': 1000},
                    {'id': 'item-2', 'label': 'Kopi O', 'quantity': 1, 'line_sen': 500},
                ],
            },
            'participants': [{'id': 'p1', 'name': 'Alice', 'organizer': True}],
            'calculation': {
                'consumption': [{'participant_id': 'p1', 'sen': 1500}],
            },
            'claims': [{'item_id': 'item-1', 'participant_id': 'p1', 'quantity': 1}],
        }

    def test_encode_multipart_file(self):
        body, ct = encode_multipart_file('file', 'receipt.png', 'image/png', b'TESTDATA')
        self.assertTrue(ct.startswith('multipart/form-data; boundary='))
        self.assertIn(b'Content-Disposition: form-data; name="file"; filename="receipt.png"', body)
        self.assertIn(b'Content-Type: image/png', body)
        self.assertIn(b'TESTDATA', body)

    def test_mock_client_upload_file(self):
        token = 'secret_test_notion_token_12345'
        file_id = self.mock_client.upload_file(token, 'receipt.png', 'image/png', self.png_bytes)
        self.assertTrue(file_id.startswith('33333333-'))
        self.assertEqual(self.mock_client.file_uploads[file_id]['status'], 'uploaded')
        self.assertEqual(self.mock_client.file_uploads[file_id]['_bytes'], self.png_bytes)

    def test_export_finalized_meal_with_receipt_photo(self):
        token = 'secret_test_notion_token_12345'
        parent_id = '11111111-2222-3333-4444-555555555555'
        config = NotionExportConfig(
            token=token,
            parent_id=parent_id,
            mode='compact',
            include_receipt_photo=True,
            receipt_photo_data=(self.png_bytes, 'receipt.png', 'image/png'),
        )

        res = export_finalized_meal(self.mock_client, self.meal_id, self.snapshot, config)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, 'completed')
        self.assertIsNotNone(res.page_id)

        # Verify page children blocks
        page_blocks = self.mock_client.blocks[res.page_id]
        image_blocks = [b for b in page_blocks if b.get('type') == 'image']
        self.assertEqual(len(image_blocks), 1)

        img_block = image_blocks[0]
        self.assertEqual(img_block['image']['type'], 'file_upload')
        uploaded_id = img_block['image']['file_upload']['id']
        self.assertIn(uploaded_id, self.mock_client.file_uploads)

        # Verify compact block budget <= 40 blocks
        self.assertLessEqual(count_notion_blocks(page_blocks), 40)

    def test_export_finalized_meal_default_off_omits_image(self):
        token = 'secret_test_notion_token_12345'
        parent_id = '11111111-2222-3333-4444-555555555555'
        # Default include_receipt_photo is False
        config = NotionExportConfig(
            token=token,
            parent_id=parent_id,
            mode='compact',
        )

        res = export_finalized_meal(self.mock_client, self.meal_id, self.snapshot, config)
        self.assertTrue(res.ok)
        page_blocks = self.mock_client.blocks[res.page_id]
        image_blocks = [b for b in page_blocks if b.get('type') == 'image']
        self.assertEqual(len(image_blocks), 0)

    def test_compact_budget_with_many_items_and_image(self):
        large_snap = dict(self.snapshot)
        items = [{'id': f'item-{i}', 'label': f'Dish {i}', 'quantity': 1, 'line_sen': 100} for i in range(50)]
        large_snap['receipt'] = dict(large_snap['receipt'], items=items)

        image_blk = {
            'object': 'block',
            'type': 'image',
            'image': {'type': 'file_upload', 'file_upload': {'id': 'test-upload-id'}},
        }
        blocks = format_compact_meal_blocks(self.meal_id, large_snap, image_block=image_blk)
        total_blocks = count_notion_blocks(blocks)
        self.assertLessEqual(total_blocks, 40)
        self.assertIn(image_blk, blocks)

    def test_export_finalized_meal_fails_on_missing_photo_data(self):
        token = 'secret_test_notion_token_12345'
        parent_id = '11111111-2222-3333-4444-555555555555'
        config = NotionExportConfig(
            token=token,
            parent_id=parent_id,
            mode='compact',
            include_receipt_photo=True,
            receipt_photo_data=None,  # Missing photo data
        )
        res = export_finalized_meal(self.mock_client, self.meal_id, self.snapshot, config)
        self.assertFalse(res.ok)
        self.assertEqual(res.status, 'failed')
        self.assertEqual(res.error, 'missing_receipt_photo_data')
        self.assertEqual(len(self.mock_client.pages), 0)

    def test_export_upgrade_in_place_without_duplicate_page(self):
        token = 'secret_test_notion_token_12345'
        parent_id = '11111111-2222-3333-4444-555555555555'

        # 1. First export: text-only
        config1 = NotionExportConfig(
            token=token,
            parent_id=parent_id,
            mode='compact',
            include_receipt_photo=False,
        )
        res1 = export_finalized_meal(self.mock_client, self.meal_id, self.snapshot, config1)
        self.assertTrue(res1.ok)
        self.assertEqual(res1.status, 'completed')
        page_id = res1.page_id
        self.assertEqual(len(self.mock_client.pages), 1)

        # 2. Second export: upgrade in-place with photo
        config2 = NotionExportConfig(
            token=token,
            parent_id=parent_id,
            mode='compact',
            include_receipt_photo=True,
            receipt_photo_data=(self.png_bytes, 'receipt.png', 'image/png'),
            existing_page_id=page_id,
        )
        res2 = export_finalized_meal(self.mock_client, self.meal_id, self.snapshot, config2)
        self.assertTrue(res2.ok)
        self.assertEqual(res2.status, 'completed')
        self.assertEqual(res2.page_id, page_id)
        self.assertEqual(len(self.mock_client.pages), 1, "Must not create a duplicate Notion page")
        self.assertEqual(res2.blocks_created, 1)

        # 3. Third export: same photo -> already_exported
        res3 = export_finalized_meal(self.mock_client, self.meal_id, self.snapshot, config2)
        self.assertTrue(res3.ok)
        self.assertEqual(res3.status, 'already_exported')
        self.assertEqual(res3.page_id, page_id)
        self.assertEqual(len(self.mock_client.pages), 1)


class TestReceiptPhotoSharing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'settletable.sqlite'
        self.storage_dir = Path(self.temp_dir.name) / 'receipt_photos'
        self.authority = Authority(str(self.db_path), storage_dir=self.storage_dir)

        self.meal_id = 'test-meal-photo-sharing'
        res = self.authority.bootstrap(self.meal_id, (
            Participant('O', 'Alice', True),
            Participant('D1', 'Bob', False),
            Participant('D2', 'Charlie', False),
        ))
        self.org_cred = res.sessions[0].credential
        self.org_id = 'O'

        # Bob
        inv1 = self.authority.issue_invitation(self.org_cred, self.meal_id, 'D1')
        self.bob_cred = self.authority.redeem_invitation(inv1.token, self.meal_id).credential

        # Charlie
        inv2 = self.authority.issue_invitation(self.org_cred, self.meal_id, 'D2')
        self.charlie_cred = self.authority.redeem_invitation(inv2.token, self.meal_id).credential

        # Upload photo by organizer
        self.png_bytes = make_minimal_png(50, 50)
        self.authority.store_receipt_photo(
            self.org_cred, self.meal_id, self.png_bytes, 'image/png', 50, 50
        )

        self.app = SettleTableApp(
            db_path=str(self.db_path),
            storage_dir=str(self.storage_dir),
            server_origin='http://localhost:8000',
        )

    def tearDown(self):
        self.app.close()
        self.authority.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _call(self, method: str, path: str, headers: dict | None = None, body: bytes | dict | None = None):
        import io
        environ = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'HTTP_HOST': 'localhost:8000',
            'HTTP_ORIGIN': 'http://localhost:8000',
            'HTTP_X_SETTLETABLE_ACTION': '1',
            'SERVER_NAME': 'localhost',
            'SERVER_PORT': '8000',
            'wsgi.url_scheme': 'http',
        }
        if headers:
            for k, v in headers.items():
                if k.startswith('HTTP_') or k in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                    environ[k] = v
                else:
                    environ['HTTP_' + k.replace('-', '_').upper()] = v

        if body is not None:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode('utf-8')
                environ['CONTENT_TYPE'] = 'application/json'
            else:
                body_bytes = body
            environ['CONTENT_LENGTH'] = str(len(body_bytes))
            environ['wsgi.input'] = io.BytesIO(body_bytes)
        else:
            environ['wsgi.input'] = io.BytesIO(b'')

        resp_headers = []
        status_box = []

        def start_response(status, response_headers):
            status_box.append(status)
            resp_headers.extend(response_headers)

        body_iter = self.app(environ, start_response)
        res_body = b''.join(body_iter)
        code = int(status_box[0].split()[0])
        return code, resp_headers, res_body

    def _finalize_meal(self):
        # Set receipt with 1 item, claim it, review, finalize
        receipt = Receipt(
            items=(ReceiptItem('item-1', 'Burger', 1, 2000),),
            subtotal_sen=2000,
            total_sen=2000,
            adjustments=(),
        )
        snap = self.authority.snapshot(self.org_cred, self.meal_id)
        self.authority.apply(self.org_cred, self.meal_id, ReplaceReceipt('cmd-r1', snap.revision, snap.financial_revision, receipt))
        snap = self.authority.snapshot(self.org_cred, self.meal_id)
        item_rev = snap.items[0].item_revision
        self.authority.apply(self.bob_cred, self.meal_id, SetOwnQuantity('cmd-b1', 'item-1', 1, item_rev, snap.financial_revision))
        snap = self.authority.snapshot(self.org_cred, self.meal_id)
        self.authority.apply(self.org_cred, self.meal_id, ReviewReceipt('cmd-rev', snap.revision, snap.financial_revision, snap.receipt_digest))
        snap = self.authority.snapshot(self.org_cred, self.meal_id)
        self.authority.apply(self.org_cred, self.meal_id, Finalize('cmd-fin', snap.revision, snap.financial_revision))

    def test_default_sharing_is_disabled(self):
        snap = self.authority.snapshot(self.bob_cred, self.meal_id)
        self.assertFalse(snap.receipt_photo_shared)
        self.assertFalse(snap.receipt_photo.get('shared', False))

    def test_sharing_cannot_be_enabled_before_finalization(self):
        # Unfinalized meal -> cannot enable photo sharing
        with self.assertRaises(AuthorityError) as ctx:
            self.authority.set_receipt_photo_sharing(self.org_cred, self.meal_id, True)
        self.assertEqual(ctx.exception.code, 'not_finalized')

        # Transport route returns 409
        code, _, res_body = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo/share',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}', 'X-SettleTable-Action': '1'},
            body={'share': True},
        )
        self.assertEqual(code, 409)

    def test_non_organizer_cannot_toggle_sharing(self):
        self._finalize_meal()
        with self.assertRaises(AuthorityError) as ctx:
            self.authority.set_receipt_photo_sharing(self.bob_cred, self.meal_id, True)
        self.assertEqual(ctx.exception.code, 'forbidden')

        code, _, _ = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo/share',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.bob_cred}', 'X-SettleTable-Action': '1'},
            body={'share': True},
        )
        self.assertEqual(code, 403)

    def test_organizer_can_enable_and_disable_sharing_post_finalization(self):
        self._finalize_meal()

        # Before sharing: Bob GET photo returns 403
        code, _, _ = self._call(
            'GET',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.bob_cred}'},
        )
        self.assertEqual(code, 403)

        # Organizer enables sharing
        code, _, res_body = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo/share',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}', 'X-SettleTable-Action': '1'},
            body={'share': True},
        )
        self.assertEqual(code, 200)
        data = json.loads(res_body.decode('utf-8'))
        self.assertTrue(data['ok'])
        self.assertTrue(data['shared'])

        # Snapshot reflects sharing enabled for all participants
        snap_org = self.authority.snapshot(self.org_cred, self.meal_id)
        snap_bob = self.authority.snapshot(self.bob_cred, self.meal_id)
        self.assertTrue(snap_org.receipt_photo_shared)
        self.assertTrue(snap_bob.receipt_photo_shared)
        self.assertTrue(snap_bob.receipt_photo['shared'])

        # Bob can now GET photo
        code_get, headers_get, img_data = self._call(
            'GET',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.bob_cred}'},
        )
        self.assertEqual(code_get, 200)
        self.assertEqual(img_data, self.png_bytes)
        hdr_dict = dict(headers_get)
        self.assertIn('no-store', hdr_dict.get('Cache-Control', ''))
        self.assertEqual(hdr_dict.get('X-Content-Type-Options'), 'nosniff')

        # Charlie (other diner) can also GET photo
        code_char, _, char_img = self._call(
            'GET',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.charlie_cred}'},
        )
        self.assertEqual(code_char, 200)
        self.assertEqual(char_img, self.png_bytes)

        # Organizer disables sharing
        code_dis, _, dis_body = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo/share',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}', 'X-SettleTable-Action': '1'},
            body={'share': False},
        )
        self.assertEqual(code_dis, 200)
        dis_data = json.loads(dis_body.decode('utf-8'))
        self.assertFalse(dis_data['shared'])

        # Bob GET photo is immediately 403 again
        code_revoked, _, _ = self._call(
            'GET',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.bob_cred}'},
        )
        self.assertEqual(code_revoked, 403)

    def test_inactive_and_cross_meal_participants_remain_forbidden(self):
        self._finalize_meal()
        # Enable sharing
        self.authority.set_receipt_photo_sharing(self.org_cred, self.meal_id, True)

        # Deactivate Charlie
        from settletable.authority import RevokeMembership
        snap = self.authority.snapshot(self.org_cred, self.meal_id)
        self.authority.apply(self.org_cred, self.meal_id, RevokeMembership('cmd-rev-c', snap.revision, 'D2'))

        # Deactivated Charlie is rejected with invalid_session
        with self.assertRaises(AuthorityError) as ctx:
            self.authority.get_receipt_photo(self.charlie_cred, self.meal_id)
        self.assertEqual(ctx.exception.code, 'invalid_session')

        # Unauthenticated request is rejected with 401
        code_unauth, _, _ = self._call(
            'GET',
            f'/api/meals/{self.meal_id}/receipt/photo',
        )
        self.assertEqual(code_unauth, 401)

        # Cross-meal session (session from meal2) rejected
        meal2 = 'other-meal-999'
        res2 = self.authority.bootstrap(meal2, (Participant('O2', 'Dave', True),))
        dave_cred = res2.sessions[0].credential
        code_cross, _, _ = self._call(
            'GET',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={'HTTP_AUTHORIZATION': f'Bearer {dave_cred}'},
        )
        self.assertEqual(code_cross, 401)

    def test_diner_write_operations_remain_forbidden_when_shared(self):
        self._finalize_meal()
        self.authority.set_receipt_photo_sharing(self.org_cred, self.meal_id, True)

        # Diner POST photo rejected
        code_post, _, _ = self._call(
            'POST',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={
                'CONTENT_TYPE': 'image/png',
                'HTTP_AUTHORIZATION': f'Bearer {self.bob_cred}',
                'X-SettleTable-Action': '1',
            },
            body=self.png_bytes,
        )
        self.assertEqual(code_post, 403)

        # Diner DELETE photo rejected
        code_del, _, _ = self._call(
            'DELETE',
            f'/api/meals/{self.meal_id}/receipt/photo',
            headers={
                'HTTP_AUTHORIZATION': f'Bearer {self.bob_cred}',
                'X-SettleTable-Action': '1',
            },
        )
        self.assertEqual(code_del, 403)

    def test_financial_calculations_preserved_when_toggling_sharing(self):
        self._finalize_meal()
        snap_before = self.authority.snapshot(self.org_cred, self.meal_id)

        # Toggle sharing on and off
        self.authority.set_receipt_photo_sharing(self.org_cred, self.meal_id, True)
        self.authority.set_receipt_photo_sharing(self.org_cred, self.meal_id, False)

        snap_after = self.authority.snapshot(self.org_cred, self.meal_id)

        # Exact financial revisions and calculation outputs preserved
        self.assertEqual(snap_before.revision, snap_after.revision)
        self.assertEqual(snap_before.financial_revision, snap_after.financial_revision)
        self.assertEqual(snap_before.receipt_digest, snap_after.receipt_digest)
        self.assertEqual(snap_before.finalized_revision, snap_after.finalized_revision)
        self.assertEqual(snap_before.calculation.consumption, snap_after.calculation.consumption)


if __name__ == '__main__':
    unittest.main()
