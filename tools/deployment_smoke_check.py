"""Deployment Health and Smoke Check Suite for SettleTable.

Validates that a local, containerized, or hosted SettleTable deployment
satisfies essential ingress, static serving, and security invariants.
"""
import argparse
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def check(description, fn):
    print(f"  * {description:<55} ... ", end="", flush=True)
    try:
        fn()
        print("PASS [OK]")
        return True
    except AssertionError as e:
        print(f"FAIL [X] ({e})")
        return False
    except HTTPError as e:
        print(f"FAIL [X] (HTTP {e.code}: {e.reason})")
        return False
    except Exception as e:
        print(f"ERROR [X] ({e})")
        return False


def run_smoke_checks(base_url: str):
    base_url = base_url.rstrip("/")
    print(f"\n=======================================================")
    print(f" SettleTable -- Deployment Smoke Check")
    print(f" Target: {base_url}")
    print(f"=======================================================\n")

    passed = 0
    total = 0

    def t(desc, fn):
        nonlocal passed, total
        total += 1
        if check(desc, fn):
            passed += 1

    # 1. Healthcheck probe
    def check_health():
        req = Request(f"{base_url}/healthz")
        with urlopen(req, timeout=5) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("ok") is True and data.get("status") == "healthy", f"Invalid payload: {data}"
    t("1. GET /healthz probe returns 200 OK healthy", check_health)

    # 2. Main HTML shell
    def check_index():
        req = Request(f"{base_url}/")
        with urlopen(req, timeout=5) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            content = resp.read().decode("utf-8")
            assert "<title>SettleTable" in content, "Missing SettleTable title"
            assert "app.js" in content, "Missing app.js script tag"
    t("2. GET / serves HTML shell with app assets", check_index)

    # 3. Static CSS asset
    def check_css():
        req = Request(f"{base_url}/static/style.css")
        with urlopen(req, timeout=5) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            ct = resp.headers.get("Content-Type", "")
            assert "text/css" in ct, f"Wrong Content-Type: {ct}"
    t("3. GET /static/style.css returns text/css", check_css)

    # 4. Static JS asset
    def check_js():
        req = Request(f"{base_url}/static/app.js")
        with urlopen(req, timeout=5) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            ct = resp.headers.get("Content-Type", "")
            assert "javascript" in ct, f"Wrong Content-Type: {ct}"
    t("4. GET /static/app.js returns javascript", check_js)

    # 5. Security headers
    def check_headers():
        req = Request(f"{base_url}/static/style.css")
        with urlopen(req, timeout=5) as resp:
            csp = resp.headers.get("Content-Security-Policy", "")
            nosniff = resp.headers.get("X-Content-Type-Options", "")
            referrer = resp.headers.get("Referrer-Policy", "")
            assert "default-src 'self'" in csp, "Missing CSP default-src 'self'"
            assert nosniff == "nosniff", "Missing X-Content-Type-Options: nosniff"
            assert referrer == "no-referrer", "Missing Referrer-Policy: no-referrer"
    t("5. Security headers (CSP, nosniff, Referrer-Policy)", check_headers)

    # 6. Proxy header rejection on bootstrap
    def check_bootstrap_proxy():
        req = Request(
            f"{base_url}/api/meals/probe-check/bootstrap",
            data=b'{"participants":[{"id":"O","name":"Org","organizer":true}]}',
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "X-Forwarded-For": "203.0.113.195",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=5) as resp:
                raise AssertionError(f"Expected 403 Forbidden, but received {resp.status}")
        except HTTPError as e:
            assert e.code == 403, f"Expected HTTP 403, got {e.code}"
    t("6. Ingress blocks /bootstrap when proxy headers present", check_bootstrap_proxy)

    # 7. Action header enforcement
    def check_missing_action():
        req = Request(
            f"{base_url}/api/meals/probe-check/apply",
            data=b'{"kind":"ReviewReceipt"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=5) as resp:
                raise AssertionError(f"Expected 400 Bad Request, but received {resp.status}")
        except HTTPError as e:
            assert e.code == 400, f"Expected HTTP 400, got {e.code}"
            data = json.loads(e.read().decode("utf-8"))
            assert data.get("error") == "missing_action_header"
    t("7. Mutating requests reject missing X-SettleTable-Action", check_missing_action)

    # 8. Origin mismatch enforcement
    def check_origin_mismatch():
        req = Request(
            f"{base_url}/api/meals/probe-check/apply",
            data=b'{"kind":"ReviewReceipt"}',
            headers={
                "Content-Type": "application/json",
                "X-SettleTable-Action": "1",
                "Origin": "https://malicious-attacker.com",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=5) as resp:
                raise AssertionError(f"Expected 403 Forbidden, but received {resp.status}")
        except HTTPError as e:
            assert e.code == 403, f"Expected HTTP 403, got {e.code}"
            data = json.loads(e.read().decode("utf-8"))
            assert data.get("error") == "origin_mismatch"
    t("8. Mutating requests reject foreign Origin header", check_origin_mismatch)

    # 9. Organizer claim HTML shell route
    def check_claim_shell():
        req = Request(f"{base_url}/claim-organizer/abcdefghijklmnopqrstuvwxyz0123456789-_ABCDE")
        with urlopen(req, timeout=5) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            content = resp.read().decode("utf-8")
            assert "<title>SettleTable" in content, "Missing SettleTable title"
    t("9. GET /claim-organizer/{token} serves HTML shell", check_claim_shell)

    # 10. Organizer claim API inspection
    def check_claim_inspection():
        req = Request(f"{base_url}/api/organizer-claims/abcdefghijklmnopqrstuvwxyz0123456789-_ABCDE")
        with urlopen(req, timeout=5) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("ok") is True and data.get("valid") is False, f"Unexpected response: {data}"
    t("10. GET /api/organizer-claims/{token} inspection returns valid=false for non-existent token", check_claim_inspection)

    print(f"\nResults: {passed}/{total} smoke checks passed.")
    if passed == total:
        print("[SUCCESS] All deployment smoke checks verified successfully!\n")
        return 0
    else:
        print("[FAILURE] One or more smoke checks failed.\n", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Run SettleTable deployment smoke checks")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base URL of running deployment")
    args = parser.parse_args()
    sys.exit(run_smoke_checks(args.url))


if __name__ == "__main__":
    main()
