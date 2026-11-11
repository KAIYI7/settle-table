"""Secure public self-service meal creation gate for SettleTable.

Implements defense-in-depth protections for unauthenticated public creation:
- Master server-side kill switch (SETTLETABLE_PUBLIC_CREATION_ENABLED)
- Cloudflare Turnstile verification with Siteverify validation, hostname/action checks, and token replay prevention
- In-memory sliding-window IP rate limiting (burst, hourly, daily)
- Global database capacity and 24-hour creation limits
- Idempotency deduplication for retries and double taps
- Cryptographically unguessable room ID generation
- Input sanitization and participant bounds
"""
from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Any

logger = logging.getLogger("settletable.public_creation")

TURNSTILE_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Cloudflare official testing keys
CF_TEST_SECRET_ALWAYS_PASS = "1x0000000000000000000000000000000AA"
CF_TEST_SECRET_ALWAYS_FAIL = "2x0000000000000000000000000000000AA"
CF_TEST_SECRET_DUPLICATE = "3x0000000000000000000000000000000AA"


def extract_client_ip(environ: dict) -> str:
    """Extract and validate visitor IP from trusted headers or socket address.

    Precedence:
    1. HTTP_CF_CONNECTING_IP: In SettleTable's production deployment, ingress is
       strictly routed via Cloudflare Tunnel where Cloudflare edge sanitizes and
       overwrites this header with the client's validated IP.
    2. HTTP_X_FORWARDED_FOR (leftmost IP): Fallback for standard reverse proxies.
    3. REMOTE_ADDR: Direct socket address.
    """
    # 1. Cloudflare connecting IP (set by Cloudflare Edge / Tunnel)
    cf_ip = environ.get("HTTP_CF_CONNECTING_IP", "").strip()
    if cf_ip:
        try:
            ipaddress.ip_address(cf_ip)
            return cf_ip
        except ValueError:
            pass

    # 2. X-Forwarded-For (client is first IP in the chain)
    xff = environ.get("HTTP_X_FORWARDED_FOR", "").strip()
    if xff:
        client_cand = xff.split(",")[0].strip()
        try:
            ipaddress.ip_address(client_cand)
            return client_cand
        except ValueError:
            pass

    # 3. Standard REMOTE_ADDR
    remote_addr = environ.get("REMOTE_ADDR", "").strip()
    if remote_addr:
        try:
            ipaddress.ip_address(remote_addr)
            return remote_addr
        except ValueError:
            pass

    return "127.0.0.1"


@dataclass
class PublicCreationConfig:
    enabled: bool = False
    turnstile_secret_key: str | None = None
    turnstile_sitekey: str | None = None
    turnstile_expected_action: str = "public_create_meal"
    turnstile_expected_hostname: str | None = None
    max_total_meals: int = 100
    max_meals_per_day: int = 25
    max_public_diners: int = 20
    rate_limit_burst: int = 2       # max 2 in 120s
    rate_limit_hourly: int = 5      # max 5 in 1 hour
    rate_limit_daily: int = 10      # max 10 in 24 hours
    burst_window_seconds: float = 120.0
    hourly_window_seconds: float = 3600.0
    daily_window_seconds: float = 86400.0
    idempotency_ttl_seconds: float = 600.0
    token_replay_ttl_seconds: float = 300.0

    @classmethod
    def from_env(cls, server_origin: str = "") -> "PublicCreationConfig":
        enabled = os.environ.get("SETTLETABLE_PUBLIC_CREATION_ENABLED", "0").lower() in ("1", "true", "yes")
        secret_key = os.environ.get("SETTLETABLE_TURNSTILE_SECRET_KEY")
        sitekey = os.environ.get("SETTLETABLE_TURNSTILE_SITEKEY")
        expected_action = os.environ.get("SETTLETABLE_TURNSTILE_ACTION", "public_create_meal")

        expected_hostname = os.environ.get("SETTLETABLE_TURNSTILE_HOSTNAME")
        if not expected_hostname and server_origin:
            parsed = urllib.parse.urlparse(server_origin)
            expected_hostname = parsed.hostname

        def _int_env(key: str, default: int) -> int:
            val = os.environ.get(key)
            if val:
                try:
                    return int(val)
                except ValueError:
                    pass
            return default

        return cls(
            enabled=enabled,
            turnstile_secret_key=secret_key.strip() if secret_key else None,
            turnstile_sitekey=sitekey.strip() if sitekey else None,
            turnstile_expected_action=expected_action,
            turnstile_expected_hostname=expected_hostname,
            max_total_meals=_int_env("SETTLETABLE_MAX_TOTAL_MEALS", 100),
            max_meals_per_day=_int_env("SETTLETABLE_MAX_MEALS_PER_DAY", 25),
            max_public_diners=_int_env("SETTLETABLE_MAX_PUBLIC_DINERS", 20),
            rate_limit_burst=_int_env("SETTLETABLE_RATE_LIMIT_BURST", 2),
            rate_limit_hourly=_int_env("SETTLETABLE_RATE_LIMIT_HOURLY", 5),
            rate_limit_daily=_int_env("SETTLETABLE_RATE_LIMIT_DAILY", 10),
        )


