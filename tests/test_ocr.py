"""Comprehensive tests for SettleTable Bounded Local OCR Pipeline."""
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from settletable.authority import Authority, Participant
from settletable.ocr import (
    InvalidImageError,
    MockOcrEngine,
    OcrLine,
    OcrUnavailableError,
    parse_malaysian_receipt,
    parse_sen,
    validate_image_payload,
)
from settletable.transport import SettleTableApp, TransportError

FIXTURES_DIR = Path(__file__).parent / 'fixtures' / 'ocr'
TOKENS_FILE = FIXTURES_DIR / 'tokens.json'
SYNTHETIC_IMAGE_FILE = FIXTURES_DIR / 'images' / 'synthetic_clear.png'


def load_token_fixtures():
    if not TOKENS_FILE.exists():
        return {}
    raw = json.loads(TOKENS_FILE.read_text(encoding='utf-8'))
    fixtures = {}
    for key, lines in raw.items():
        fixtures[key] = [
            OcrLine(text=l['text'], score=l['score'], box=tuple(tuple(pt) for pt in l['box']))
            for l in lines
        ]
    return fixtures


class TestImageHeaderValidation(unittest.TestCase):
    """Test image magic bytes, MIME matching, and dimension bounds validation."""

    def test_valid_png_header_and_dimensions(self):
        # 100x200 PNG header
        header = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + (100).to_bytes(4, 'big') + (200).to_bytes(4, 'big') + b'\x08\x02\x00\x00\x00'
        fmt, w, h = validate_image_payload(header, 'image/png')
        self.assertEqual(fmt, 'png')
        self.assertEqual((w, h), (100, 200))

    def test_valid_jpeg_header_and_dimensions(self):
        # Minimal JPEG with SOF0 marker (height=300, width=400)
        header = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xc0\x00\x11\x08' + (300).to_bytes(2, 'big') + (400).to_bytes(2, 'big') + b'\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01'
        fmt, w, h = validate_image_payload(header, 'image/jpeg')
        self.assertEqual(fmt, 'jpeg')
        self.assertEqual((w, h), (400, 300))

    def test_valid_webp_vp8x_header_and_dimensions(self):
        # Extended WebP with canvas size 640x480
        # VP8X width-1 is 24-bit LE at offset 24, height-1 at offset 27
        w_bytes = (639).to_bytes(3, 'little')
        h_bytes = (479).to_bytes(3, 'little')
        header = b'RIFF\x00\x01\x00\x00WEBPVP8X\x0a\x00\x00\x00\x00\x00\x00\x00' + w_bytes + h_bytes
        fmt, w, h = validate_image_payload(header, 'image/webp')
        self.assertEqual(fmt, 'webp')
        self.assertEqual((w, h), (640, 480))

    def test_rejects_empty_payload(self):
        with self.assertRaises(InvalidImageError) as ctx:
            validate_image_payload(b'')
        self.assertEqual(str(ctx.exception), 'empty_payload')

    def test_rejects_oversized_payload(self):
        oversized = b'x' * (5_242_880 + 1)
        with self.assertRaises(InvalidImageError) as ctx:
            validate_image_payload(oversized)
        self.assertEqual(str(ctx.exception), 'payload_too_large')

    def test_rejects_non_image_magic_bytes(self):
        # HTML / SVG / scripts
        for bad in (b'<!DOCTYPE html><html>', b'<svg xmlns="http://www.w3.org/2000/svg">', b'<?php phpinfo(); ?>', b'MZ\x90\x00'):
            with self.assertRaises(InvalidImageError) as ctx:
                validate_image_payload(bad)
            self.assertEqual(str(ctx.exception), 'invalid_magic_bytes')

    def test_rejects_content_type_mismatch(self):
        # PNG bytes declared as image/jpeg
        png_header = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + (10).to_bytes(4, 'big') + (10).to_bytes(4, 'big') + b'\x08\x02\x00\x00\x00'
        with self.assertRaises(InvalidImageError) as ctx:
            validate_image_payload(png_header, 'image/jpeg')
        self.assertEqual(str(ctx.exception), 'content_type_mismatch')

    def test_rejects_dimension_bomb(self):
        # PNG with 20000x20000 dimensions (400 MP, decompression bomb)
        bomb = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + (20000).to_bytes(4, 'big') + (20000).to_bytes(4, 'big') + b'\x08\x02\x00\x00\x00'
        with self.assertRaises(InvalidImageError) as ctx:
            validate_image_payload(bomb)
        self.assertEqual(str(ctx.exception), 'image_dimensions_too_large')


