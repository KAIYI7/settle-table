import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
from fractions import Fraction

from settletable.authority import (
    Authority,
    AuthorityError,
    Participant,
    Receipt,
    ReceiptItem,
    ReceiptAdjustment,
    ReplaceReceipt,
    ReviewReceipt,
    SetOwnQuantity,
    AssignParticipantQuantity,
    SetItemAllocations,
    Finalize,
    RecordContribution,
    ReverseContribution,
    RecordTransfer,
    ReverseTransfer,
    RevokeInvitation,
)
from settletable.notion.client import MockNotionClient
from settletable.transport import SettleTableApp


class SyntheticPostFinalizationUAT(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "uat.sqlite")
        self.storage_dir = os.path.join(self.temp_dir.name, "storage")
        os.makedirs(self.storage_dir, exist_ok=True)
        self.mock_notion = MockNotionClient()
        self.app = SettleTableApp(
            db_path=self.db_path,
            storage_dir=self.storage_dir,
            allow_sync_export=True,
            notion_client=self.mock_notion,
        )

    def tearDown(self):
        self.app.close()
        self.temp_dir.cleanup()

    def _call(self, method, path, headers=None, body=None):
        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
            "HTTP_HOST": "localhost:8000",
            "HTTP_ORIGIN": "http://localhost:8000",
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(),
        }
        hdrs = headers or {}
        for k, v in hdrs.items():
            key = "HTTP_" + k.upper().replace("-", "_")
            if k.lower() == "content-type":
                key = "CONTENT_TYPE"
            elif k.lower() == "content-length":
                key = "CONTENT_LENGTH"
            env[key] = str(v)

        if body is not None:
            if isinstance(body, (dict, list)):
                raw = json.dumps(body).encode("utf-8")
                env["CONTENT_TYPE"] = "application/json"
            elif isinstance(body, bytes):
                raw = body
            else:
                raw = str(body).encode("utf-8")
            env["CONTENT_LENGTH"] = str(len(raw))
            env["wsgi.input"] = io.BytesIO(raw)

        response_status = None
        response_headers = []

        def start_response(status, headers, exc_info=None):
            nonlocal response_status, response_headers
            response_status = status
            response_headers = headers

        res_iter = self.app(env, start_response)
        res_body = b"".join(res_iter)
        code = int(response_status.split()[0])
        return code, response_headers, res_body

    def test_historical_schema_migration_preserves_records(self):
        """Verify that an older database without public_url or share_with_diners upgrades cleanly and retains all records."""
        legacy_db = os.path.join(self.temp_dir.name, "legacy.sqlite")
        con = sqlite3.connect(legacy_db)

        # 1. Create older schema without public_url in notion_exports and without share_with_diners in receipt_photos
        con.executescript("""
            CREATE TABLE meals (
                id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE meal_log (
                meal_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                actor_participant_id TEXT,
                command_kind TEXT NOT NULL,
                command_data TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (meal_id, revision)
            );
            CREATE TABLE participants (
                meal_id TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                joined_at REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (meal_id, participant_id)
            );
            CREATE TABLE credentials (
                secret_hash TEXT PRIMARY KEY,
                meal_id TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                is_organizer INTEGER NOT NULL,
                created_at REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE receipt_photos (
                meal_id TEXT PRIMARY KEY,
                image_bytes BLOB NOT NULL,
                content_type TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                created_at REAL NOT NULL,
                storage_path TEXT,
                sha256 TEXT
            );
            CREATE TABLE notion_exports (
                meal_id TEXT NOT NULL,
                finalized_revision INTEGER NOT NULL,
                page_id TEXT,
                page_url TEXT,
                exported_at REAL,
                export_digest TEXT,
                status TEXT,
                PRIMARY KEY (meal_id, finalized_revision)
            );
        """)

        # Insert synthetic legacy records
        sample_state = json.dumps({
            "meal_id": "meal-legacy-1",
            "name": "Legacy Meal",
            "revision": 3,
            "finalized": True,
            "finalized_revision": 3,
            "calculation": {
                "per_participant": {
                    "alice": {"subtotal_sen": 1000, "total_sen": 1100},
                },
                "total_sen": 1100,
            },
            "calculation_digest": "legacy-calc-digest-001",
        })
        con.execute(
            "INSERT INTO meals (id, revision, state, created_at, updated_at, archived) VALUES (?, ?, ?, ?, ?, ?)",
            ("meal-legacy-1", 3, sample_state, 1000.0, 1000.0, 0),
        )
        dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        con.execute(
            "INSERT INTO receipt_photos (meal_id, image_bytes, content_type, width, height, created_at, sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("meal-legacy-1", dummy_png, "image/png", 1, 1, 1000.0, "fake-sha"),
        )
        con.execute(
            "INSERT INTO notion_exports (meal_id, finalized_revision, page_id, page_url, exported_at, export_digest, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("meal-legacy-1", 3, "legacy-page-999", "https://notion.so/legacy-page-999", 1000.0, "legacy-digest", "completed"),
        )
        con.commit()
        con.close()

        # 2. Open with current Authority
        auth = Authority(legacy_db, storage_dir=self.storage_dir)
        try:
            # Verify columns were added automatically
            columns_notion = [r[1] for r in auth._db.execute("PRAGMA table_info(notion_exports)").fetchall()]
            self.assertIn("public_url", columns_notion)

            columns_photo = [r[1] for r in auth._db.execute("PRAGMA table_info(receipt_photos)").fetchall()]
            self.assertIn("share_with_diners", columns_photo)

            # Verify existing records remain intact
            exp = auth.get_notion_export("meal-legacy-1", 3)
            self.assertIsNotNone(exp)
            self.assertEqual(exp["status"], "completed")
            self.assertEqual(exp["page_id"], "legacy-page-999")
            self.assertEqual(exp["page_url"], "https://notion.so/legacy-page-999")
            self.assertIsNone(exp["public_url"])

            # Verify receipt photo is intact and share_with_diners defaulted to 0
            row = auth._db.execute("SELECT width, height, share_with_diners FROM receipt_photos WHERE meal_id=?", ("meal-legacy-1",)).fetchone()
            self.assertEqual(row[0], 1)
            self.assertEqual(row[1], 1)
            self.assertEqual(row[2], 0)
        finally:
            auth.close()

    def test_comprehensive_synthetic_post_finalization_uat(self):
        """Execute full synthetic UAT verifying receipt sharing, diner math balances, unauthorized commands, and notion privacy."""
        auth = self.app.get_authority()

        # 1. Setup Meal & Participants
        meal_id = "meal-uat-101"
        participants = (
            Participant("alice", "Alice", organizer=True),
            Participant("bob", "Bob", organizer=False),
            Participant("charlie", "Charlie", organizer=False),
        )
        boot = auth.bootstrap(meal_id, participants)
        creds = {g.participant_id: g.credential for g in boot.sessions}
        org_cred = creds["alice"]
        bob_cred = creds["bob"]
        charlie_cred = creds["charlie"]
        org_session = org_cred
        bob_session = bob_cred
        charlie_session = charlie_cred
        alice_id = "alice"
        bob_id = "bob"
        charlie_id = "charlie"

        # Setup distinct receipt items:
        # Burger: $10.00 (1000 sen)
        # Pizza:  $20.00 (2000 sen)
        # Salad:   $5.00  (500 sen)
        # Tax:    10% = 350 sen
        # Subtotal: 3500 sen, Total: 3850 sen
        items = (
            ReceiptItem("item-burger", "Burger", Fraction(1), 1000),
            ReceiptItem("item-pizza", "Pizza", Fraction(1), 2000),
            ReceiptItem("item-salad", "Salad", Fraction(1), 500),
        )
        tax = ReceiptAdjustment("adj-tax", "Tax", "tax", 350, ("item-burger", "item-pizza", "item-salad"), "10% tax", "all_items")
        receipt = Receipt(items, 3500, 3850, (tax,), 0)

        # Apply receipt
        auth.apply(org_cred, meal_id, ReplaceReceipt("cmd-rcpt", 0, 0, receipt))

        # Assign claims / quantities
        snap = auth.snapshot(org_cred, meal_id)
        rev_burger = next(i.item_revision for i in snap.items if i.item_id == "item-burger")
        rev_pizza = next(i.item_revision for i in snap.items if i.item_id == "item-pizza")
        rev_salad = next(i.item_revision for i in snap.items if i.item_id == "item-salad")

        auth.apply(bob_cred, meal_id, SetOwnQuantity("cmd-bob-q", "item-burger", Fraction(1), rev_burger, snap.financial_revision))
        snap = auth.snapshot(org_cred, meal_id)
        auth.apply(charlie_cred, meal_id, SetOwnQuantity("cmd-charlie-q", "item-pizza", Fraction(1), rev_pizza, snap.financial_revision))
        snap = auth.snapshot(org_cred, meal_id)
        auth.apply(org_cred, meal_id, SetOwnQuantity("cmd-alice-q", "item-salad", Fraction(1), rev_salad, snap.financial_revision))

        # Upload receipt photo before finalization
        dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x06\x00\x00\x00v~{\x9a\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        auth.store_receipt_photo(org_cred, meal_id, dummy_png, "image/png", 2, 2)

        # Review and finalize
        snap = auth.snapshot(org_cred, meal_id)
        auth.apply(org_cred, meal_id, ReviewReceipt("cmd-rev", snap.revision, snap.financial_revision, snap.receipt_digest))
        snap = auth.snapshot(org_cred, meal_id)
        auth.apply(org_cred, meal_id, Finalize("cmd-fin", snap.revision, snap.financial_revision))

        # -------------------------------------------------------------
        # 2. Receipt Sharing Authorization & Privacy Check
        # -------------------------------------------------------------
        # Default: sharing disabled
        code, _, _ = self._call("GET", f"/api/meals/{meal_id}/receipt/photo", headers={"Authorization": f"Bearer {org_session}"})
        self.assertEqual(code, 200)

        # Diners cannot view when disabled
        code_bob, _, _ = self._call("GET", f"/api/meals/{meal_id}/receipt/photo", headers={"Authorization": f"Bearer {bob_session}"})
        self.assertEqual(code_bob, 403)

        code_charlie, _, _ = self._call("GET", f"/api/meals/{meal_id}/receipt/photo", headers={"Authorization": f"Bearer {charlie_session}"})
        self.assertEqual(code_charlie, 403)

        # Unauthenticated blocked
        code_unauth, _, _ = self._call("GET", f"/api/meals/{meal_id}/receipt/photo")
        self.assertEqual(code_unauth, 401)

        # Non-organizer diner cannot change receipt sharing
        code_bob_mod, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/receipt/photo/share",
            headers={"Authorization": f"Bearer {bob_session}", "X-SettleTable-Action": "1"},
            body={"share": True},
        )
        self.assertEqual(code_bob_mod, 403)

        # Organizer enables sharing
        code_share_on, _, res_share_on = self._call(
            "POST",
            f"/api/meals/{meal_id}/receipt/photo/share",
            headers={"Authorization": f"Bearer {org_session}", "X-SettleTable-Action": "1"},
            body={"share": True},
        )
        self.assertEqual(code_share_on, 200)
        self.assertTrue(json.loads(res_share_on.decode("utf-8"))["shared"])

        # Active diners can now view the shared receipt
        code_bob_view, _, body_bob_view = self._call("GET", f"/api/meals/{meal_id}/receipt/photo", headers={"Authorization": f"Bearer {bob_session}"})
        self.assertEqual(code_bob_view, 200)
        self.assertEqual(body_bob_view, dummy_png)

        # Organizer disables sharing
        code_share_off, _, res_share_off = self._call(
            "POST",
            f"/api/meals/{meal_id}/receipt/photo/share",
            headers={"Authorization": f"Bearer {org_session}", "X-SettleTable-Action": "1"},
            body={"share": False},
        )
        self.assertEqual(code_share_off, 200)
        self.assertFalse(json.loads(res_share_off.decode("utf-8"))["shared"])

        # Diner is blocked again
        code_bob_view2, _, _ = self._call("GET", f"/api/meals/{meal_id}/receipt/photo", headers={"Authorization": f"Bearer {bob_session}"})
        self.assertEqual(code_bob_view2, 403)

        # -------------------------------------------------------------
        # 3. Non-Organizer Direct Ledger Mutation Rejection
        # -------------------------------------------------------------
        # Diner Bob cannot record contribution
        snap = auth.snapshot(bob_cred, meal_id)
        with self.assertRaises(AuthorityError) as ctx_c:
            auth.apply(bob_cred, meal_id, RecordContribution("cmd-bad-contrib", snap.revision, bob_id, 1100, "cash"))
        self.assertEqual(ctx_c.exception.code, "forbidden")

        # Diner Bob cannot reverse contribution
        with self.assertRaises(AuthorityError) as ctx_rc:
            auth.apply(bob_cred, meal_id, ReverseContribution("cmd-bad-revc", snap.revision, "contrib-fake", "mistake"))
        self.assertEqual(ctx_rc.exception.code, "forbidden")

        # Diner Bob cannot record transfer
        with self.assertRaises(AuthorityError) as ctx_t:
            auth.apply(bob_cred, meal_id, RecordTransfer("cmd-bad-xfer", snap.revision, bob_id, alice_id, 1100, "promptpay"))
        self.assertEqual(ctx_t.exception.code, "forbidden")

        # Diner Bob cannot reverse transfer
        with self.assertRaises(AuthorityError) as ctx_rt:
            auth.apply(bob_cred, meal_id, ReverseTransfer("cmd-bad-revt", snap.revision, "xfer-fake", "mistake"))
        self.assertEqual(ctx_rt.exception.code, "forbidden")

        # -------------------------------------------------------------
        # 4. Mathematical Balance Accuracy Across Funding States
        # -------------------------------------------------------------
        # State 1: Underfunded (No contributions yet)
        snap_bob1 = auth.snapshot(bob_cred, meal_id)
        # Bob had Burger: 1000 sen. Subtotal was 3500 sen. Tax was 350 sen.
        # Bob's tax portion: 1000/3500 * 350 = 100 sen.
        # Bob's total: 1100 sen ($11.00).
        bob_consumption = next(c.sen for c in snap_bob1.calculation.consumption if c.participant_id == bob_id)
        self.assertEqual(bob_consumption, 1100)
        # Outstanding bill funding across entire meal is 3850 sen (underfunded)
        self.assertEqual(snap_bob1.funding.unfunded_sen, 3850)
        self.assertEqual(snap_bob1.funding.status, "not_funded")

        # State 2: Fully Funded by Organizer Alice
        # Alice records restaurant bill payment of 3850 sen
        snap = auth.snapshot(org_cred, meal_id)
        auth.apply(org_cred, meal_id, RecordContribution("cmd-fund-bill", snap.revision, alice_id, 3850, "card"))
        snap_bob2 = auth.snapshot(bob_cred, meal_id)
        self.assertEqual(snap_bob2.funding.unfunded_sen, 0)
        self.assertEqual(snap_bob2.funding.status, "fully_funded")
        # Bob still owes 1100 sen
        bob_net_2 = next(b.outstanding_net_balance_sen for b in snap_bob2.settlement.outstanding_net_balances if b.participant_id == bob_id)
        self.assertEqual(bob_net_2, -1100)

        # State 3: Bob Settles with Alice
        # Alice records transfer from Bob of 1100 sen
        snap = auth.snapshot(org_cred, meal_id)
        auth.apply(org_cred, meal_id, RecordTransfer("cmd-settle-bob", snap.revision, bob_id, alice_id, 1100, "promptpay"))
        snap_bob3 = auth.snapshot(bob_cred, meal_id)
        bob_net_3 = next(b.outstanding_net_balance_sen for b in snap_bob3.settlement.outstanding_net_balances if b.participant_id == bob_id)
        self.assertEqual(bob_net_3, 0)

        # Charlie still owes 2200 sen (Pizza 2000 + 200 tax)
        charlie_net_3 = next(b.outstanding_net_balance_sen for b in snap_bob3.settlement.outstanding_net_balances if b.participant_id == charlie_id)
        self.assertEqual(charlie_net_3, -2200)

        # -------------------------------------------------------------
        # 5. Notion Export Reliability & URL Privacy
        # -------------------------------------------------------------
        # Organizer exports meal to Notion
        code_exp, _, res_exp = self._call(
            "POST",
            f"/api/meals/{meal_id}/export/notion?sync=1",
            headers={"Authorization": f"Bearer {org_session}", "X-SettleTable-Action": "1"},
            body={"parent_id": "11111111-2222-3333-4444-555555555555", "token": "secret_12345678901234567890"},
        )
        self.assertEqual(code_exp, 200)
        exp_data = json.loads(res_exp.decode("utf-8"))["export"]
        self.assertEqual(exp_data["status"], "completed")
        self.assertTrue(exp_data["page_url"].startswith("https://notion.so/") or exp_data["page_url"].startswith("https://www.notion.so/"))

        # Organizer retrieves report link
        code_org_get, _, res_org_get = self._call("GET", f"/api/meals/{meal_id}/export/notion", headers={"Authorization": f"Bearer {org_session}"})
        self.assertEqual(code_org_get, 200)
        org_rec = json.loads(res_org_get.decode("utf-8"))["export"]
        self.assertEqual(org_rec["status"], "completed")
        self.assertEqual(org_rec["page_id"], exp_data["page_id"])
        self.assertEqual(org_rec["page_url"], exp_data["page_url"])

        # Diner retrieves report status: gets status 'completed', but NO page_id and NO private workspace page_url!
        code_bob_get, _, res_bob_get = self._call("GET", f"/api/meals/{meal_id}/export/notion", headers={"Authorization": f"Bearer {bob_session}"})
        self.assertEqual(code_bob_get, 200)
        bob_rec = json.loads(res_bob_get.decode("utf-8"))["export"]
        self.assertEqual(bob_rec["status"], "completed")
        self.assertNotIn("page_id", bob_rec)
        self.assertNotIn("page_url", bob_rec)
        self.assertIsNone(bob_rec.get("public_url"))

        # Organizer registers view-only public link
        code_set_pub, _, res_set_pub = self._call(
            "POST",
            f"/api/meals/{meal_id}/export/notion/public-url",
            headers={"Authorization": f"Bearer {org_session}", "X-SettleTable-Action": "1"},
            body={"public_url": "https://notion.site/my-shared-dinner-report-123"},
        )
        self.assertEqual(code_set_pub, 200)

        # Diner now sees public_url, still no private page_id or page_url
        code_bob_get2, _, res_bob_get2 = self._call("GET", f"/api/meals/{meal_id}/export/notion", headers={"Authorization": f"Bearer {bob_session}"})
        self.assertEqual(code_bob_get2, 200)
        bob_rec2 = json.loads(res_bob_get2.decode("utf-8"))["export"]
        self.assertEqual(bob_rec2["status"], "completed")
        self.assertEqual(bob_rec2["public_url"], "https://notion.site/my-shared-dinner-report-123")
        self.assertNotIn("page_id", bob_rec2)
        self.assertNotIn("page_url", bob_rec2)

        # Non-organizer cannot modify public_url
        code_bob_set_pub, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/export/notion/public-url",
            headers={"Authorization": f"Bearer {bob_session}", "X-SettleTable-Action": "1"},
            body={"public_url": "https://notion.site/hacked-url"},
        )
        self.assertEqual(code_bob_set_pub, 403)

        # Organizer removes public link
        code_clear_pub, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/export/notion/public-url",
            headers={"Authorization": f"Bearer {org_session}", "X-SettleTable-Action": "1"},
            body={"public_url": ""},
        )
        self.assertEqual(code_clear_pub, 200)

        # Diner no longer sees public_url
        code_bob_get3, _, res_bob_get3 = self._call("GET", f"/api/meals/{meal_id}/export/notion", headers={"Authorization": f"Bearer {bob_session}"})
        self.assertEqual(code_bob_get3, 200)
        bob_rec3 = json.loads(res_bob_get3.decode("utf-8"))["export"]
        self.assertIsNone(bob_rec3.get("public_url"))

        # -------------------------------------------------------------
        # 6. Cross-Meal Session & Authorization Boundary Enforcement
        # -------------------------------------------------------------
        # Create a second meal with David
        boot_cross = auth.bootstrap("meal-cross-2", (Participant("david", "David", organizer=True),))
        david_cred = boot_cross.sessions[0].credential
        david_session = david_cred

        # David from meal 2 cannot access meal 1 receipt photo
        code_david_photo, _, _ = self._call("GET", f"/api/meals/{meal_id}/receipt/photo", headers={"Authorization": f"Bearer {david_session}"})
        self.assertIn(code_david_photo, (401, 403))

        # David cannot toggle meal 1 receipt sharing
        code_david_share, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/receipt/photo/share",
            headers={"Authorization": f"Bearer {david_session}", "X-SettleTable-Action": "1"},
            body={"share": True},
        )
        self.assertIn(code_david_share, (401, 403))

        # David cannot access meal 1 notion export status
        code_david_exp, _, _ = self._call("GET", f"/api/meals/{meal_id}/export/notion", headers={"Authorization": f"Bearer {david_session}"})
        self.assertIn(code_david_exp, (401, 403))

        # David cannot set meal 1 notion public url
        code_david_pub, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/export/notion/public-url",
            headers={"Authorization": f"Bearer {david_session}", "X-SettleTable-Action": "1"},
            body={"public_url": "https://notion.site/david-hijack"},
        )
        self.assertIn(code_david_pub, (401, 403))

    def test_post_finalization_invitations_and_access_lifecycle(self):
        """Verify organizer can issue, revoke, reissue invitations, and review join requests after finalization,
        while diners are forbidden from organizer actions and financial calculations remain immutable."""
        auth = Authority(str(self.db_path))
        try:
            meal_id = "meal-post-fin-inv"
            alice_id, bob_id, charlie_id = "alice", "bob", "charlie"
            participants = (
                Participant(alice_id, "Alice", organizer=True),
                Participant(bob_id, "Bob", organizer=False),
                Participant(charlie_id, "Charlie", organizer=False),
            )
            boot = auth.bootstrap(meal_id, participants)
            org_cred = boot.sessions[0].credential
            org_headers = {"Authorization": f"Bearer {org_cred}", "X-SettleTable-Action": "1"}

            # 1. Setup receipt and finalize meal
            items = (
                ReceiptItem("item-1", "Steak", Fraction(1), 5000),
                ReceiptItem("item-2", "Salad", Fraction(1), 2000),
            )
            rcpt = Receipt(items=items, subtotal_sen=7000, total_sen=7000, adjustments=(), included_tax_sen=0)
            auth.apply(org_cred, meal_id, ReplaceReceipt("cmd-rcpt", 0, 0, rcpt))
            snap = auth.snapshot(org_cred, meal_id)
            rev1 = next(i.item_revision for i in snap.items if i.item_id == "item-1")
            rev2 = next(i.item_revision for i in snap.items if i.item_id == "item-2")
            auth.apply(org_cred, meal_id, AssignParticipantQuantity("cmd-q1", bob_id, "item-1", Fraction(1), rev1, snap.financial_revision))
            snap = auth.snapshot(org_cred, meal_id)
            auth.apply(org_cred, meal_id, AssignParticipantQuantity("cmd-q2", charlie_id, "item-2", Fraction(1), rev2, snap.financial_revision))
            snap = auth.snapshot(org_cred, meal_id)
            auth.apply(org_cred, meal_id, ReviewReceipt("cmd-rev", snap.revision, snap.financial_revision, snap.receipt_digest))
            snap = auth.snapshot(org_cred, meal_id)
            auth.apply(org_cred, meal_id, Finalize("cmd-fin", snap.revision, snap.financial_revision))

            # Capture baseline calculation state for invariance assertions
            fin_snap_baseline = auth.snapshot(org_cred, meal_id)
            self.assertTrue(fin_snap_baseline.finalized)
            self.assertIsNotNone(fin_snap_baseline.calculation)
            baseline_calc_dict = json.dumps([{"p": c.participant_id, "sen": c.sen} for c in fin_snap_baseline.calculation.consumption], sort_keys=True)
            baseline_total_sen = fin_snap_baseline.receipt.total_sen
            baseline_fin_rev = fin_snap_baseline.financial_revision
        finally:
            auth.close()

        # 2. Organizer issues invitation for Bob on finalized meal
        code_inv_bob, _, res_inv_bob = self._call(
            "POST",
            f"/api/meals/{meal_id}/invitations",
            headers=org_headers,
            body={"participant_id": bob_id, "invite_ttl": 86400},
        )
        self.assertEqual(code_inv_bob, 201)
        bob_inv_data = json.loads(res_inv_bob.decode("utf-8"))
        self.assertTrue(bob_inv_data["ok"])
        bob_token = bob_inv_data["token"]
        self.assertTrue(bool(bob_token))

        # 3. Bob redeems invitation and accesses finalized calculation
        code_redeem_bob, hdrs_redeem_bob, res_redeem_bob = self._call(
            "POST",
            f"/api/meals/{meal_id}/invitations/redeem",
            headers={"Content-Type": "application/json", "X-SettleTable-Action": "1"},
            body={"invitation_token": bob_token},
        )
        self.assertEqual(code_redeem_bob, 200)
        bob_inv_res = json.loads(res_redeem_bob.decode("utf-8"))
        self.assertEqual(bob_inv_res["participant_id"], bob_id)
        bob_cred = None
        for k, v in hdrs_redeem_bob:
            if k.lower() == "set-cookie" and "settletable_session=" in v:
                bob_cred = v.split("settletable_session=")[1].split(";")[0]
        self.assertIsNotNone(bob_cred)
        bob_headers = {"Authorization": f"Bearer {bob_cred}", "X-SettleTable-Action": "1"}

        # Bob verifies finalized calculation
        code_snap_bob, _, res_snap_bob = self._call("GET", f"/api/meals/{meal_id}/snapshot", headers=bob_headers)
        self.assertEqual(code_snap_bob, 200)
        bob_snap = json.loads(res_snap_bob.decode("utf-8"))
        self.assertTrue(bob_snap["finalized"])
        self.assertFalse(bob_snap["is_organizer"])
        bob_consumption = next(c["sen"] for c in bob_snap["calculation"]["consumption"] if c["participant_id"] == bob_id)
        self.assertEqual(bob_consumption, 5000)

        # 4. Organizer issues invitation for Charlie, then revokes and reissues it
        code_inv_c1, _, res_inv_c1 = self._call(
            "POST",
            f"/api/meals/{meal_id}/invitations",
            headers=org_headers,
            body={"participant_id": charlie_id, "invite_ttl": 86400},
        )
        self.assertEqual(code_inv_c1, 201)
        c1_token = json.loads(res_inv_c1.decode("utf-8"))["token"]

        # Duplicate active invitation attempt rejected with 409
        code_inv_dup, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/invitations",
            headers=org_headers,
            body={"participant_id": charlie_id},
        )
        self.assertEqual(code_inv_dup, 409)

        # Organizer revokes Charlie's lost invitation
        code_snap_cur, _, res_snap_cur = self._call("GET", f"/api/meals/{meal_id}/snapshot", headers=org_headers)
        current_rev = json.loads(res_snap_cur.decode("utf-8"))["revision"]
        code_rev_c, _, res_rev_c = self._call(
            "POST",
            f"/api/meals/{meal_id}/apply",
            headers=org_headers,
            body={
                "command_id": "rev-charlie-lost",
                "kind": "RevokeInvitation",
                "participant_id": charlie_id,
                "expected_revision": current_rev,
            },
        )
        self.assertEqual(code_rev_c, 200)

        # Charlie cannot redeem the revoked invitation
        code_c1_redeem, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/invitations/redeem",
            headers={"Content-Type": "application/json", "X-SettleTable-Action": "1"},
            body={"invitation_token": c1_token},
        )
        self.assertIn(code_c1_redeem, (400, 403, 409))

        # Organizer reissues Charlie's invitation successfully
        code_inv_c2, _, res_inv_c2 = self._call(
            "POST",
            f"/api/meals/{meal_id}/invitations",
            headers=org_headers,
            body={"participant_id": charlie_id, "invite_ttl": 86400},
        )
        self.assertEqual(code_inv_c2, 201)
        c2_token = json.loads(res_inv_c2.decode("utf-8"))["token"]

        # 5. Join request flow on finalized meal
        code_join_req, _, res_join_req = self._call(
            "POST",
            f"/api/meals/{meal_id}/join-requests",
            headers={"Content-Type": "application/json", "X-SettleTable-Action": "1"},
            body={"display_name": "Charlie"},
        )
        self.assertEqual(code_join_req, 201)
        join_req_id = json.loads(res_join_req.decode("utf-8"))["request_id"]

        # Organizer approves join request on finalized meal
        code_review_req, _, res_review_req = self._call(
            "POST",
            f"/api/meals/{meal_id}/join-requests/{join_req_id}/review",
            headers=org_headers,
            body={"action": "approve"},
        )
        self.assertEqual(code_review_req, 200)
        self.assertEqual(json.loads(res_review_req.decode("utf-8"))["status"], "approved")

        # 6. Diner authorization boundary enforcement on finalized meal
        # Bob cannot issue invitations
        code_bad_inv, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/invitations",
            headers=bob_headers,
            body={"participant_id": charlie_id},
        )
        self.assertEqual(code_bad_inv, 403)

        # Bob cannot revoke invitations
        code_bad_rev, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/apply",
            headers=bob_headers,
            body={
                "command_id": "bad-rev",
                "kind": "RevokeInvitation",
                "participant_id": charlie_id,
                "expected_revision": current_rev,
            },
        )
        self.assertEqual(code_bad_rev, 403)

        # Bob cannot review join requests
        code_bad_req, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/join-requests/{join_req_id}/review",
            headers=bob_headers,
            body={"action": "reject"},
        )
        self.assertEqual(code_bad_req, 403)

        # Bob cannot generate emergency organizer recovery links
        code_bad_claim, _, _ = self._call(
            "POST",
            f"/api/meals/{meal_id}/organizer-claims",
            headers=bob_headers,
            body={},
        )
        self.assertEqual(code_bad_claim, 403)

        # 7. Strict mathematical & financial invariance verification
        auth_final = Authority(str(self.db_path))
        try:
            fin_snap_after = auth_final.snapshot(org_cred, meal_id)
            after_calc_dict = json.dumps([{"p": c.participant_id, "sen": c.sen} for c in fin_snap_after.calculation.consumption], sort_keys=True)
            self.assertEqual(after_calc_dict, baseline_calc_dict)
            self.assertEqual(fin_snap_after.receipt.total_sen, baseline_total_sen)
            self.assertEqual(fin_snap_after.financial_revision, baseline_fin_rev)
        finally:
            auth_final.close()


if __name__ == "__main__":
    unittest.main()
