"""Unit and integration test suite for secure public self-service meal creation in SettleTable."""
import io
import json
from pathlib import Path
import tempfile
import time
import unittest

from settletable.authority import Authority, Participant
from settletable.public_creation import (
    PublicCreationConfig,
    PublicCreationGate,
    extract_client_ip,
    CF_TEST_SECRET_ALWAYS_PASS,
    CF_TEST_SECRET_ALWAYS_FAIL,
    CF_TEST_SECRET_DUPLICATE,
)
from settletable.transport import SettleTableApp


class TestPublicCreation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_public_create.sqlite"
        self.storage_dir = Path(self.tmp_dir.name) / "receipt_photos"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.server_origin = "https://settle.kybuilds.com"
        self.allowed_hosts = ["settle.kybuilds.com", "localhost:8000", "127.0.0.1:8000", "settletable:8000"]
        self.sim_clock_time = 1731300000.0

        self.config = PublicCreationConfig(
            enabled=True,
            turnstile_secret_key=None,  # Disabled by default in basic tests
            turnstile_sitekey="test-sitekey-123",
            turnstile_expected_action="public_create_meal",
            turnstile_expected_hostname="settle.kybuilds.com",
            max_total_meals=5,
            max_meals_per_day=4,
            max_public_diners=10,
            rate_limit_burst=2,
            rate_limit_hourly=3,
            rate_limit_daily=5,
            burst_window_seconds=120.0,
            hourly_window_seconds=3600.0,
            daily_window_seconds=86400.0,
        )
        self.gate = PublicCreationGate(self.config, clock=lambda: self.sim_clock_time)

        self.app = SettleTableApp(
            db_path=self.db_path,
            storage_dir=self.storage_dir,
            server_origin=self.server_origin,
            allowed_hosts=self.allowed_hosts,
            clock=lambda: self.sim_clock_time,
            public_creation_gate=self.gate,
        )

    def tearDown(self):
        self.app.close()
        self.tmp_dir.cleanup()

    def _call(self, method="GET", path="/", headers=None, body=b"", remote_addr="127.0.0.1"):
        headers = headers or {}
        raw_path = path
        qs = ""
        if "?" in raw_path:
            raw_path, qs = raw_path.split("?", 1)

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": raw_path,
            "QUERY_STRING": qs,
            "REMOTE_ADDR": remote_addr,
            "wsgi.input": io.BytesIO(body),
        }
        if body:
            environ["CONTENT_LENGTH"] = str(len(body))
        if "Content-Type" in headers:
            environ["CONTENT_TYPE"] = headers["Content-Type"]
        if "HTTP_HOST" not in headers:
            environ["HTTP_HOST"] = "settle.kybuilds.com"

        for k, v in headers.items():
            if k.lower() == "content-type":
                environ["CONTENT_TYPE"] = v
            elif k.lower() == "content-length":
                environ["CONTENT_LENGTH"] = v
            elif k.startswith("HTTP_"):
                environ[k] = v
            else:
                norm_key = "HTTP_" + k.upper().replace("-", "_")
                environ[norm_key] = v

        response_status = None
        response_headers = None

        def start_response(status, resp_headers):
            nonlocal response_status, response_headers
            response_status = status
            response_headers = resp_headers

        body_chunks = self.app(environ, start_response)
        code = int(response_status.split()[0])
        resp_headers_dict = dict(response_headers)
        return code, resp_headers_dict, b"".join(body_chunks)

    # --------------------------------------------------------------------------
    # 1. Master Switch & Public Config
    # --------------------------------------------------------------------------
    def test_public_creation_disabled_by_default(self):
        self.config.enabled = False
        payload = json.dumps({"meal_title": "Friday Hotpot", "organizer_name": "Alice"}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
        }
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code, 503)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("error"), "public_creation_disabled")

    def test_public_config_endpoint(self):
        code, _, body = self._call("GET", "/api/public-config")
        self.assertEqual(code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("public_creation_enabled"))
        self.assertEqual(data.get("turnstile_sitekey"), "test-sitekey-123")
        self.assertEqual(data.get("max_diners"), 10)

    # --------------------------------------------------------------------------
    # 2. Successful Public Creation & Organizer Session
    # --------------------------------------------------------------------------
    def test_successful_public_meal_creation(self):
        payload = json.dumps({
            "meal_title": "Friday Hai Di Lao",
            "organizer_name": "Alice",
            "diners": ["Bob", "Charlie"],
            "idempotency_key": "test-uuid-1",
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.50",
        }
        code, resp_headers, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code, 201)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        meal_id = data.get("meal_id")
        self.assertTrue(meal_id.startswith("friday-hai-di-lao-"))
        self.assertEqual(len(meal_id), len("friday-hai-di-lao-") + 10)  # slug + 10-hex random
        self.assertEqual(data.get("organizer_name"), "Alice")
        self.assertEqual(data.get("organizer_id"), "O")

        # Set-Cookie present
        cookie = resp_headers.get("Set-Cookie", "")
        self.assertIn("settletable_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Path=/", cookie)

        # Organizer Claim Link present
        org_claim = data.get("organizer_claim")
        self.assertIsNotNone(org_claim)
        self.assertTrue(org_claim["claim_url"].startswith("https://settle.kybuilds.com/#/claim-organizer/"))
        self.assertEqual(len(org_claim["token"]), 43)

        # Verify immediate organizer access via snapshot
        cookie_val = cookie.split("settletable_session=")[1].split(";")[0]
        snap_headers = {
            "Cookie": f"settletable_session={cookie_val}",
        }
        code_snap, _, snap_body = self._call("GET", f"/api/meals/{meal_id}/snapshot", headers=snap_headers)
        self.assertEqual(code_snap, 200)
        snap = json.loads(snap_body.decode("utf-8"))
        self.assertTrue(snap.get("is_organizer"))
        self.assertEqual(snap.get("current_participant_id"), "O")

        # Diners provisioned
        participants = snap.get("participants", [])
        names = set(p["name"] for p in participants)
        self.assertEqual(names, {"Alice", "Bob", "Charlie"})

    # --------------------------------------------------------------------------
    # 3. Cloudflare Turnstile Validation
    # --------------------------------------------------------------------------
    def test_turnstile_validation_pass_and_fail(self):
        self.config.turnstile_secret_key = CF_TEST_SECRET_ALWAYS_PASS
        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.60",
        }

        # 3a. Missing token when secret key is set fails with 400
        payload_no_token = json.dumps({"meal_title": "Dinner", "organizer_name": "Alice"}).encode("utf-8")
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload_no_token)
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "missing_turnstile_token")

        # 3b. Valid token passes
        payload_valid = json.dumps({
            "meal_title": "Dinner",
            "organizer_name": "Alice",
            "turnstile_token": "valid_dummy_token_123",
        }).encode("utf-8")
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload_valid)
        self.assertEqual(code, 201)

        # 3c. Reusing the exact same token within 300s fails with turnstile_token_reused
        code_reuse, _, body_reuse = self._call("POST", "/api/meals/public-create", headers=headers, body=payload_valid)
        self.assertEqual(code_reuse, 400)
        self.assertEqual(json.loads(body_reuse.decode("utf-8")).get("error"), "turnstile_token_reused")

        # 3d. Always fail secret key
        self.config.turnstile_secret_key = CF_TEST_SECRET_ALWAYS_FAIL
        payload_fail = json.dumps({
            "meal_title": "Dinner",
            "organizer_name": "Bob",
            "turnstile_token": "token_for_failing_key",
        }).encode("utf-8")
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload_fail)
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "turnstile_verification_failed")

    def test_turnstile_action_and_hostname_mismatch(self):
        # Custom siteverify mock returning mismatched action / hostname
        mock_response = {
            "success": True,
            "action": "login",
            "hostname": "attacker.org",
        }
        self.gate._siteverify_fn = lambda secret, token, ip, idem: mock_response
        self.config.turnstile_secret_key = "some_secret_key"

        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.70",
        }
        payload = json.dumps({
            "meal_title": "Dinner",
            "organizer_name": "Alice",
            "turnstile_token": "some_token",
        }).encode("utf-8")

        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "turnstile_action_mismatch")

    # --------------------------------------------------------------------------
    # 4. IP Rate Limiting (Burst, Hourly, Daily)
    # --------------------------------------------------------------------------
    def test_ip_rate_limiting_burst_and_hourly(self):
        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "198.51.100.22",
        }
        # Burst limit is 2 per 120s
        for i in range(2):
            payload = json.dumps({"meal_title": f"Meal {i}", "organizer_name": "Alice"}).encode("utf-8")
            code, _, _ = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
            self.assertEqual(code, 201)

        # 3rd request in same burst window is rate limited
        payload = json.dumps({"meal_title": "Meal 3", "organizer_name": "Alice"}).encode("utf-8")
        code, resp_headers, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code, 429)
        self.assertIn("Retry-After", resp_headers)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("error"), "rate_limit_exceeded")

        # Advance clock past burst window (130s), now 3rd request succeeds
        self.sim_clock_time += 130.0
        code, _, _ = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code, 201)

        # Total in 1h is now 3. Hourly limit is 3. Next request triggers hourly limit
        self.sim_clock_time += 130.0  # past burst, but still within 1h
        payload = json.dumps({"meal_title": "Meal 4", "organizer_name": "Alice"}).encode("utf-8")
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code, 429)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "rate_limit_exceeded")

    # --------------------------------------------------------------------------
    # 5. Client IP Extraction
    # --------------------------------------------------------------------------
    def test_client_ip_extraction(self):
        # 5a. CF-Connecting-IP takes highest priority
        env = {
            "HTTP_CF_CONNECTING_IP": "203.0.113.195",
            "HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2",
            "REMOTE_ADDR": "127.0.0.1",
        }
        self.assertEqual(extract_client_ip(env), "203.0.113.195")

        # 5b. X-Forwarded-For first element if CF header absent
        env_xff = {
            "HTTP_X_FORWARDED_FOR": "198.51.100.44, 10.0.0.1",
            "REMOTE_ADDR": "127.0.0.1",
        }
        self.assertEqual(extract_client_ip(env_xff), "198.51.100.44")

        # 5c. Fallback to REMOTE_ADDR
        env_remote = {
            "REMOTE_ADDR": "192.0.2.1",
        }
        self.assertEqual(extract_client_ip(env_remote), "192.0.2.1")

        # 5d. Malformed IP rejected and falls back safely
        env_malformed = {
            "HTTP_CF_CONNECTING_IP": "spoofed-non-ip-garbage",
            "REMOTE_ADDR": "127.0.0.1",
        }
        self.assertEqual(extract_client_ip(env_malformed), "127.0.0.1")

    # --------------------------------------------------------------------------
    # 6. Global Capacity Limits
    # --------------------------------------------------------------------------
    def test_global_capacity_limits(self):
        # Config max_total_meals = 5
        self.config.rate_limit_burst = 20
        self.config.rate_limit_hourly = 20
        self.config.rate_limit_daily = 20
        self.config.max_meals_per_day = 20
        self.config.max_total_meals = 2  # Set low cap for test

        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.99",
        }

        # Create 2 meals (reaches capacity)
        for i in range(2):
            payload = json.dumps({"meal_title": f"Party {i}", "organizer_name": "Host"}).encode("utf-8")
            code, _, _ = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
            self.assertEqual(code, 201)

        # 3rd meal exceeds capacity
        payload = json.dumps({"meal_title": "Party 3", "organizer_name": "Host"}).encode("utf-8")
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code, 507)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "capacity_exceeded")

    # --------------------------------------------------------------------------
    # 7. Idempotency & Retry Deduplication
    # --------------------------------------------------------------------------
    def test_idempotency_deduplication(self):
        payload = json.dumps({
            "meal_title": "Hotpot Night",
            "organizer_name": "Dave",
            "idempotency_key": "unique-mobile-uuid-42",
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.111",
        }

        # First request creates meal
        code1, _, body1 = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code1, 201)
        data1 = json.loads(body1.decode("utf-8"))

        # Second request with same idempotency key returns identical result without creating second meal
        code2, _, body2 = self._call("POST", "/api/meals/public-create", headers=headers, body=payload)
        self.assertEqual(code2, 201)
        data2 = json.loads(body2.decode("utf-8"))
        self.assertEqual(data1["meal_id"], data2["meal_id"])
        self.assertEqual(data1["organizer_claim"]["token"], data2["organizer_claim"]["token"])

        # Check DB only has 1 meal
        auth = self.app.get_authority()
        self.assertEqual(auth.get_meals_count(), 1)

    # --------------------------------------------------------------------------
    # 8. Input Validation & Squatting Protection
    # --------------------------------------------------------------------------
    def test_input_validation_and_bounds(self):
        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.120",
        }

        # 8a. Empty title
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=b'{"meal_title":"","organizer_name":"Alice"}')
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "invalid_input")

        # 8b. Title too long (>60 chars)
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=json.dumps({"meal_title":"A"*61,"organizer_name":"Alice"}).encode("utf-8"))
        self.assertEqual(code, 400)

        # 8c. Control characters in title
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=json.dumps({"meal_title":"Bad\nTitle","organizer_name":"Alice"}).encode("utf-8"))
        self.assertEqual(code, 400)

        # 8d. Duplicate participant names (case-insensitive collision)
        payload_dup = json.dumps({"meal_title":"Dinner","organizer_name":"Alice","diners":["alice"]}).encode("utf-8")
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload_dup)
        self.assertEqual(code, 409)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "ambiguous_participant_name")

        # 8e. Diners exceeding max_public_diners (cap is 10)
        payload_too_many = json.dumps({"meal_title":"Big Dinner","organizer_name":"Host","diners":[f"D{i}" for i in range(11)]}).encode("utf-8")
        code, _, body = self._call("POST", "/api/meals/public-create", headers=headers, body=payload_too_many)
        self.assertEqual(code, 400)

    def test_room_id_squatting_defense(self):
        # Two users creating "Friday Hotpot" receive distinct, unpredictable IDs
        headers1 = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.131",
        }
        headers2 = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.132",
        }
        payload = json.dumps({"meal_title": "Friday Hotpot", "organizer_name": "Host"}).encode("utf-8")

        code1, _, body1 = self._call("POST", "/api/meals/public-create", headers=headers1, body=payload)
        code2, _, body2 = self._call("POST", "/api/meals/public-create", headers=headers2, body=payload)

        self.assertEqual(code1, 201)
        self.assertEqual(code2, 201)
        id1 = json.loads(body1.decode("utf-8"))["meal_id"]
        id2 = json.loads(body2.decode("utf-8"))["meal_id"]

        self.assertNotEqual(id1, id2)
        self.assertTrue(id1.startswith("friday-hotpot-"))
        self.assertTrue(id2.startswith("friday-hotpot-"))

    # --------------------------------------------------------------------------
    # 9. Administrative Bootstrap Unchanged & Ingress Preservation
    # --------------------------------------------------------------------------
    def test_administrative_bootstrap_remains_loopback_only(self):
        # 9a. Local loopback bootstrap succeeds
        b_body = json.dumps({"participants": [{"id": "O", "name": "Admin", "organizer": True}]}).encode("utf-8")
        code, _, body = self._call("POST", "/api/meals/admin-meal-1/bootstrap", headers={"Content-Type": "application/json", "X-SettleTable-Action": "1", "Origin": "https://settle.kybuilds.com"}, body=b_body, remote_addr="127.0.0.1")
        self.assertEqual(code, 201)

        # 9b. Proxy headers on administrative bootstrap rejected with 403 forbidden
        code, _, _ = self._call(
            "POST",
            "/api/meals/admin-meal-2/bootstrap",
            headers={"Content-Type": "application/json", "X-SettleTable-Action": "1", "Origin": "https://settle.kybuilds.com", "CF-Connecting-IP": "203.0.113.1"},
            body=b_body,
            remote_addr="127.0.0.1",
        )
        self.assertEqual(code, 403)


    # --------------------------------------------------------------------------
    # 10. Regression Tests: CSP Turnstile, Idempotency Retry vs Rate Limit, Turnstile Action Matching
    # --------------------------------------------------------------------------
    def test_csp_allows_cloudflare_turnstile(self):
        code, headers, _ = self._call("GET", "/")
        self.assertEqual(code, 200)
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self' https://challenges.cloudflare.com", csp)
        self.assertIn("frame-src 'self' https://challenges.cloudflare.com", csp)
        self.assertIn("connect-src 'self' https://challenges.cloudflare.com", csp)

    def test_idempotency_bypasses_rate_limit_on_retry(self):
        headers = {
            "Content-Type": "application/json",
            "X-SettleTable-Action": "1",
            "Origin": "https://settle.kybuilds.com",
            "CF-Connecting-IP": "203.0.113.140",
        }
        # First request creates meal with idempotency key
        payload1 = json.dumps({
            "meal_title": "First Meal",
            "organizer_name": "Host",
            "idempotency_key": "retry-key-999",
        }).encode("utf-8")
        code1, _, body1 = self._call("POST", "/api/meals/public-create", headers=headers, body=payload1)
        self.assertEqual(code1, 201)
        meal_id1 = json.loads(body1.decode("utf-8"))["meal_id"]

        # Second request consumes the burst rate limit (rate_limit_burst is 2)
        payload2 = json.dumps({
            "meal_title": "Second Meal",
            "organizer_name": "Host",
        }).encode("utf-8")
        code2, _, _ = self._call("POST", "/api/meals/public-create", headers=headers, body=payload2)
        self.assertEqual(code2, 201)

        # Third new request gets 429
        payload3 = json.dumps({
            "meal_title": "Third Meal",
            "organizer_name": "Host",
        }).encode("utf-8")
        code3, _, body3 = self._call("POST", "/api/meals/public-create", headers=headers, body=payload3)
        self.assertEqual(code3, 429)

        # Retrying the first request with completed idempotency key succeeds with 201 despite rate limit
        code_retry, _, body_retry = self._call("POST", "/api/meals/public-create", headers=headers, body=payload1)
        self.assertEqual(code_retry, 201)
        self.assertEqual(json.loads(body_retry.decode("utf-8"))["meal_id"], meal_id1)

    def test_turnstile_missing_action_or_hostname_rejected(self):
        gate = PublicCreationGate(
            PublicCreationConfig(
                enabled=True,
                turnstile_secret_key="secret-key",
                turnstile_expected_action="public_create_meal",
                turnstile_expected_hostname="settle.kybuilds.com",
            )
        )
        # Mock siteverify returning no action
        gate._call_siteverify = lambda token, ip, key: {
            "success": True,
            "action": None,
            "hostname": "settle.kybuilds.com",
        }
        valid, err = gate.verify_turnstile("dummy-token", "203.0.113.1", None)
        self.assertFalse(valid)
        self.assertEqual(err, "turnstile_action_mismatch")

        # Mock siteverify returning no hostname
        gate._call_siteverify = lambda token, ip, key: {
            "success": True,
            "action": "public_create_meal",
            "hostname": None,
        }
        valid, err = gate.verify_turnstile("dummy-token", "203.0.113.1", None)
        self.assertFalse(valid)
        self.assertEqual(err, "turnstile_hostname_mismatch")


if __name__ == "__main__":
    unittest.main()
