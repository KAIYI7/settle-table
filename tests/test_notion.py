"""Comprehensive tests for SettleTable Bounded Notion Reporting."""
import json
from pathlib import Path
import re
import socket
import tempfile
import time
import unittest

from settletable.authority import (
    Authority,
    Finalize,
    Participant,
    Receipt,
    ReceiptAdjustment,
    ReceiptItem,
    ReplaceReceipt,
    ReviewReceipt,
    SetOwnQuantity,
)
from settletable.notion import (
    MockNotionClient,
    NotionAuthError,
    NotionExportConfig,
    NotionNotFoundError,
    NotionRateLimitError,
    NotionValidationError,
    count_notion_blocks,
    export_finalized_meal,
    format_compact_meal_blocks,
    format_full_meal_blocks,
    format_meal_properties,
    format_sen,
    sanitize_notion_error_message,
    text_cell,
)
from settletable.transport import SettleTableApp, redact_log_string


class TestNotionModelsAndFormatting(unittest.TestCase):
    """Test pure unit models, money formatting, and block generation."""

    def test_format_sen(self):
        self.assertEqual(format_sen(0), "RM 0.00")
        self.assertEqual(format_sen(5), "RM 0.05")
        self.assertEqual(format_sen(1250), "RM 12.50")
        self.assertEqual(format_sen(-50), "-RM 0.50")
        self.assertEqual(format_sen(None), "RM 0.00")

    def test_text_cell(self):
        cell = text_cell("Test Cell")
        self.assertEqual(cell, [{"type": "text", "text": {"content": "Test Cell"}}])

    def test_sanitize_notion_error_message(self):
        msg = "Error with token secret_abcdef1234567890123456 and Bearer mytoken123"
        cleaned = sanitize_notion_error_message(msg)
        self.assertNotIn("secret_abcdef", cleaned)
        self.assertNotIn("mytoken123", cleaned)
        self.assertIn("secret_[REDACTED]", cleaned)

    def test_transport_redact_log_string_notion_tokens(self):
        log_line = 'User provided {"token": "secret_1234567890abcdefghijk"} with Bearer abc'
        cleaned = redact_log_string(log_line)
        self.assertNotIn("secret_1234567890", cleaned)
        self.assertIn('"token":"[REDACTED]"', cleaned)
        self.assertIn('Bearer [REDACTED]', cleaned)

    def test_compact_blocks_quota_under_40(self):
        """Verify that a meal with 6 diners and 10 items creates <= 40 blocks."""
        participants = [
            {"id": f"P{i}", "name": f"Diner {i}", "is_organizer": (i == 1)}
            for i in range(1, 7)
        ]
        items = [
            {"id": f"it_{i}", "label": f"Food {i}", "quantity": 1, "line_sen": 1000}
            for i in range(1, 11)
        ]
        snapshot = {
            "finalized": True,
            "revision": 5,
            "receipt": {
                "merchant": "Warung Kopitiam",
                "subtotal_sen": 10000,
                "total_sen": 10600,
                "included_tax_sen": 600,
                "items": items,
                "adjustments": [],
            },
            "calculation": {
                "consumption": {
                    f"P{i}": {"base_sen": 1666, "adjustments_sen": 100, "total_sen": 1766}
                    for i in range(1, 7)
                }
            },
            "participants": participants,
            "claims": {},
        }
        blocks = format_compact_meal_blocks("meal-test", snapshot)
        # Count total blocks: each block + table rows
        total_block_count = 0
        for b in blocks:
            total_block_count += 1
            if b.get("type") == "table":
                total_block_count += len(b.get("table", {}).get("children", []))

        # 1 callout + 2 headings + 2 tables + (1 header + 6 diners) + (1 header + 10 items) + 1 divider + 1 audit <= 40 blocks
        self.assertLessEqual(total_block_count, 40)
        self.assertEqual(total_block_count, count_notion_blocks(blocks))

    def test_large_meal_compact_blocks_bounded_to_40(self):
        """Verify that a very large meal (25 diners, 60 items) is strictly bounded to <= 40 blocks."""
        participants = [
            {"id": f"P{i}", "name": f"Diner {i}", "is_organizer": (i == 1)}
            for i in range(1, 26)
        ]
        items = [
            {"id": f"it_{i}", "label": f"Food Item {i}", "quantity": 1, "line_sen": 500}
            for i in range(1, 61)
        ]
        snapshot = {
            "finalized": True,
            "revision": 10,
            "receipt": {
                "merchant": "Banquet Palace",
                "subtotal_sen": 30000,
                "total_sen": 31800,
                "items": items,
                "adjustments": [],
            },
            "calculation": {
                "consumption": {
                    f"P{i}": {"base_sen": 1200, "adjustments_sen": 72, "total_sen": 1272}
                    for i in range(1, 26)
                }
            },
            "participants": participants,
            "claims": {},
        }
        blocks = format_compact_meal_blocks("meal-big", snapshot)
        total = count_notion_blocks(blocks)
        self.assertLessEqual(total, 40)

    def test_full_meal_blocks_unconstrained(self):
        """Verify that format_full_meal_blocks lists all participants and items without rollup."""
        participants = [
            {"id": f"P{i}", "name": f"Diner {i}", "is_organizer": (i == 1)}
            for i in range(1, 6)
        ]
        items = [
            {"id": f"it_{i}", "label": f"Food Item {i}", "quantity": 1, "line_sen": 500}
            for i in range(1, 16)
        ]
        snapshot = {
            "finalized": True,
            "revision": 2,
            "receipt": {
                "merchant": "Cafe",
                "subtotal_sen": 7500,
                "total_sen": 7500,
                "items": items,
                "adjustments": [],
            },
            "calculation": {
                "consumption": {
                    f"P{i}": {"base_sen": 1500, "adjustments_sen": 0, "total_sen": 1500}
                    for i in range(1, 6)
                }
            },
            "participants": participants,
            "claims": {},
        }
        blocks = format_full_meal_blocks("meal-full", snapshot)
        total = count_notion_blocks(blocks)
        # 9 fixed + 5 participants + 15 items = 29 blocks
        self.assertEqual(total, 9 + 5 + 15)


