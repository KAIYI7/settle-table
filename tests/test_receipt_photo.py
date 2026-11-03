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
        self.app = SettleTableApp(str(self.db_path), storage_dir=self.storage_dir)

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


if __name__ == '__main__':
    unittest.main()
