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
    AuthorityError,
    Finalize,
    Participant,
    Receipt,
    ReceiptAdjustment,
    ReceiptItem,
    ReplaceReceipt,
    ReviewReceipt,
    SetOwnQuantity,
    AssignParticipantQuantity,
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
    extract_notion_id,
    format_compact_meal_blocks,
    format_full_meal_blocks,
    format_meal_properties,
    format_sen,
    sanitize_notion_error_message,
    text_cell,
)
from settletable.transport import SettleTableApp, redact_log_string


class TestNotionHttpClientSecurity(unittest.TestCase):
    """Test NotionHttpClient security controls, redirect disallowance, and token hygiene."""

    def test_default_api_version_is_stable_2022_06_28(self):
        from settletable.notion.client import NotionHttpClient
        cli = NotionHttpClient()
        self.assertEqual(cli.api_version, "2022-06-28")

    def test_disallow_redirect_handler_blocks_redirects_and_preserves_token(self):
        import urllib.error
        from settletable.notion.client import DisallowRedirectHandler, NotionHttpClient, NotionError

        handler = DisallowRedirectHandler()
        # Simulate a 302 redirect attempting to forward request to external domain
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            handler.redirect_request(None, None, 302, "Found", {}, "https://evil.attacker.com/leak")
        self.assertEqual(ctx.exception.code, 302)
        self.assertIn("blocked to prevent credential leakage", str(ctx.exception))

    def test_client_opener_has_disallow_redirect_handler(self):
        from settletable.notion.client import DisallowRedirectHandler, NotionHttpClient
        cli = NotionHttpClient()
        self.assertTrue(any(isinstance(h, DisallowRedirectHandler) for h in cli._opener.handlers))

    def test_request_redirect_raises_notion_error_with_blocked_msg(self):
        import io
        import urllib.error
        from unittest.mock import patch
        from settletable.notion.client import NotionHttpClient, NotionError

        cli = NotionHttpClient()
        redirect_err = urllib.error.HTTPError(
            "https://api.notion.com/v1/pages",
            302,
            "Notion API redirect (302) blocked to prevent credential leakage",
            {},
            fp=io.BytesIO(b""),
        )
        with patch.object(cli._opener, "open", side_effect=redirect_err):
            with self.assertRaises(NotionError) as ctx:
                cli._request("test_token", "GET", "pages")
            self.assertIn("302", str(ctx.exception))
            self.assertIn("blocked to prevent credential leakage", str(ctx.exception))


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

    def test_extract_notion_id(self):
        canonical = "3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d"
        # Standard hyphenated UUID
        self.assertEqual(extract_notion_id("3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d"), canonical)
        # Unhyphenated 32-hex
        self.assertEqual(extract_notion_id("3fb0ffe172a6815eb59def81c6e8eb4d"), canonical)
        # Full Notion sharing page URL with slug and query
        share_url = "https://app.notion.com/p/SYNTHETIC-Meal-001-" + "3fb0ffe172a6815eb59def81c6e8eb4d?source=copy_link"
        self.assertEqual(extract_notion_id(share_url), canonical)
        # Workspace Notion URL
        ws_url = "https://www.notion.so/my-workspace/Dinner-" + "3fb0ffe172a6815eb59def81c6e8eb4d"
        self.assertEqual(extract_notion_id(ws_url), canonical)
        # Invalid inputs
        self.assertIsNone(extract_notion_id(""))
        self.assertIsNone(extract_notion_id("not-a-uuid"))
        self.assertIsNone(extract_notion_id(None))

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

    def test_complimentary_item_renders_complimentary_in_notion_receipt(self):
        """Verify that zero-priced items without claims render as 'Complimentary' instead of 'Unclaimed'."""
        snapshot = {
            "finalized": True,
            "revision": 3,
            "receipt": {
                "subtotal_sen": 1500,
                "total_sen": 1500,
                "items": [
                    {"id": "rice", "label": "Chicken Rice", "quantity": 1, "line_sen": 1500},
                    {"id": "water", "label": "Warm Water", "quantity": 2, "line_sen": 0},
                ],
                "adjustments": [],
            },
            "calculation": {
                "consumption": {"P1": {"base_sen": 1500, "adjustments_sen": 0, "total_sen": 1500}}
            },
            "participants": [{"id": "P1", "name": "Alice", "is_organizer": True}],
            "claims": [{"item_id": "rice", "participant_id": "P1", "quantity": 1}],
        }
        blocks = format_compact_meal_blocks("meal-comp", snapshot)
        tables = [b for b in blocks if b.get("type") == "table"]
        items_table = tables[1]
        rows = items_table["table"]["children"]
        # Row 0: header, Row 1: Chicken Rice, Row 2: Warm Water
        water_row = rows[2]
        cells = water_row["table_row"]["cells"]
        split_cell_text = cells[4][0]["text"]["content"]
        self.assertEqual(split_cell_text, "Complimentary")

    def test_table_rows_have_block_object_structure(self):
        """Verify that all table_row children generated for tables (including rollups) have object='block'."""
        snapshot_small = {
            "finalized": True,
            "revision": 1,
            "receipt": {
                "merchant": "Test",
                "subtotal_sen": 2000,
                "total_sen": 2000,
                "items": [{"id": "i1", "label": "Dish", "quantity": 1, "line_sen": 2000}],
                "adjustments": [],
            },
            "calculation": {
                "consumption": {"P1": {"base_sen": 2000, "adjustments_sen": 0, "total_sen": 2000}}
            },
            "participants": [{"id": "P1", "name": "Alice", "is_organizer": True}],
            "claims": {},
        }
        snapshot_large = {
            "finalized": True,
            "revision": 2,
            "receipt": {
                "merchant": "Large Banquet",
                "subtotal_sen": 50000,
                "total_sen": 50000,
                "items": [{"id": f"it_{i}", "label": f"Dish {i}", "quantity": 1, "line_sen": 1000} for i in range(1, 31)],
                "adjustments": [],
            },
            "calculation": {
                "consumption": {f"P{i}": {"base_sen": 2000, "adjustments_sen": 0, "total_sen": 2000} for i in range(1, 26)}
            },
            "participants": [{"id": f"P{i}", "name": f"Diner {i}", "is_organizer": (i == 1)} for i in range(1, 26)],
            "claims": {},
        }
        for snap in (snapshot_small, snapshot_large):
            for fn in (format_compact_meal_blocks, format_full_meal_blocks):
                blocks = fn("meal-test", snap)
                for b in blocks:
                    if b.get("type") == "table":
                        tbl = b.get("table", {})
                        rows = tbl.get("children", [])
                        self.assertTrue(len(rows) > 0)
                        for r in rows:
                            self.assertEqual(r.get("object"), "block")
                            self.assertEqual(r.get("type"), "table_row")
                            self.assertIn("cells", r.get("table_row", {}))

    def test_mock_notion_client_enforces_table_row_block_object(self):
        """Verify that MockNotionClient rejects table_row missing object='block'."""
        cli = MockNotionClient()
        valid_row = {
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": [text_cell("A"), text_cell("B")]},
        }
        invalid_row = {
            "type": "table_row",
            "table_row": {"cells": [text_cell("A"), text_cell("B")]},
        }
        table_block = {
            "object": "block",
            "type": "table",
            "table": {"table_width": 2, "children": [invalid_row]},
        }
        parent = {"page_id": "11111111-2222-3333-4444-555555555555"}
        properties = {"title": {"title": [{"type": "text", "text": {"content": "Test"}}]}}
        with self.assertRaises(NotionValidationError) as ctx:
            cli.create_page("token", parent, properties, [table_block])
        self.assertIn("object='block'", str(ctx.exception))

        # With valid_row it succeeds
        table_block["table"]["children"] = [valid_row]
        res = cli.create_page("token", parent, properties, [table_block])
        self.assertIsNotNone(res.get("id"))


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

    def test_async_export_records_granular_page_not_found_and_validation(self):
        """Verify that async background export records page_not_found and validation_error."""
        authority = Authority(self.db_path)
        try:
            from settletable.notion import NotionNotFoundError
            # Force NotionNotFoundError
            self.mock_client._forced_error = (NotionNotFoundError, "Could not find block with ID: 11111111-2222-3333-4444-555555555555")
            headers = {
                "Authorization": f"Bearer {self.org_cred}",
                "X-SettleTable-Action": "1",
            }
            body = {
                "parent_id": "11111111-2222-3333-4444-555555555555",
                "token": "secret_12345678901234567890",
            }
            code, _, _ = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
            self.assertEqual(code, 202)

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
            self.assertIn("page_not_found", status_data["export"]["export_digest"])
            self.assertIn("Could not find block", status_data["export"]["export_digest"])
        finally:
            authority.close()

    def test_async_export_records_granular_validation_error(self):
        """Verify that async background export records validation_error when Notion rejects payload schema."""
        authority = Authority(self.db_path)
        try:
            from settletable.notion import NotionValidationError
            # Force NotionValidationError
            self.mock_client._forced_error = (NotionValidationError, "body.children[0].object should be defined")
            headers = {
                "Authorization": f"Bearer {self.org_cred}",
                "X-SettleTable-Action": "1",
            }
            body = {
                "parent_id": "11111111-2222-3333-4444-555555555555",
                "token": "secret_12345678901234567890",
            }
            code, _, _ = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
            self.assertEqual(code, 202)

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
            self.assertIn("validation_error", status_data["export"]["export_digest"])
            self.assertIn("body.children", status_data["export"]["export_digest"])
        finally:
            authority.close()

    def test_export_with_notion_url_and_mock_token_default(self):
        """Verify that passing a full Notion page URL and omitting token in mock mode succeeds."""
        headers = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        share_url = "https://app.notion.com/p/SYNTHETIC-Meal-001-" + "3fb0ffe172a6815eb59def81c6e8eb4d?source=copy_link"
        body = {
            "parent_id": share_url,
            # token omitted to test mock notion mode defaulting
        }
        code, _, res_body = self._call("POST", "/api/meals/meal-notion-test/export/notion?sync=1", headers, body)
        self.assertEqual(code, 200)
        data = json.loads(res_body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("export", {}).get("ok"))
        # Verify page created under parent with normalized UUID
        created_pages = list(self.mock_client.pages.values())
        self.assertTrue(any(p.get("parent", {}).get("page_id") == "3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d" for p in created_pages))

    def test_organizer_managed_meal_notion_export_without_diner_sessions(self):
        """Verify organizer can allocate entire meal to diners who never log in and export to Notion."""
        auth = Authority(self.db_path)
        try:
            boot = auth.bootstrap("meal-managed-notion", (
                Participant("alice", "Alice", True),
                Participant("bob", "Bob", False),
                Participant("charlie", "Charlie", False),
            ))
            alice_cred = boot.sessions[0].credential

            rcpt = Receipt(
                items=(
                    ReceiptItem("dish1", "Rendang Beef", 2, 3600),
                    ReceiptItem("dish2", "Nasi Lemak", 1, 1400),
                ),
                subtotal_sen=5000,
                total_sen=5000,
            )
            auth.apply(alice_cred, "meal-managed-notion", ReplaceReceipt("r1", 0, 0, rcpt))

            # Alice allocates to Bob and Charlie using AssignParticipantQuantity
            # Bob and Charlie never receive or redeem invitations!
            auth.apply(alice_cred, "meal-managed-notion", AssignParticipantQuantity("a1", "bob", "dish1", 2, 1, 1))
            auth.apply(alice_cred, "meal-managed-notion", AssignParticipantQuantity("a2", "charlie", "dish2", 1, 1, 1))

            snap = auth.snapshot(alice_cred, "meal-managed-notion")
            self.assertEqual(snap.issues, ())
            self.assertEqual(len(snap.claims), 2)
            # Revoke/expire any diner bootstrap sessions to simulate diners never joining or logging in
            auth._db.execute("UPDATE sessions SET revoked=1 WHERE meal_id='meal-managed-notion' AND participant_id IN ('bob', 'charlie')")
            active_diner_sessions = auth._db.execute("SELECT COUNT(*) FROM sessions WHERE meal_id='meal-managed-notion' AND participant_id IN ('bob', 'charlie') AND revoked=0").fetchone()[0]
            self.assertEqual(active_diner_sessions, 0)

            auth.apply(alice_cred, "meal-managed-notion", ReviewReceipt("rev1", 3, 1, snap.receipt_digest))
            fin = auth.apply(alice_cred, "meal-managed-notion", Finalize("fin1", 4, 1))
            self.assertTrue(fin.calculation is not None)

            # Export to Notion via Transport API
            headers = {
                "Authorization": f"Bearer {alice_cred}",
                "X-SettleTable-Action": "1",
            }
            body = {
                "parent_id": "3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d",
            }
            code, _, res_body = self._call("POST", "/api/meals/meal-managed-notion/export/notion?sync=1", headers, body)
            self.assertEqual(code, 200)
            data = json.loads(res_body.decode("utf-8"))
            self.assertTrue(data.get("ok"))
            self.assertTrue(data.get("export", {}).get("ok"))
        finally:
            auth.close()

    def test_set_notion_public_url_organizer_and_diner_restrictions(self):
        """Verify organizer can set/clear view-only Notion public URL, while diners and invalid formats are rejected."""
        # 1. Export meal first so an export record exists
        headers_org = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        body_export = {"parent_id": "11111111-2222-3333-4444-555555555555", "token": "secret_12345678901234567890"}
        code, _, _ = self._call("POST", "/api/meals/meal-notion-test/export/notion?sync=1", headers_org, body_export)
        self.assertEqual(code, 200)

        # 2. Diner attempting to set public URL via transport returns 403
        headers_diner = {
            "Authorization": f"Bearer {self.diner_cred}",
            "X-SettleTable-Action": "1",
        }
        code_diner, _, res_diner = self._call(
            "POST",
            "/api/meals/meal-notion-test/export/notion/public-url",
            headers_diner,
            {"public_url": "https://notion.site/shared-page"},
        )
        self.assertEqual(code_diner, 403)
        data_diner = json.loads(res_diner.decode("utf-8"))
        self.assertEqual(data_diner["error"], "forbidden")

        # 3. Diner attempting at authority level raises forbidden
        auth = Authority(str(self.db_path))
        try:
            with self.assertRaises(AuthorityError) as ctx:
                auth.set_notion_public_url(self.diner_cred, "meal-notion-test", "https://notion.site/shared-page")
            self.assertEqual(ctx.exception.code, "forbidden")
        finally:
            auth.close()

        # 4. Invalid URLs rejected with 400
        invalid_urls = [
            "http://subdomain.notion.site/unencrypted",  # unencrypted http
            "javascript:alert(1)",  # XSS scheme
            "https://evil.phishing-site.com/fake",  # unauthorized domain
            "https://notion.site.evil.com/fake",  # prefix domain bypass attempt
            "https://notion.site/" + "a" * 520,  # exceeds 512 chars
        ]
        for bad_url in invalid_urls:
            code_bad, _, res_bad = self._call(
                "POST",
                "/api/meals/meal-notion-test/export/notion/public-url",
                headers_org,
                {"public_url": bad_url},
            )
            self.assertEqual(code_bad, 400, f"Expected 400 for bad URL: {bad_url}")
            data_bad = json.loads(res_bad.decode("utf-8"))
            self.assertEqual(data_bad["error"], "invalid_input")

        # 5. Valid notion.site and notion.so URLs accepted
        valid_urls = [
            "https://table-123.notion.site/Dinner-Report-xyz",
            "https://notion.so/my-org/Dinner-Report-xyz",
            "https://www.notion.so/my-org/Dinner-Report-xyz",
        ]
        for good_url in valid_urls:
            code_good, _, res_good = self._call(
                "POST",
                "/api/meals/meal-notion-test/export/notion/public-url",
                headers_org,
                {"public_url": good_url},
            )
            self.assertEqual(code_good, 200, f"Expected 200 for good URL: {good_url}")
            data_good = json.loads(res_good.decode("utf-8"))
            self.assertTrue(data_good["ok"])
            self.assertEqual(data_good["public_url"], good_url)

        # 6. Clearing the public URL via empty string or None
        code_clear, _, res_clear = self._call(
            "POST",
            "/api/meals/meal-notion-test/export/notion/public-url",
            headers_org,
            {"public_url": ""},
        )
        self.assertEqual(code_clear, 200)
        data_clear = json.loads(res_clear.decode("utf-8"))
        self.assertTrue(data_clear["ok"])
        self.assertIsNone(data_clear["public_url"])

    def test_diner_export_status_sanitization_and_privacy(self):
        """Verify diners can check Notion status and see public_url, but never receive private page_id or page_url."""
        headers_org = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        headers_diner = {
            "Authorization": f"Bearer {self.diner_cred}",
        }

        # 1. Before export: both get not_started export
        code_before, _, res_before = self._call("GET", "/api/meals/meal-notion-test/export/notion", headers_diner)
        self.assertEqual(code_before, 200)
        self.assertEqual(json.loads(res_before.decode("utf-8"))["export"], {"status": "not_started"})

        # 2. Export meal as organizer
        body_export = {"parent_id": "11111111-2222-3333-4444-555555555555", "token": "secret_12345678901234567890"}
        code, _, _ = self._call("POST", "/api/meals/meal-notion-test/export/notion?sync=1", headers_org, body_export)
        self.assertEqual(code, 200)

        # 3. Set a published public URL as organizer
        pub_link = "https://settletable.notion.site/dinner-share-link"
        self._call("POST", "/api/meals/meal-notion-test/export/notion/public-url", headers_org, {"public_url": pub_link})

        # 4. Organizer GET export receives full internal record
        code_org_get, _, res_org_get = self._call("GET", "/api/meals/meal-notion-test/export/notion", headers_org)
        self.assertEqual(code_org_get, 200)
        org_data = json.loads(res_org_get.decode("utf-8"))["export"]
        self.assertEqual(org_data["status"], "completed")
        self.assertTrue(org_data["page_id"])
        self.assertTrue(org_data["page_url"])
        self.assertEqual(org_data["public_url"], pub_link)

        # 5. Diner GET export receives strictly sanitized record
        code_diner_get, _, res_diner_get = self._call("GET", "/api/meals/meal-notion-test/export/notion", headers_diner)
        self.assertEqual(code_diner_get, 200)
        diner_data = json.loads(res_diner_get.decode("utf-8"))["export"]
        self.assertEqual(diner_data["status"], "completed")
        self.assertEqual(diner_data["public_url"], pub_link)

        # Zero leakage of private fields
        for private_key in ("page_id", "page_url", "parent_id", "token", "export_digest", "exported_at", "finalized_revision"):
            self.assertNotIn(private_key, diner_data, f"Private key '{private_key}' must NOT be leaked to diner!")

    def test_snapshot_includes_notion_export_fields(self):
        """Verify snapshot includes notion_export_status and notion_public_url for both organizer and diner."""
        headers_org = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        # Sync export and set public link
        body_export = {"parent_id": "11111111-2222-3333-4444-555555555555", "token": "secret_12345678901234567890"}
        self._call("POST", "/api/meals/meal-notion-test/export/notion?sync=1", headers_org, body_export)
        pub_link = "https://settletable.notion.site/dinner-share-snapshot-test"
        self._call("POST", "/api/meals/meal-notion-test/export/notion/public-url", headers_org, {"public_url": pub_link})

        auth = Authority(str(self.db_path))
        try:
            org_snap = auth.snapshot(self.org_cred, "meal-notion-test")
            diner_snap = auth.snapshot(self.diner_cred, "meal-notion-test")

            self.assertEqual(org_snap.notion_export_status, "completed")
            self.assertEqual(org_snap.notion_public_url, pub_link)

            self.assertEqual(diner_snap.notion_export_status, "completed")
            self.assertEqual(diner_snap.notion_public_url, pub_link)
        finally:
            auth.close()

    def test_in_progress_export_75s_timeout(self):
        """Verify in_progress exports time out and transition to failed after 75 seconds."""
        auth = Authority(str(self.db_path))
        try:
            snap = auth.snapshot(self.org_cred, "meal-notion-test")
            fin_rev = snap.finalized_revision or snap.revision

            # Record in-progress export started 30 seconds ago (< 75s)
            now = time.time()
            auth._db.execute(
                "INSERT OR REPLACE INTO notion_exports (meal_id, finalized_revision, page_id, page_url, exported_at, export_digest, status) "
                "VALUES (?, ?, '', '', ?, 'pending', 'in_progress')",
                ("meal-notion-test", fin_rev, now - 30.0),
            )
            auth._db.commit()

            rec = auth.get_notion_export("meal-notion-test", fin_rev)
            self.assertIsNotNone(rec)
            self.assertEqual(rec["status"], "in_progress")

            # Update exported_at to 76 seconds ago (> 75s)
            auth._db.execute(
                "UPDATE notion_exports SET exported_at = ? WHERE meal_id = ? AND finalized_revision = ?",
                (now - 76.0, "meal-notion-test", fin_rev),
            )
            auth._db.commit()

            rec_timeout = auth.get_notion_export("meal-notion-test", fin_rev)
            self.assertIsNotNone(rec_timeout)
            self.assertEqual(rec_timeout["status"], "failed")
            self.assertEqual(rec_timeout["export_digest"], "timeout")
        finally:
            auth.close()

    def test_record_notion_export_failed_does_not_overwrite_completed_status(self):
        """Verify that record_notion_export_failed and record_notion_export_in_progress do not overwrite completed exports."""
        auth = Authority(str(self.db_path))
        try:
            snap = auth.snapshot(self.org_cred, "meal-notion-test")
            fin_rev = snap.finalized_revision or snap.revision

            # Record initial completed export
            auth.record_notion_export_completed(
                "meal-notion-test", fin_rev, "page-completed-123", "https://notion.so/page-completed-123", "digest-abc"
            )
            rec = auth.get_notion_export("meal-notion-test", fin_rev)
            self.assertEqual(rec["status"], "completed")
            self.assertEqual(rec["page_id"], "page-completed-123")
            self.assertEqual(rec["page_url"], "https://notion.so/page-completed-123")

            # Lagging failure attempt arrives (e.g. from an overlapping timed-out worker)
            auth.record_notion_export_failed("meal-notion-test", fin_rev, "lagging_worker_timeout")

            rec_after_failed = auth.get_notion_export("meal-notion-test", fin_rev)
            self.assertEqual(rec_after_failed["status"], "completed")
            self.assertEqual(rec_after_failed["page_id"], "page-completed-123")
            self.assertEqual(rec_after_failed["page_url"], "https://notion.so/page-completed-123")

            # In-progress attempt with the same digest also cannot downgrade completed status
            auth.record_notion_export_in_progress("meal-notion-test", fin_rev, "digest-abc")
            rec_after_inprogress = auth.get_notion_export("meal-notion-test", fin_rev)
            self.assertEqual(rec_after_inprogress["status"], "completed")
            self.assertEqual(rec_after_inprogress["page_id"], "page-completed-123")
        finally:
            auth.close()

    def test_overlapping_async_export_requests_reuse_active_thread_and_prevent_duplicates(self):
        """Verify that concurrent or retry export calls while a worker is alive reuse the active thread without duplicate Notion page creations."""
        import threading

        # Wrap mock client to delay create_page until an event is set
        gate = threading.Event()
        original_client = self.app.notion_client
        create_page_calls = []

        class DelayedMockClient:
            def __init__(self, inner):
                self._inner = inner
            def create_page(self, *args, **kwargs):
                create_page_calls.append(args)
                gate.wait(timeout=5.0)
                return self._inner.create_page(*args, **kwargs)
            def __getattr__(self, name):
                return getattr(self._inner, name)

        delayed_client = DelayedMockClient(original_client)
        self.app.notion_client = delayed_client

        headers = {
            "Authorization": f"Bearer {self.org_cred}",
            "X-SettleTable-Action": "1",
        }
        body = {
            "parent_id": "11111111-2222-3333-4444-555555555555",
            "token": "secret_12345678901234567890",
        }

        try:
            # First request: starts background worker
            code1, _, res1 = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
            self.assertEqual(code1, 202)
            data1 = json.loads(res1.decode("utf-8"))
            self.assertEqual(data1["export"]["status"], "in_progress")

            # Wait briefly for worker thread to enter create_page
            for _ in range(50):
                if len(create_page_calls) > 0:
                    break
                time.sleep(0.02)
            self.assertEqual(len(create_page_calls), 1)

            # Second request arrives while worker 1 is still in-flight
            code2, _, res2 = self._call("POST", "/api/meals/meal-notion-test/export/notion", headers, body)
            self.assertEqual(code2, 202)
            data2 = json.loads(res2.decode("utf-8"))
            self.assertEqual(data2["export"]["status"], "in_progress")

            # Verify that create_page was NOT called a second time
            self.assertEqual(len(create_page_calls), 1)

            # Unblock the gate so worker completes
            gate.set()

            # Poll until completed
            body_p = {}
            for _ in range(100):
                code_p, _, res_p = self._call("GET", "/api/meals/meal-notion-test/export/notion", headers)
                if code_p == 200:
                    body_p = json.loads(res_p.decode("utf-8"))
                    if body_p.get("export", {}).get("status") == "completed":
                        break
                time.sleep(0.03)

            self.assertEqual(body_p.get("export", {}).get("status"), "completed")
            self.assertEqual(len(create_page_calls), 1)
        finally:
            gate.set()
            self.app.notion_client = original_client

    def test_lagging_worker_after_75s_timeout_cannot_overwrite_completed_retry(self):
        """Verify that when a request times out (>75s) and a subsequent retry succeeds, any lagging failure from the original worker cannot clobber the completed state."""
        auth = Authority(str(self.db_path))
        try:
            snap = auth.snapshot(self.org_cred, "meal-notion-test")
            fin_rev = snap.finalized_revision or snap.revision

            # 1. Worker 1 starts at t=0
            now = time.time()
            auth.record_notion_export_in_progress("meal-notion-test", fin_rev, "digest-abc")

            # 2. Worker 1 lags beyond 75s
            auth._db.execute(
                "UPDATE notion_exports SET exported_at = ? WHERE meal_id = ? AND finalized_revision = ?",
                (now - 80.0, "meal-notion-test", fin_rev),
            )
            auth._db.commit()

            # Authority sees timeout failure
            timed_out = auth.get_notion_export("meal-notion-test", fin_rev)
            self.assertEqual(timed_out["status"], "failed")
            self.assertEqual(timed_out["export_digest"], "timeout")

            # 3. Retry happens and succeeds (Worker 2 records completion)
            auth.record_notion_export_completed(
                "meal-notion-test", fin_rev, "page-retry-win", "https://notion.so/page-retry-win", "digest-abc"
            )
            completed_rec = auth.get_notion_export("meal-notion-test", fin_rev)
            self.assertEqual(completed_rec["status"], "completed")
            self.assertEqual(completed_rec["page_id"], "page-retry-win")

            # 4. Lagging Worker 1 finally errors out at t=85 and attempts to record failure
            auth.record_notion_export_failed("meal-notion-test", fin_rev, "http_read_timeout_504")

            # 5. Completed status and URL MUST remain intact
            final_rec = auth.get_notion_export("meal-notion-test", fin_rev)
            self.assertEqual(final_rec["status"], "completed")
            self.assertEqual(final_rec["page_id"], "page-retry-win")
            self.assertEqual(final_rec["page_url"], "https://notion.so/page-retry-win")
        finally:
            auth.close()




if __name__ == "__main__":
    unittest.main()