class TestMockNotionClient(unittest.TestCase):
    """Test MockNotionClient validation and error injection."""

    def setUp(self):
        self.client = MockNotionClient()

    def test_page_parent_properties_restriction(self):
        """Notion API strictly forbids properties other than 'title' on page_id parent."""
        parent = {"page_id": "11111111-2222-3333-4444-555555555555"}
        # Invalid property: Total (Sen)
        props_invalid = {
            "title": {"title": [{"type": "text", "text": {"content": "Test"}}]},
            "Total (Sen)": {"number": 1000},
        }
        with self.assertRaises(NotionValidationError):
            self.client.create_page("secret_test", parent, props_invalid)

        # Valid property: title only
        props_valid = {
            "title": {"title": [{"type": "text", "text": {"content": "Test"}}]},
        }
        res = self.client.create_page("secret_test", parent, props_valid)
        self.assertTrue(res["id"])
        self.assertIn("notion.so", res["url"])

    def test_table_block_width_mismatch(self):
        parent = {"page_id": "11111111-2222-3333-4444-555555555555"}
        props = {"title": {"title": [{"type": "text", "text": {"content": "Test"}}]}}
        # Table with width 3 but row with 2 cells
        bad_table = {
            "type": "table",
            "table": {
                "table_width": 3,
                "children": [
                    {
                        "type": "table_row",
                        "table_row": {"cells": [text_cell("A"), text_cell("B")]},
                    }
                ],
            },
        }
        with self.assertRaises(NotionValidationError):
            self.client.create_page("secret_test", parent, props, children=[bad_table])

    def test_reconciliation_detects_existing_page_and_avoids_duplicate(self):
        """Pre-creation reconciliation checks parent children and prevents duplicate pages on lost response retry."""
        parent_uuid = "11111111-2222-3333-4444-555555555555"
        config = NotionExportConfig(
            token="secret_test_12345678901234567890",
            parent_id=parent_uuid,
            parent_type="page_id",
            mode="compact",
        )
        snapshot = {
            "finalized": True,
            "revision": 3,
            "receipt": {"merchant": "Cafe Reconcile", "total_sen": 2500, "items": []},
            "calculation": {"consumption": {"P1": 2500}},
            "participants": [{"id": "P1", "name": "Alice"}],
            "claims": {},
        }
        # First export creates page in Notion
        res1 = export_finalized_meal(self.client, "meal-recon", snapshot, config)
        self.assertTrue(res1.ok)
        self.assertEqual(res1.status, "completed")
        self.assertEqual(len(self.client.pages), 1)
        created_id = res1.page_id

        # Second export simulates retry after lost response
        # It must detect the child page with identical title under parent_id,
        # adopt the existing page_id, and NOT call create_page again!
        res2 = export_finalized_meal(self.client, "meal-recon", snapshot, config)
        self.assertTrue(res2.ok)
        self.assertEqual(res2.status, "already_exported")
        self.assertEqual(res2.page_id, created_id)
        # Total pages in client remains 1, exactly 0 duplicate pages
        self.assertEqual(len(self.client.pages), 1)


