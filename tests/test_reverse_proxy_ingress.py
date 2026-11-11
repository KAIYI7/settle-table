"""Synthetic reverse-proxy and Cloudflare Tunnel ingress security test suite for SettleTable.

Validates that when SettleTable is deployed behind an edge reverse proxy or
Cloudflare Named Tunnel with a custom HTTPS origin, all security boundaries,
ingress rules, CSRF validations, cache controls, and loopback restrictions hold.
"""
import io
import json
import tempfile
import unittest
from pathlib import Path

from settletable.authority import Authority, Participant
from settletable.transport import SettleTableApp, MAX_BODY_BYTES


class TestReverseProxyIngress(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_tunnel.sqlite"
        self.storage_dir = Path(self.tmp_dir.name) / "receipt_photos"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.custom_origin = "https://settle.kybuilds.com"
        self.allowed_hosts = [
            "settle.kybuilds.com",
            "localhost:8000",
            "127.0.0.1:8000",
            "settletable:8000",
        ]

        self.logs = []
        self.app = SettleTableApp(
            db_path=self.db_path,
            storage_dir=self.storage_dir,
            server_origin=self.custom_origin,
            allowed_hosts=self.allowed_hosts,
            logger=self.logs.append,
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
    # 1. Public Custom Domain Host & Ingress Validation
    # --------------------------------------------------------------------------
    def test_public_custom_domain_host_validation(self):
        # 1a. Public custom hostname accepted on application routes
        code, _, _ = self._call("GET", "/", headers={"Host": "settle.kybuilds.com"})
        self.assertEqual(code, 200)

        # Container-to-container internal hostname accepted
        code, _, _ = self._call("GET", "/", headers={"Host": "settletable:8000"})
        self.assertEqual(code, 200)

        # Loopback admin hostname accepted
        code, _, _ = self._call("GET", "/", headers={"Host": "127.0.0.1:8000"})
        self.assertEqual(code, 200)

        # 1b. Unrecognized / spoofed host rejected on application routes with 400 invalid_host
        code, _, body = self._call("GET", "/", headers={"Host": "attacker.example.org"})
        self.assertEqual(code, 400)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("error"), "invalid_host")

        # 1c. Health probe bypasses Host check to allow container orchestrators to probe by IP
        code, _, _ = self._call("GET", "/healthz", headers={"Host": "arbitrary-internal-ip:8000"})
        self.assertEqual(code, 200)

    # --------------------------------------------------------------------------
    # 2. Exact-Origin CSRF Protection Under Public HTTPS
    # --------------------------------------------------------------------------
    def test_exact_origin_csrf_protection_under_public_https(self):
        body = json.dumps({"claim_token": "abcdefghijklmnopqrstuvwxyz0123456789-_ABCDE"}).encode("utf-8")

        # Mutating request with exact public HTTPS origin succeeds
        code, _, _ = self._call(
            "POST",
            "/api/organizer-claims/inspect",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://settle.kybuilds.com",
            },
            body=body,
        )
        self.assertEqual(code, 200)

        # Mutating request to a state-changing route without action header is rejected
        code, _, resp_body = self._call(
            "POST",
            "/api/meals/test-meal/apply",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://settle.kybuilds.com",
            },
            body=b'{"kind":"ReviewReceipt"}',
        )
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(resp_body).get("error"), "missing_action_header")

        # Mutating request with HTTP instead of HTTPS (scheme mismatch) is rejected
        code, _, resp_body = self._call(
            "POST",
            "/api/meals/test-meal/apply",
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Origin": "http://settle.kybuilds.com",
            },
            body=b'{"kind":"ReviewReceipt"}',
        )
        self.assertEqual(code, 403)
        self.assertEqual(json.loads(resp_body).get("error"), "origin_mismatch")

        # Mutating request with foreign attacker Origin is rejected
        code, _, resp_body = self._call(
            "POST",
            "/api/meals/test-meal/apply",
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Origin": "https://malicious-site.com",
            },
            body=b'{"kind":"ReviewReceipt"}',
        )
        self.assertEqual(code, 403)
        self.assertEqual(json.loads(resp_body).get("error"), "origin_mismatch")

        # Mutating request with 'null' Origin (sandboxed iframe / file) is rejected
        code, _, resp_body = self._call(
            "POST",
            "/api/meals/test-meal/apply",
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Origin": "null",
            },
            body=b'{"kind":"ReviewReceipt"}',
        )
        self.assertEqual(code, 403)
        self.assertEqual(json.loads(resp_body).get("error"), "origin_mismatch")

        # Referer fallback: valid HTTPS referer matches
        code, _, resp_body = self._call(
            "POST",
            "/api/meals/test-meal/apply",
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Referer": "https://settle.kybuilds.com/meal/test-meal",
            },
            body=b'{"kind":"ReviewReceipt"}',
        )
        self.assertEqual(code, 401)
        self.assertEqual(json.loads(resp_body).get("error"), "invalid_session")

        # Referer fallback: invalid referer rejected with 403 origin_mismatch
        code, _, resp_body = self._call(
            "POST",
            "/api/meals/test-meal/apply",
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Referer": "https://evil.attacker.org/phish",
            },
            body=b'{"kind":"ReviewReceipt"}',
        )
        self.assertEqual(code, 403)
        self.assertEqual(json.loads(resp_body).get("error"), "origin_mismatch")

    # --------------------------------------------------------------------------
    # 3. Cloudflare Forwarding Headers Handling
    # --------------------------------------------------------------------------
    def test_cloudflare_forwarding_headers_handling(self):
        # Standard API requests carrying Cloudflare edge headers execute cleanly
        headers = {
            "CF-Connecting-IP": "203.0.113.195",
            "CF-Ray": "8e123456789abcde-SIN",
            "CF-Visitor": '{"scheme":"https"}',
            "X-Forwarded-For": "203.0.113.195, 172.70.1.1",
            "X-Forwarded-Proto": "https",
        }
        code, _, body = self._call("GET", "/healthz", headers=headers)
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body).get("ok"))

        # HTML landing routes execute cleanly with Cloudflare headers
        code, resp_headers, body = self._call("GET", "/", headers=headers)
        self.assertEqual(code, 200)
        self.assertIn("text/html", resp_headers.get("Content-Type", ""))
        self.assertIn("<title>SettleTable", body.decode("utf-8"))

    # --------------------------------------------------------------------------
    # 4. External Meal Bootstrap Rejected with Proxy Headers
    # --------------------------------------------------------------------------
    def test_external_meal_bootstrap_rejected_with_all_proxy_headers(self):
        bootstrap_body = json.dumps({
            "participants": [{"id": "O", "name": "Organizer", "organizer": True}]
        }).encode("utf-8")

        # 4a. Each proxy header individually blocks bootstrap with 403 forbidden
        tested_proxy_headers = [
            ("X-Forwarded-For", "203.0.113.195"),
            ("X-Forwarded-Host", "settle.kybuilds.com"),
            ("X-Forwarded-Proto", "https"),
            ("Forwarded", "for=203.0.113.195"),
            ("X-Real-IP", "203.0.113.195"),
            ("CF-Connecting-IP", "203.0.113.195"),
            ("True-Client-IP", "203.0.113.195"),
            ("X-Cluster-Client-IP", "203.0.113.195"),
        ]

        for hdr_name, hdr_val in tested_proxy_headers:
            code, _, body = self._call(
                "POST",
                "/api/meals/test-bootstrap/bootstrap",
                headers={
                    "Content-Type": "application/json",
                    "X-SettleTable-Action": "1",
                    "Origin": "https://settle.kybuilds.com",
                    hdr_name: hdr_val,
                },
                body=bootstrap_body,
                remote_addr="127.0.0.1",
            )
            self.assertEqual(
                code,
                403,
                f"Expected 403 when header {hdr_name} is present, got {code}",
            )
            data = json.loads(body.decode("utf-8"))
            self.assertEqual(data.get("error"), "forbidden")

        # 4b. Non-loopback REMOTE_ADDR blocks bootstrap even without proxy headers
        code, _, body = self._call(
            "POST",
            "/api/meals/test-bootstrap/bootstrap",
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Origin": "https://settle.kybuilds.com",
            },
            body=bootstrap_body,
            remote_addr="198.51.100.22",
        )
        self.assertEqual(code, 403)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "forbidden")

        # 4c. Legitimate local bootstrap on 127.0.0.1 without proxy headers succeeds
        code, _, body = self._call(
            "POST",
            "/api/meals/test-bootstrap/bootstrap",
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Origin": "https://settle.kybuilds.com",
            },
            body=bootstrap_body,
            remote_addr="127.0.0.1",
        )
        self.assertEqual(code, 201)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("meal_id"), "test-bootstrap")

    # --------------------------------------------------------------------------
    # 5. Unauthenticated Access to Private Data Denied
    # --------------------------------------------------------------------------
    def test_unauthenticated_access_to_private_data_denied(self):
        auth = Authority(self.db_path, storage_dir=self.storage_dir)
        meal_id = "private-meal-1"
        try:
            b_res = auth.bootstrap(meal_id, (Participant(id="org", name="Organizer", organizer=True),))
        finally:
            auth.close()

        # Unauthenticated snapshot -> 401
        code, _, body = self._call("GET", f"/api/meals/{meal_id}/snapshot")
        self.assertEqual(code, 401)
        self.assertEqual(json.loads(body).get("error"), "invalid_session")

        # Unauthenticated receipt photo -> 401
        code, _, body = self._call("GET", f"/api/meals/{meal_id}/receipt/photo")
        self.assertEqual(code, 401)
        self.assertEqual(json.loads(body).get("error"), "invalid_session")

        # Unauthenticated photo delete -> 401
        code, _, body = self._call(
            "DELETE",
            f"/api/meals/{meal_id}/receipt/photo",
            headers={
                "X-SettleTable-Action": "1",
                "Origin": "https://settle.kybuilds.com",
            },
        )
        self.assertEqual(code, 401)
        self.assertEqual(json.loads(body).get("error"), "invalid_session")

        # Unauthenticated join-requests list -> 401
        code, _, body = self._call("GET", f"/api/meals/{meal_id}/join-requests")
        self.assertEqual(code, 401)
        self.assertEqual(json.loads(body).get("error"), "invalid_session")

        # Forged cookie -> 401
        code, _, body = self._call(
            "GET",
            f"/api/meals/{meal_id}/snapshot",
            headers={"Cookie": "settletable_session=forged_unauthorized_token_1234567890"},
        )
        self.assertEqual(code, 401)
        self.assertEqual(json.loads(body).get("error"), "invalid_session")

    # --------------------------------------------------------------------------
    # 6. Private Responses Not Cached by Shared Intermediaries
    # --------------------------------------------------------------------------
    def test_private_responses_not_cached_by_shared_intermediaries(self):
        # 6a. Dynamic API responses must return Cache-Control: no-store
        code, headers, _ = self._call("GET", "/healthz")
        self.assertEqual(code, 200)
        self.assertEqual(headers.get("Cache-Control"), "no-store")

        # 6b. Error responses must return Cache-Control: no-store
        code, headers, _ = self._call("GET", "/api/meals/non-existent/snapshot")
        self.assertEqual(code, 401)
        self.assertEqual(headers.get("Cache-Control"), "no-store")

        # 6c. Bootstrap a meal, store a synthetic photo, and verify photo Cache-Control
        auth = Authority(self.db_path, storage_dir=self.storage_dir)
        meal_id = "photo-cache-meal"
        try:
            b_res = auth.bootstrap(meal_id, (Participant(id="org", name="Organizer", organizer=True),))
            org_cred = next(s.credential for s in b_res.sessions if s.participant_id == "org")

            # 1x1 valid PNG bytes
            png_bytes = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00"
                b"\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            auth.store_receipt_photo(org_cred, meal_id, png_bytes, "image/png", 1, 1)
        finally:
            auth.close()

        code, photo_headers, _ = self._call(
            "GET",
            f"/api/meals/{meal_id}/receipt/photo",
            headers={"Cookie": f"settletable_session={org_cred}"},
        )
        self.assertEqual(code, 200)
        cache_ctrl = photo_headers.get("Cache-Control", "")
        # Must explicitly instruct intermediaries (Cloudflare Edge Cache) not to store private receipt photos
        self.assertIn("no-store", cache_ctrl)
        self.assertIn("private", cache_ctrl)
        self.assertIn("no-cache", cache_ctrl)
        self.assertIn("must-revalidate", cache_ctrl)

    # --------------------------------------------------------------------------
    # 7. No Secrets in Request Logs Under Tunnel
    # --------------------------------------------------------------------------
    def test_no_secrets_in_request_logs_under_tunnel(self):
        secret_token = "TEST_SECRET_TOKEN_43_CHARS_1234567890abcdef"

        # Query param redaction
        self._call("GET", f"/api/healthz?token={secret_token}&claim_token={secret_token}")

        # Path redaction
        self._call("GET", f"/claim-organizer/{secret_token}")
        self._call("GET", f"/invite/{secret_token}")

        # Clean POST inspection (token in JSON body)
        body = json.dumps({"claim_token": secret_token}).encode("utf-8")
        self._call("POST", "/api/organizer-claims/inspect", headers={"Content-Type": "application/json"}, body=body)

        # Inspect all captured log lines
        for log_line in self.logs:
            self.assertNotIn(
                secret_token,
                log_line,
                f"Secret token leaked in log line: {log_line}",
            )

    # --------------------------------------------------------------------------
    # 8. Abuse Protections Under Tunnel
    # --------------------------------------------------------------------------
    def test_abuse_protections_under_tunnel(self):
        # 8a. Single header line > 4KB returns 431
        huge_header_val = "A" * 4100
        code, _, body = self._call(
            "GET",
            "/healthz",
            headers={"X-Custom-Abuse": huge_header_val},
        )
        self.assertEqual(code, 431)
        self.assertEqual(json.loads(body).get("error"), "header_too_large")

        # 8b. Huge integer in JSON payload returns 400 invalid_number
        huge_int_body = b'{"number": 999999999999999999999999999999999999999999999999999}'
        code, _, body = self._call(
            "POST",
            "/api/organizer-claims/inspect",
            headers={"Content-Type": "application/json"},
            body=huge_int_body,
        )
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(body).get("error"), "invalid_number")

        # 8c. Body payload exceeding MAX_BODY_BYTES returns 413
        code, _, body = self._call(
            "POST",
            "/api/organizer-claims/inspect",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(MAX_BODY_BYTES + 1024),
            },
            body=b"",
        )
        self.assertEqual(code, 413)
        self.assertEqual(json.loads(body).get("error"), "payload_too_large")

    # --------------------------------------------------------------------------
    # 9. Deny-by-Default Unmatched Hostnames
    # --------------------------------------------------------------------------
    def test_deny_by_default_unmatched_hostnames(self):
        unmatched_hosts = [
            "sub.settle.kybuilds.com",
            "kybuilds.com",
            "tunnel.kybuilds.com",
            "192.168.1.50",
            "random-domain.net",
            "settletable.internal",
        ]
        for host in unmatched_hosts:
            code, _, body = self._call("GET", "/", headers={"Host": host})
            self.assertEqual(
                code,
                400,
                f"Expected 400 for unmatched host '{host}', got {code}",
            )
            self.assertEqual(json.loads(body).get("error"), "invalid_host")

    # --------------------------------------------------------------------------
    # 10. Public Self-Service Creation Ingress Validation
    # --------------------------------------------------------------------------
    def test_public_creation_through_reverse_proxy_ingress(self):
        # Enable public creation on the test app gate
        self.app.public_creation_gate.config.enabled = True

        # 10a. Public config accessible through reverse proxy
        code, _, body = self._call("GET", "/api/public-config", headers={"Host": "settle.kybuilds.com"})
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body.decode("utf-8")).get("public_creation_enabled"))

        # 10b. Public create with malicious Origin rejected with 403 origin_mismatch
        payload = json.dumps({"meal_title": "Hotpot", "organizer_name": "Alice"}).encode("utf-8")
        code, _, body = self._call(
            "POST",
            "/api/meals/public-create",
            headers={
                "Host": "settle.kybuilds.com",
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Origin": "https://evil-phishing.org",
                "CF-Connecting-IP": "203.0.113.195",
            },
            body=payload,
        )
        self.assertEqual(code, 403)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "origin_mismatch")

        # 10c. Public create missing X-SettleTable-Action rejected with 400
        code, _, body = self._call(
            "POST",
            "/api/meals/public-create",
            headers={
                "Host": "settle.kybuilds.com",
                "Content-Type": "application/json",
                "Origin": "https://settle.kybuilds.com",
                "CF-Connecting-IP": "203.0.113.195",
            },
            body=payload,
        )
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(body.decode("utf-8")).get("error"), "missing_action_header")

        # 10d. Valid public creation through Cloudflare Tunnel with CF-Connecting-IP succeeds
        code, resp_headers, body = self._call(
            "POST",
            "/api/meals/public-create",
            headers={
                "Host": "settle.kybuilds.com",
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Origin": "https://settle.kybuilds.com",
                "CF-Connecting-IP": "203.0.113.195",
            },
            body=payload,
        )
        self.assertEqual(code, 201)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertIn("settletable_session=", resp_headers.get("Set-Cookie", ""))


if __name__ == "__main__":
    unittest.main()