class TestMalaysianReceiptParser(unittest.TestCase):
    """Test Malaysian dining receipt layout parsing against token fixtures."""

    @classmethod
    def setUpClass(cls):
        cls.fixtures = load_token_fixtures()

    def test_wan_sheng_tax_inclusive_rule(self):
        tokens = self.fixtures.get('X51008030563.jpg')
        if not tokens:
            self.skipTest('Token fixtures for X51008030563.jpg not found')
        candidate = parse_malaysian_receipt(tokens)

        # In tax-inclusive receipts, subtotal_sen MUST equal the sum of line items (600 sen)
        # to satisfy SettleTable's calculation invariant (item_subtotal == subtotal_sen)
        items_sum = sum(i.line_sen for i in candidate.items)
        self.assertEqual(candidate.subtotal_sen, 600)
        self.assertEqual(items_sum, 600)
        self.assertEqual(candidate.total_sen, 600)
        self.assertTrue(candidate.tax_included)
        self.assertEqual(candidate.included_tax_sen, 34)
        self.assertEqual(candidate.printed_net_subtotal_sen, 566)
        self.assertEqual(candidate.discrepancy_sen, 0)
        self.assertTrue(candidate.reconciled)
        self.assertEqual(candidate.route, 'human_verification')
        # Tax is already inside line items, so no external additive tax adjustment
        self.assertEqual(len(candidate.adjustments), 0)

    def test_coffee_bean_tax_exclusive_and_rounding(self):
        tokens = self.fixtures.get('X51006828201.jpg')
        if not tokens:
            self.skipTest('Token fixtures for X51006828201.jpg not found')
        candidate = parse_malaysian_receipt(tokens)

        self.assertEqual(candidate.total_sen, 3970)
        self.assertEqual(candidate.tax_sen, 225)
        self.assertEqual(candidate.service_sen, 341)
        self.assertEqual(candidate.rounding_sen, -2)
        # Rounding adjustment is negative sen
        adj_rounding = next(a for a in candidate.adjustments if a.kind == 'rounding')
        self.assertEqual(adj_rounding.amount_sen, -2)
        self.assertEqual(candidate.discrepancy_sen, 0)
        self.assertTrue(candidate.reconciled)

    def test_kechara_unprinted_rounding_discrepancy_flagged(self):
        tokens = self.fixtures.get('X51006647984.jpg')
        if not tokens:
            self.skipTest('Token fixtures for X51006647984.jpg not found')
        candidate = parse_malaysian_receipt(tokens)

        # The slip components sum to 6448 sen, total is 6450 sen, but NO rounding row is printed.
        # Parser must NOT invent a 2-sen rounding adjustment!
        self.assertIsNone(candidate.rounding_sen)
        self.assertEqual(candidate.discrepancy_sen, 2)
        self.assertFalse(candidate.reconciled)
        self.assertIn('candidate_receipt_mismatch', candidate.issues)
        self.assertEqual(candidate.route, 'manual_correction')

    def test_summary_line_without_amounts_does_not_abort_item_scanning(self):
        # Regression test: table headers containing 'Subtotal' or tax header 'GST ID' without amounts
        # must NOT prematurely terminate item parsing.
        box = ((10, 10), (100, 10), (100, 30), (10, 30))
        lines = [
            OcrLine("RESTORAN VEGAN JAYA", 0.99, ((10, 10), (100, 10), (100, 30), (10, 30))),
            OcrLine("GST ID : (000619970560)", 0.98, ((10, 35), (100, 35), (100, 50), (10, 50))),
            OcrLine("Qty Product Code Unit RM Subtotal RM", 0.97, ((10, 55), (100, 55), (100, 70), (10, 70))),
            OcrLine("MUSHROOM CURRY 1 16.80", 0.99, ((10, 75), (100, 75), (100, 95), (10, 95))),
            OcrLine("BROWN RICE 2 3.00 6.00", 0.98, ((10, 100), (100, 100), (100, 120), (10, 120))),
            OcrLine("SUB-TOTAL 22.80", 0.99, ((10, 130), (100, 130), (100, 150), (10, 150))),
            OcrLine("TOTAL 22.80", 0.99, ((10, 160), (100, 160), (100, 180), (10, 180))),
        ]
        cand = parse_malaysian_receipt(lines)
        self.assertEqual(len(cand.items), 2)
        self.assertEqual(cand.items[0].label, "MUSHROOM CURRY")
        self.assertEqual(cand.items[0].line_sen, 1680)
        self.assertEqual(cand.items[1].label, "BROWN RICE")
        self.assertEqual(cand.items[1].quantity, (2, 1))
        self.assertEqual(cand.items[1].unit_price_sen, 300)
        self.assertEqual(cand.items[1].line_sen, 600)
        self.assertTrue(cand.reconciled)

    def test_trailing_item_quantity_extraction(self):
        lines = [
            OcrLine("RESTORAN TEST", 0.99, ((10, 10), (100, 10), (100, 30), (10, 30))),
            OcrLine("NASI LEMAK 3 12.00 36.00", 0.99, ((10, 50), (100, 50), (100, 70), (10, 70))),
            OcrLine("TEH TARIK 2 3.00 6.00", 0.99, ((10, 75), (100, 75), (100, 95), (10, 95))),
            OcrLine("SUBTOTAL 42.00", 0.99, ((10, 110), (100, 110), (100, 130), (10, 130))),
            OcrLine("TOTAL 42.00", 0.99, ((10, 140), (100, 140), (100, 160), (10, 160))),
        ]
        cand = parse_malaysian_receipt(lines)
        self.assertEqual(len(cand.items), 2)
        self.assertEqual(cand.items[0].label, "NASI LEMAK")
        self.assertEqual(cand.items[0].quantity, (3, 1))
        self.assertEqual(cand.items[0].unit_price_sen, 1200)
        self.assertEqual(cand.items[0].line_sen, 3600)
        self.assertEqual(cand.items[1].label, "TEH TARIK")
        self.assertEqual(cand.items[1].quantity, (2, 1))
        self.assertEqual(cand.items[1].line_sen, 600)
        self.assertTrue(cand.reconciled)

    def test_trailing_zero_quantity_does_not_set_zero_quantity(self):
        lines = [
            OcrLine("RESTORAN TEST", 0.99, ((10, 10), (100, 10), (100, 30), (10, 30))),
            OcrLine("COKE ZERO 0 5.00", 0.99, ((10, 50), (100, 50), (100, 70), (10, 70))),
            OcrLine("TOTAL 5.00", 0.99, ((10, 140), (100, 140), (100, 160), (10, 160))),
        ]
        cand = parse_malaysian_receipt(lines)
        self.assertEqual(len(cand.items), 1)
        self.assertEqual(cand.items[0].quantity, (1, 1))

    def test_synthetic_clear_reconciliation(self):
        tokens = self.fixtures.get('synthetic_clear.png')
        if not tokens:
            self.skipTest('Token fixtures for synthetic_clear.png not found')
        candidate = parse_malaysian_receipt(tokens)

        self.assertEqual(candidate.subtotal_sen, 2900)
        self.assertEqual(candidate.tax_sen, 174)
        self.assertEqual(candidate.service_sen, 290)
        self.assertEqual(candidate.discount_sen, 200)
        self.assertEqual(candidate.rounding_sen, 1)
        self.assertEqual(candidate.total_sen, 3165)
        # Verify discount is negative sen in SettleTable domain model
        adj_discount = next(a for a in candidate.adjustments if a.kind == 'discount')
        self.assertEqual(adj_discount.amount_sen, -200)
        self.assertEqual(candidate.discrepancy_sen, 0)
        self.assertTrue(candidate.reconciled)
        self.assertEqual(candidate.route, 'human_verification')