class TestNotionTransportIntegration(unittest.TestCase):
    """Test wire endpoint POST /api/meals/{meal_id}/export/notion."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "notion_test.sqlite"
        self.mock_client = MockNotionClient()
        self.app = SettleTableApp(
            self.db_path,
            server_origin="http://localhost:8000",
            notion_client=self.mock_client,
            allow_sync_export=True,
        )

        # Bootstrap meal with Alice (organizer) and Bob (diner)
        authority = Authority(str(self.db_path))
        try:
            res = authority.bootstrap("meal-notion-test", (
                Participant("O", "Alice", True),
                Participant("D1", "Bob", False),
            ))
            self.org_cred = res.sessions[0].credential

            grant = authority.issue_invitation(self.org_cred, "meal-notion-test", "D1")
            redeem = authority.redeem_invitation(grant.token, "meal-notion-test")
            self.diner_cred = redeem.credential

            # Finalize meal for export tests
            rcpt = Receipt(
                items=(ReceiptItem("i1", "Burger", 1, 2000),),
                subtotal_sen=2000,
                total_sen=2000,
            )
            snap = authority.snapshot(self.org_cred, "meal-notion-test")
            c1 = ReplaceReceipt(
                command_id="cmd-1",
                receipt=rcpt,
                expected_revision=snap.revision,
                expected_financial_revision=snap.financial_revision,
            )
            authority.apply(self.org_cred, "meal-notion-test", c1)

            # Claim
            snap = authority.snapshot(self.org_cred, "meal-notion-test")
            item_rev = snap.items[0].item_revision
            c2 = SetOwnQuantity(
                command_id="cmd-2",
                item_id="i1",
                quantity=1,
                expected_item_revision=item_rev,
                expected_financial_revision=snap.financial_revision,
            )
            authority.apply(self.org_cred, "meal-notion-test", c2)

            # Review
            snap = authority.snapshot(self.org_cred, "meal-notion-test")
            c3 = ReviewReceipt(
                command_id="cmd-3",
                expected_revision=snap.revision,
                expected_financial_revision=snap.financial_revision,
                receipt_digest=snap.receipt_digest,
            )
            authority.apply(self.org_cred, "meal-notion-test", c3)

            # Finalize
            snap = authority.snapshot(self.org_cred, "meal-notion-test")
            c4 = Finalize(
                command_id="cmd-4",
                expected_revision=snap.revision,
                expected_financial_revision=snap.financial_revision,
            )
            authority.apply(self.org_cred, "meal-notion-test", c4)
        finally:
            authority.close()

    def tearDown(self):
        self.app.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _call(self, method, path, headers=None, body=None):
        headers = headers or {}
        path_info = path.split("?")[0]
        qs = path.split("?")[1] if "?" in path else ""
        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path_info,
            "QUERY_STRING": qs,
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
            "HTTP_HOST": "localhost:8000",
            "wsgi.url_scheme": "http",
            "wsgi.input": tempfile.SpooledTemporaryFile(),
        }
        body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
        if body_bytes:
            env["wsgi.input"].write(body_bytes)
            env["wsgi.input"].seek(0)
            env["CONTENT_LENGTH"] = str(len(body_bytes))
            env["CONTENT_TYPE"] = "application/json"

        for k, v in headers.items():
            key = "HTTP_" + k.upper().replace("-", "_")
            if k.lower() == "content-type":
                env["CONTENT_TYPE"] = v
            elif k.lower() == "content-length":
                env["CONTENT_LENGTH"] = v
            else:
                env[key] = v

        response_status = None
        response_headers = None

        def start_response(status, hdrs):
            nonlocal response_status, response_headers
            response_status = status
            response_headers = hdrs

        chunks = self.app(env, start_response)
        res_body = b"".join(chunks)
        env["wsgi.input"].close()
        code = int(response_status.split()[0])
        return code, response_headers, res_body

    def test_unauthenticated_export_401(self):
        headers = {
            "X-SettleTable-Action": "1",
            "Origin": "http://localhost:8000",
        }
        body = {"parent_id": "11111111-2222-3333-4444-555555555555", "token": "secret_12345678901234567890"}
        code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
        self.assertEqual(code, 401)
        data = json.loads(res_body.decode("utf-8"))
        self.assertEqual(data["error"], "invalid_session")

    def test_diner_export_forbidden_403(self):
        headers = {
            "Authorization": f"Bearer {self.diner_cred}",
            "X-SettleTable-Action": "1",
        }
        body = {"parent_id": "11111111-2222-3333-4444-555555555555", "token": "secret_12345678901234567890"}
        code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
        self.assertEqual(code, 403)
        data = json.loads(res_body.decode("utf-8"))
        self.assertEqual(data["error"], "forbidden")

    def test_invalid_uuid_rejected_400(self):
        headers = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        body = {"parent_id": "../../invalid/path", "token": "secret_12345678901234567890"}
        code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
        self.assertEqual(code, 400)
        data = json.loads(res_body.decode("utf-8"))
        self.assertEqual(data["error"], "invalid_input")

    def test_malformed_token_rejected_400(self):
        headers = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        body = {"parent_id": "11111111-2222-3333-4444-555555555555", "token": "bad_token"}
        code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
        self.assertEqual(code, 400)
        data = json.loads(res_body.decode("utf-8"))
        self.assertEqual(data["error"], "invalid_input")

    def test_successful_organizer_export_and_deduplication(self):
        headers = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        body = {
            "parent_id": "11111111-2222-3333-4444-555555555555",
            "token": "secret_12345678901234567890",
        }
        # First export via synchronous query parameter
        code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion?sync=1", headers, body)
        self.assertEqual(code, 200)
        data = json.loads(res_body.decode("utf-8"))
        self.assertTrue(data["ok"])
        exp = data["export"]
        self.assertEqual(exp["status"], "completed")
        self.assertTrue(exp["page_id"])
        self.assertIn("notion.so", exp["page_url"])

        # Second export on the same finalized revision returns already_exported
        code2, _, res_body2 = self._call("POST", "/api/meals/meal-notion-test/export/notion?sync=1", headers, body)
        self.assertEqual(code2, 200)
        data2 = json.loads(res_body2.decode("utf-8"))
        self.assertTrue(data2["ok"])
        self.assertEqual(data2["export"]["status"], "already_exported")
        self.assertEqual(data2["export"]["page_id"], exp["page_id"])
        # Exactly 1 page was created in the mock client
        self.assertEqual(len(self.mock_client.pages), 1)

    def test_async_export_and_status_polling(self):
        """Default export executes asynchronously (202 Accepted) and status is pollable via GET."""
        headers = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        body = {
            "parent_id": "11111111-2222-3333-4444-555555555555",
            "token": "secret_12345678901234567890",
        }
        # Initial POST returns 202 Accepted with status in_progress
        code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
        self.assertEqual(code, 202)
        data = json.loads(res_body.decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["export"]["status"], "in_progress")

        # Poll GET /api/meals/meal-notion-test/export/notion until completed
        import time
        completed_rec = None
        for _ in range(20):
            time.sleep(0.05)
            get_code, _, get_body = self._call("GET", "/api/meals/meal-notion-test/export/notion", headers)
            self.assertEqual(get_code, 200)
            get_data = json.loads(get_body.decode("utf-8"))
            if get_data.get("export", {}).get("status") == "completed":
                completed_rec = get_data["export"]
                break
        self.assertIsNotNone(completed_rec, "Background export failed to complete within timeout")
        self.assertTrue(completed_rec["page_id"])
        self.assertIn("notion.so", completed_rec["page_url"])

    def test_unfinalized_meal_export_conflict_409(self):
        """Exporting an unfinalized meal returns 409 meal_not_finalized."""
        # Bootstrap a draft meal
        authority = Authority(str(self.db_path))
        res = authority.bootstrap("meal-draft", (
            Participant("O2", "Alice2", True),
        ))
        draft_org_cred = res.sessions[0].credential
        authority.close()

        headers = {
            "Authorization": f"Bearer {draft_org_cred}",
            "X-SettleTable-Action": "1",
        }
        body = {
            "parent_id": "11111111-2222-3333-4444-555555555555",
            "token": "secret_12345678901234567890",
        }
        code, _, res_body = self._call("POST", "/api/meals/meal-draft/export/notion", headers, body)
        self.assertEqual(code, 409)
        data = json.loads(res_body.decode("utf-8"))
        self.assertEqual(data["error"], "meal_not_finalized")

    def test_airgap_zero_outbound_network_sockets(self):
        """Verify that Notion export test executes with zero outbound network calls."""
        headers = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        body = {
            "parent_id": "11111111-2222-3333-4444-555555555555",
            "token": "secret_12345678901234567890",
        }
        orig_connect = socket.socket.connect

        def guarded_connect(self, *args, **kwargs):
            raise RuntimeError("Outbound socket connection strictly forbidden in tests")

        socket.socket.connect = guarded_connect
        try:
            code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion?sync=1", headers, body)
            self.assertEqual(code, 200)
        finally:
            socket.socket.connect = orig_connect


    def test_sync_export_override_disabled_by_default(self):
        """Verify that ?sync=1 is safely ignored and executed asynchronously when allow_sync_export is False."""
        app_default = SettleTableApp(
            self.db_path,
            server_origin="http://localhost:8000",
            notion_client=self.mock_client,
            allow_sync_export=False,
        )
        try:
            headers = {
                "Authorization": f"Bearer {self.org_cred}",
                "X-SettleTable-Action": "1",
            }
            body = {
                "parent_id": "11111111-2222-3333-4444-555555555555",
                "token": "secret_12345678901234567890",
            }
            env = {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/meals/meal-notion-test/export/notion",
                "QUERY_STRING": "sync=1",
                "SERVER_NAME": "localhost",
                "SERVER_PORT": "8000",
                "HTTP_HOST": "localhost:8000",
                "wsgi.url_scheme": "http",
            }
            body_file = tempfile.SpooledTemporaryFile()
            env["wsgi.input"] = body_file
            body_bytes = json.dumps(body).encode("utf-8")
            body_file.write(body_bytes)
            body_file.seek(0)
            env["CONTENT_LENGTH"] = str(len(body_bytes))
            env["CONTENT_TYPE"] = "application/json"
            for k, v in headers.items():
                env[f"HTTP_{k.upper().replace('-', '_')}"] = v

            status_captured = []
            def start_response(status, resp_headers):
                status_captured.append(status)

            try:
                res_iter = app_default(env, start_response)
                res_body = b"".join(res_iter)
            finally:
                body_file.close()
            code = int(status_captured[0].split()[0])
            self.assertEqual(code, 202)
            data = json.loads(res_body.decode("utf-8"))
            self.assertEqual(data["export"]["status"], "in_progress")
        finally:
            app_default.close()

    def test_notion_export_failed_status_and_recovery(self):
        """Verify that export failures transition to 'failed' and allow clean recovery and status reporting."""
        authority = Authority(str(self.db_path))
        try:
            snap = authority.snapshot(self.org_cred, "meal-notion-test")
            rev = snap.revision
            authority.record_notion_export_failed("meal-notion-test", rev, "test_network_error")
            rec = authority.get_notion_export("meal-notion-test", rev)
            self.assertIsNotNone(rec)
            self.assertEqual(rec["status"], "failed")
            self.assertEqual(rec["export_digest"], "test_network_error")

            # GET endpoint returns failed status to caller
            headers = {"Authorization": f"Bearer {self.org_cred}"}
            code, _, res_body = self._call("GET", "/api/meals/meal-notion-test/export/notion", headers)
            self.assertEqual(code, 200)
            data = json.loads(res_body.decode("utf-8"))
            self.assertEqual(data["export"]["status"], "failed")
            self.assertEqual(data["export"]["export_digest"], "test_network_error")

            # Clean recovery: re-export succeeds
            body = {
                "parent_id": "11111111-2222-3333-4444-555555555555",
                "token": "secret_12345678901234567890",
            }
            post_headers = {
                "Authorization": f"Bearer {self.org_cred}",
                "X-SettleTable-Action": "1",
            }
            code2, _, res_body2 = self._call("POST", "/api/meals/meal-notion-test/export/notion?sync=1", post_headers, body)
            self.assertEqual(code2, 200)
            data2 = json.loads(res_body2.decode("utf-8"))
            self.assertEqual(data2["export"]["status"], "completed")
        finally:
            authority.close()

    def test_query_block_children_pagination(self):
        """Verify that NotionHttpClient.query_block_children handles cursor pagination."""
        from settletable.notion.client import NotionHttpClient
        client = NotionHttpClient()

        calls = []
        def fake_request(token, method, endpoint, data=None):
            calls.append(endpoint)
            if "start_cursor=page2" in endpoint:
                return {
                    "results": [{"id": "b3", "type": "paragraph"}],
                    "has_more": False,
                    "next_cursor": None,
                }
            return {
                "results": [{"id": "b1", "type": "paragraph"}, {"id": "b2", "type": "paragraph"}],
                "has_more": True,
                "next_cursor": "page2",
            }

        client._request = fake_request
        blocks = client.query_block_children("secret_test", "block-uuid")
        self.assertEqual(len(blocks), 3)
        self.assertEqual([b["id"] for b in blocks], ["b1", "b2", "b3"])
        self.assertEqual(len(calls), 2)

    def test_reconciliation_bubbles_rate_limit_and_auth_errors(self):
        """Verify that export_finalized_meal re-raises NotionRateLimitError and NotionAuthError during title reconciliation."""
        from settletable.notion import export_finalized_meal, NotionExportConfig, NotionRateLimitError, NotionAuthError
        from settletable.authority import Authority
        from dataclasses import asdict

        authority = Authority(self.db_path)
        try:
            snap = authority.snapshot(self.org_cred, "meal-notion-test")
            snap_dict = asdict(snap)

            # Test rate limit error bubbling
            self.mock_client._forced_error = (NotionRateLimitError, "rate limit exceeded")
            config = NotionExportConfig(token="secret_test", parent_id="11111111-2222-3333-4444-555555555555")
            with self.assertRaises(NotionRateLimitError):
                export_finalized_meal(self.mock_client, "meal-notion-test", snap_dict, config)

            # Test auth error bubbling
            self.mock_client._forced_error = (NotionAuthError, "invalid token")
            with self.assertRaises(NotionAuthError):
                export_finalized_meal(self.mock_client, "meal-notion-test", snap_dict, config)
        finally:
            authority.close()

    def test_async_export_granular_error_codes(self):
        """Verify that async background export records specific error codes (notion_rate_limited, notion_auth_error)."""
        authority = Authority(self.db_path)
        try:
            # Force rate limit error
            self.mock_client._forced_error = (NotionRateLimitError, "rate limited")
            headers = {
                "Authorization": f"Bearer {self.org_cred}",
                "X-SettleTable-Action": "1",
            }
            body = {
                "parent_id": "11111111-2222-3333-4444-555555555555",
                "token": "secret_12345678901234567890",
            }
            code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
            self.assertEqual(code, 202)

            # Poll for background thread completion
            deadline = time.time() + 5.0
            status_data = None
            while time.time() < deadline:
                _, _, get_res = self._call("GET", "/api/meals/meal-notion-test/export/notion", headers, None)
                status_data = json.loads(get_res.decode("utf-8"))
                if status_data.get("export", {}).get("status") == "failed":
                    break
                time.sleep(0.05)

            self.assertIsNotNone(status_data)
            self.assertEqual(status_data["export"]["status"], "failed")
            self.assertEqual(status_data["export"]["export_digest"], "notion_rate_limited")
        finally:
            authority.close()


if __name__ == "__main__":
    unittest.main()