class PublicCreationGate:
    def __init__(
        self,
        config: PublicCreationConfig,
        clock: Callable[[], float] | None = None,
        siteverify_fn: Callable[[str, str, str | None, str | None], dict] | None = None,
    ):
        self.config = config
        self.clock = clock or time.time
        self._siteverify_fn = siteverify_fn

        self._lock = threading.Lock()
        # IP -> list of creation timestamps
        self._ip_creations: dict[str, list[float]] = {}
        # List of global creation timestamps
        self._global_creations: list[float] = []
        # (client_ip, idempotency_key) -> {'status': 'in_progress'|'completed', 'result': ..., 'time': float}
        self._idempotency_cache: dict[tuple[str, str], dict[str, Any]] = {}
        # token_hash -> expiry_timestamp
        self._spent_tokens: dict[str, float] = {}

    def _now(self) -> float:
        return self.clock()

    def get_client_ip(self, environ: dict) -> str:
        return extract_client_ip(environ)

    def check_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        """Check if client IP is within burst, hourly, and daily limits.
        
        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        now = self._now()
        with self._lock:
            # Prune global creations older than 24 hours
            cutoff_daily = now - self.config.daily_window_seconds
            self._global_creations = [t for t in self._global_creations if t > cutoff_daily]
            if len(self._global_creations) >= self.config.max_meals_per_day:
                oldest = self._global_creations[0]
                retry_after = max(1, int(oldest + self.config.daily_window_seconds - now))
                return False, retry_after

            # Client IP rate limits
            timestamps = self._ip_creations.get(client_ip, [])
            # Prune older than 24 hours
            timestamps = [t for t in timestamps if t > cutoff_daily]
            if not timestamps:
                self._ip_creations.pop(client_ip, None)
            else:
                self._ip_creations[client_ip] = timestamps

            # 1. Burst limit (e.g. 2 in 120s)
            cutoff_burst = now - self.config.burst_window_seconds
            burst_count = sum(1 for t in timestamps if t > cutoff_burst)
            if burst_count >= self.config.rate_limit_burst:
                oldest_burst = [t for t in timestamps if t > cutoff_burst][0]
                retry_after = max(1, int(oldest_burst + self.config.burst_window_seconds - now))
                return False, retry_after

            # 2. Hourly limit (e.g. 5 in 3600s)
            cutoff_hourly = now - self.config.hourly_window_seconds
            hourly_count = sum(1 for t in timestamps if t > cutoff_hourly)
            if hourly_count >= self.config.rate_limit_hourly:
                oldest_hourly = [t for t in timestamps if t > cutoff_hourly][0]
                retry_after = max(1, int(oldest_hourly + self.config.hourly_window_seconds - now))
                return False, retry_after

            # 3. Daily limit (e.g. 10 in 86400s)
            if len(timestamps) >= self.config.rate_limit_daily:
                oldest_daily = timestamps[0]
                retry_after = max(1, int(oldest_daily + self.config.daily_window_seconds - now))
                return False, retry_after

            return True, 0

    def record_creation_success(self, client_ip: str) -> None:
        """Record successful meal creation for IP and global rate tracking."""
        now = self._now()
        with self._lock:
            if client_ip not in self._ip_creations:
                self._ip_creations[client_ip] = []
            self._ip_creations[client_ip].append(now)
            self._global_creations.append(now)

            # Housekeeping: prune old entries if table grows large
            if len(self._ip_creations) > 2000:
                cutoff_daily = now - self.config.daily_window_seconds
                self._ip_creations = {
                    ip: [t for t in ts if t > cutoff_daily]
                    for ip, ts in self._ip_creations.items()
                    if any(t > cutoff_daily for t in ts)
                }

    def verify_turnstile(
        self,
        token: str | None,
        client_ip: str,
        idempotency_key: str | None = None,
    ) -> tuple[bool, str | None]:
        """Validate Cloudflare Turnstile token.
        
        Returns:
            (valid: bool, error_code: str | None)
        """
        # If secret key is not configured, Turnstile check is skipped (e.g. local dev/test)
        if not self.config.turnstile_secret_key:
            return True, None

        if not token or not isinstance(token, str):
            return False, "missing_turnstile_token"

        token = token.strip()
        if not token or len(token) > 2048:
            return False, "invalid_turnstile_token"

        now = self._now()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        with self._lock:
            # Prune spent tokens
            self._spent_tokens = {h: exp for h, exp in self._spent_tokens.items() if exp > now}
            if token_hash in self._spent_tokens:
                return False, "turnstile_token_reused"

        # Perform siteverify call
        res = self._call_siteverify(token, client_ip, idempotency_key)
        if not res or not res.get("success"):
            err_codes = res.get("error-codes", []) if res else []
            if "timeout-or-duplicate" in err_codes:
                return False, "turnstile_token_reused"
            return False, "turnstile_verification_failed"

        # Verify action if expected
        if self.config.turnstile_expected_action:
            action = res.get("action")
            if action != self.config.turnstile_expected_action:
                logger.warning("Turnstile action mismatch: expected '%s', got '%s'", self.config.turnstile_expected_action, action)
                return False, "turnstile_action_mismatch"

        # Verify hostname if expected
        if self.config.turnstile_expected_hostname:
            hostname = res.get("hostname")
            if hostname != self.config.turnstile_expected_hostname:
                logger.warning("Turnstile hostname mismatch: expected '%s', got '%s'", self.config.turnstile_expected_hostname, hostname)
                return False, "turnstile_hostname_mismatch"

        # Record spent token to prevent replay
        with self._lock:
            self._spent_tokens[token_hash] = now + self.config.token_replay_ttl_seconds

        return True, None

    def _call_siteverify(self, token: str, client_ip: str, idempotency_key: str | None) -> dict:
        """Call Turnstile siteverify API or custom verification handler."""
        if self._siteverify_fn is not None:
            return self._siteverify_fn(self.config.turnstile_secret_key, token, client_ip, idempotency_key)

        secret = self.config.turnstile_secret_key or ""

        # Cloudflare test secret key handling for offline / local test environments
        if secret == CF_TEST_SECRET_ALWAYS_PASS:
            return {
                "success": True,
                "action": self.config.turnstile_expected_action,
                "hostname": self.config.turnstile_expected_hostname or "localhost",
            }
        elif secret == CF_TEST_SECRET_ALWAYS_FAIL:
            return {"success": False, "error-codes": ["invalid-input-response"]}
        elif secret == CF_TEST_SECRET_DUPLICATE:
            return {"success": False, "error-codes": ["timeout-or-duplicate"]}

        data = {
            "secret": secret,
            "response": token,
            "remoteip": client_ip,
        }
        if idempotency_key:
            data["idempotency_key"] = idempotency_key

        payload = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(
            TURNSTILE_SITEVERIFY_URL,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "SettleTable-Turnstile-Verifier/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            logger.error("Turnstile Siteverify network/parse error: %s", e)
            return {"success": False, "error-codes": ["internal-verification-error"]}

    def check_idempotency(self, client_ip: str, idempotency_key: str | None) -> tuple[str, dict | None]:
        """Check if an idempotency key is new, in-progress, or already completed.
        
        Returns:
            (status: 'new' | 'in_progress' | 'completed', cached_result: dict | None)
        """
        if not idempotency_key:
            return "new", None

        now = self._now()
        cache_key = (client_ip, idempotency_key)
        with self._lock:
            # Prune expired idempotency entries
            cutoff = now - self.config.idempotency_ttl_seconds
            self._idempotency_cache = {
                k: v for k, v in self._idempotency_cache.items() if v.get("time", 0) > cutoff
            }

            entry = self._idempotency_cache.get(cache_key)
            if entry:
                if entry["status"] == "in_progress":
                    return "in_progress", None
                elif entry["status"] == "completed":
                    return "completed", entry["result"]

            # Mark in-progress
            self._idempotency_cache[cache_key] = {
                "status": "in_progress",
                "time": now,
            }
            return "new", None

    def store_idempotency_result(self, client_ip: str, idempotency_key: str | None, result: dict) -> None:
        if not idempotency_key:
            return
        now = self._now()
        cache_key = (client_ip, idempotency_key)
        with self._lock:
            self._idempotency_cache[cache_key] = {
                "status": "completed",
                "result": result,
                "time": now,
            }

    def clear_idempotency_entry(self, client_ip: str, idempotency_key: str | None) -> None:
        if not idempotency_key:
            return
        cache_key = (client_ip, idempotency_key)
        with self._lock:
            self._idempotency_cache.pop(cache_key, None)

    def check_capacity(self, authority: Any) -> tuple[bool, str | None]:
        """Check whether the server has reached maximum meal capacity."""
        try:
            total_count = authority.get_meals_count()
        except Exception as e:
            logger.error("Failed to query meals count from authority: %s", e)
            return False, "storage_error"

        if total_count >= self.config.max_total_meals:
            logger.warning("Public meal creation rejected: capacity limit reached (%d >= %d)", total_count, self.config.max_total_meals)
            return False, "capacity_exceeded"

        return True, None

    def validate_inputs(
        self,
        meal_title: Any,
        organizer_name: Any,
        raw_diners: Any,
    ) -> tuple[str, str, list[str]]:
        """Validate and sanitize public meal creation parameters.
        
        Returns:
            (clean_title: str, clean_organizer_name: str, clean_diner_names: list[str])
        """
        if not isinstance(meal_title, str) or not meal_title.strip():
            raise ValueError("invalid_input")
        title = meal_title.strip()
        if len(title) > 60:
            raise ValueError("invalid_input")
        # Reject control characters
        if any(unicodedata.category(c).startswith("C") for c in title):
            raise ValueError("invalid_input")

        if not isinstance(organizer_name, str) or not organizer_name.strip():
            raise ValueError("invalid_input")
        org_name = organizer_name.strip()
        if len(org_name) > 40:
            raise ValueError("invalid_input")
        if any(unicodedata.category(c).startswith("C") for c in org_name):
            raise ValueError("invalid_input")

        diner_names: list[str] = []
        if raw_diners is not None:
            if isinstance(raw_diners, str):
                parts = [d.strip() for d in raw_diners.split(",") if d.strip()]
            elif isinstance(raw_diners, list):
                parts = [d.strip() for d in raw_diners if isinstance(d, str) and d.strip()]
            else:
                raise ValueError("invalid_input")

            for name in parts:
                if len(name) > 40 or any(unicodedata.category(c).startswith("C") for c in name):
                    raise ValueError("invalid_input")
                diner_names.append(name)

        total_diners = 1 + len(diner_names)
        if total_diners > self.config.max_public_diners:
            raise ValueError("invalid_input")

        # Collision check across all participant names (case-insensitive)
        all_names_lower = [org_name.lower()] + [d.lower() for d in diner_names]
        if len(all_names_lower) != len(set(all_names_lower)):
            raise ValueError("ambiguous_participant_name")

        return title, org_name, diner_names

    def generate_meal_id(
        self,
        meal_title: str,
        authority: Any,
        custom_meal_id: str | None = None,
        is_loopback: bool = False,
    ) -> str:
        """Generate a cryptographically unguessable, collision-resistant meal ID.
        
        Combines a human-friendly ASCII slug with 10 random hex characters (40 bits of entropy).
        Example: 'friday-hotpot-a8f2k9b4c1'

        For trusted loopback callers only (without proxy headers), an explicit custom_meal_id
        is accepted if valid and not already existing.
        """
        if is_loopback and custom_meal_id and isinstance(custom_meal_id, str):
            clean_custom = custom_meal_id.strip()
            if len(clean_custom) <= 64 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", clean_custom):
                if not authority.meal_exists(clean_custom):
                    return clean_custom

        # Normalize to ASCII slug
        normalized = unicodedata.normalize("NFKD", meal_title)
        ascii_clean = normalized.encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_clean).strip("-")
        if not slug:
            slug = "meal"
        slug = slug[:24].rstrip("-")
        if not slug:
            slug = "meal"

        # Attempt up to 5 times to generate unique unguessable ID
        for _ in range(5):
            entropy = secrets.token_hex(5)  # 10 chars
            candidate = f"{slug}-{entropy}"
            if len(candidate) <= 64 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", candidate):
                if not authority.meal_exists(candidate):
                    return candidate

        # Fallback to high-entropy URL-safe token
        return f"meal-{secrets.token_urlsafe(12)}"