class TestOcrTransportIntegration(unittest.TestCase):
    """Test wire transport endpoint POST /api/meals/{meal_id}/ocr/extract."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'transport_ocr.sqlite'
        self.fixtures = load_token_fixtures()
        default_tokens = self.fixtures.get('synthetic_clear.png', [])
        self.mock_engine = MockOcrEngine(default_lines=default_tokens)
        self.app = SettleTableApp(
            self.db_path,
            server_origin='http://localhost:8000',
            ocr_engine=self.mock_engine,
        )

        # Bootstrap test meal: Alice (organizer), Bob (diner)
        authority = Authority(str(self.db_path))
        res = authority.bootstrap('meal-ocr-test', (
            Participant('O', 'Alice', True),
            Participant('D1', 'Bob', False),
        ))
        self.org_cred = res.sessions[0].credential
        # Bob joins via invitation
        grant = authority.issue_invitation(self.org_cred, 'meal-ocr-test', 'D1')
        redeem = authority.redeem_invitation(grant.token, 'meal-ocr-test')
        self.diner_cred = redeem.credential
        authority.close()

        # Valid test image bytes (PNG)
        if SYNTHETIC_IMAGE_FILE.exists():
            self.valid_png_bytes = SYNTHETIC_IMAGE_FILE.read_bytes()
        else:
            self.valid_png_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + (100).to_bytes(4, 'big') + (100).to_bytes(4, 'big') + b'\x08\x02\x00\x00\x00'

    def tearDown(self):
        self.app.close()
        self.temp_dir.cleanup()

    def _call(self, method, path, headers=None, body=b''):
        headers = headers or {}
        env = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'SERVER_NAME': 'localhost',
            'SERVER_PORT': '8000',
            'HTTP_HOST': 'localhost:8000',
            'wsgi.url_scheme': 'http',
            'wsgi.input': tempfile.SpooledTemporaryFile(),
        }
        if body:
            env['wsgi.input'].write(body)
            env['wsgi.input'].seek(0)
            env['CONTENT_LENGTH'] = str(len(body))
        for k, v in headers.items():
            key = 'HTTP_' + k.upper().replace('-', '_')
            if k.lower() == 'content-type':
                env['CONTENT_TYPE'] = v
            elif k.lower() == 'content-length':
                env['CONTENT_LENGTH'] = v
            else:
                env[key] = v

        response_status = None
        response_headers = None

        def start_response(status, hdrs):
            nonlocal response_status, response_headers
            response_status = status
            response_headers = hdrs

        input_file = env['wsgi.input']
        try:
            chunks = self.app(env, start_response)
            res_body = b''.join(chunks)
        finally:
            input_file.close()
        code = int(response_status.split()[0])
        return code, response_headers, res_body

    def test_organizer_successful_ocr_extraction(self):
        headers = {
            'Authorization': f'Bearer {self.org_cred}',
            'X-SettleTable-Action': '1',
            'Content-Type': 'image/png',
        }
        code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
        self.assertEqual(code, 200)
        data = json.loads(body.decode('utf-8'))
        self.assertTrue(data['ok'])
        cand = data['candidate']
        self.assertEqual(cand['total_sen'], 3165)
        self.assertEqual(cand['subtotal_sen'], 2900)
        self.assertTrue(cand['reconciled'])

    def test_content_type_mismatch_rejected_400(self):
        headers = {
            'Authorization': f'Bearer {self.org_cred}',
            'X-SettleTable-Action': '1',
            'Content-Type': 'image/jpeg',
        }
        # Send PNG bytes with image/jpeg header
        code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
        self.assertEqual(code, 400)
        data = json.loads(body.decode('utf-8'))
        self.assertEqual(data['error'], 'invalid_image')

    def test_diner_extraction_forbidden_403(self):
        headers = {
            'Authorization': f'Bearer {self.diner_cred}',
            'X-SettleTable-Action': '1',
            'Content-Type': 'image/png',
        }
        code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
        self.assertEqual(code, 403)
        data = json.loads(body.decode('utf-8'))
        self.assertEqual(data['error'], 'forbidden')

    def test_unauthenticated_extraction_401(self):
        headers = {
            'X-SettleTable-Action': '1',
            'Content-Type': 'image/png',
            'Origin': 'http://localhost:8000',
        }
        code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
        self.assertEqual(code, 401)

    def test_missing_csrf_action_header_400(self):
        headers = {
            'Authorization': f'Bearer {self.org_cred}',
            'Content-Type': 'image/png',
        }
        code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
        self.assertEqual(code, 400)
        data = json.loads(body.decode('utf-8'))
        self.assertEqual(data['error'], 'missing_action_header')

    def test_cookie_origin_mismatch_403(self):
        headers = {
            'Cookie': f'settletable_session={self.org_cred}',
            'X-SettleTable-Action': '1',
            'Origin': 'https://evil.attacker.com',
            'Content-Type': 'image/png',
        }
        code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
        self.assertEqual(code, 403)
        data = json.loads(body.decode('utf-8'))
        self.assertEqual(data['error'], 'origin_mismatch')

    def test_non_image_payload_rejected_400(self):
        headers = {
            'Authorization': f'Bearer {self.org_cred}',
            'X-SettleTable-Action': '1',
            'Content-Type': 'text/plain',
        }
        code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, b'Hello World')
        self.assertEqual(code, 400)
        data = json.loads(body.decode('utf-8'))
        self.assertEqual(data['error'], 'invalid_image')

    def test_oversized_payload_rejected_413(self):
        headers = {
            'Authorization': f'Bearer {self.org_cred}',
            'X-SettleTable-Action': '1',
            'Content-Type': 'image/png',
        }
        oversized = b'\x89PNG\r\n\x1a\n' + b'0' * 5_242_880
        code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, oversized)
        self.assertEqual(code, 413)
        data = json.loads(body.decode('utf-8'))
        self.assertEqual(data['error'], 'payload_too_large')

    def test_ocr_unavailable_returns_503(self):
        # Set engine to None and simulate missing RapidOCR
        app_no_ocr = SettleTableApp(self.db_path, ocr_engine=None)
        headers = {
            'Authorization': f'Bearer {self.org_cred}',
            'X-SettleTable-Action': '1',
            'Content-Type': 'image/png',
        }
        with patch('settletable.transport.SettleTableApp.get_ocr_engine', side_effect=TransportError('ocr_unavailable', 503)):
            env = {
                'REQUEST_METHOD': 'POST',
                'PATH_INFO': '/api/meals/meal-ocr-test/ocr/extract',
                'SERVER_NAME': 'localhost',
                'SERVER_PORT': '8000',
                'HTTP_HOST': 'localhost:8000',
                'wsgi.url_scheme': 'http',
                'wsgi.input': tempfile.SpooledTemporaryFile(),
                'CONTENT_LENGTH': str(len(self.valid_png_bytes)),
                'CONTENT_TYPE': 'image/png',
                'HTTP_X_SETTLETABLE_ACTION': '1',
                'HTTP_AUTHORIZATION': f'Bearer {self.org_cred}',
            }
            env['wsgi.input'].write(self.valid_png_bytes)
            env['wsgi.input'].seek(0)
            status_out = None
            def sr(s, h):
                nonlocal status_out
                status_out = s
            try:
                chunks = app_no_ocr(env, sr)
            finally:
                env['wsgi.input'].close()
            code = int(status_out.split()[0])
            self.assertEqual(code, 503)
        app_no_ocr.close()

    def test_zero_state_and_database_mutation(self):
        # Read DB hash before OCR call
        db_bytes_before = self.db_path.read_bytes()
        sha_before = hashlib.sha256(db_bytes_before).hexdigest()

        headers = {
            'Authorization': f'Bearer {self.org_cred}',
            'X-SettleTable-Action': '1',
            'Content-Type': 'image/png',
        }
        code, _, _ = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
        self.assertEqual(code, 200)

        # Check DB hash after call: MUST be byte-for-byte identical
        db_bytes_after = self.db_path.read_bytes()
        sha_after = hashlib.sha256(db_bytes_after).hexdigest()
        self.assertEqual(sha_before, sha_after)

    def test_air_gap_zero_outbound_network_sockets(self):
        headers = {
            'Authorization': f'Bearer {self.org_cred}',
            'X-SettleTable-Action': '1',
            'Content-Type': 'image/png',
        }
        with patch.object(socket.socket, 'connect', side_effect=RuntimeError('Outbound network attempt blocked!')):
            code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
            self.assertEqual(code, 200)


class TestRapidOcrEngineOutputCompatibility(unittest.TestCase):
    """Test RapidOcrEngine across different RapidOCR distribution return types."""

    def setUp(self):
        # Generate minimal valid PNG bytes (10x10)
        self.valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + (10).to_bytes(4, 'big') + (10).to_bytes(4, 'big') + b'\x08\x02\x00\x00\x00'

    def test_handles_rapidocr_onnxruntime_tuple_return(self):
        from settletable.ocr.engine import RapidOcrEngine
        engine = object.__new__(RapidOcrEngine)
        # rapidocr_onnxruntime returns (result_list, elapse_list)
        box = [[10, 10], [100, 10], [100, 30], [10, 30]]
        engine._engine = lambda img: ([[box, "NASI LEMAK", 0.985]], [0.01, 0.05])
        lines = engine.recognize(self.valid_png)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "NASI LEMAK")
        self.assertEqual(lines[0].score, 0.985)
        self.assertEqual(lines[0].box, ((10, 10), (100, 10), (100, 30), (10, 30)))

    def test_handles_rapidocr_dataclass_return(self):
        from settletable.ocr.engine import RapidOcrEngine
        from dataclasses import dataclass

        @dataclass
        class MockRapidOCROutput:
            boxes: list
            txts: list
            scores: list

        engine = object.__new__(RapidOcrEngine)
        box = [[10, 10], [100, 10], [100, 30], [10, 30]]
        engine._engine = lambda img: MockRapidOCROutput(boxes=[box], txts=["TEH TARIK"], scores=[0.97])
        lines = engine.recognize(self.valid_png)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "TEH TARIK")
        self.assertEqual(lines[0].score, 0.97)

    def test_handles_empty_or_none_recognition(self):
        from settletable.ocr.engine import RapidOcrEngine
        engine = object.__new__(RapidOcrEngine)
        # Empty tuple or None
        engine._engine = lambda img: (None, None)
        lines = engine.recognize(self.valid_png)
        self.assertEqual(lines, [])


if __name__ == '__main__':
    unittest.main()
