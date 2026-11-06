"""Bounded same-origin transport adapter for SettleTable Authority.

Implements a defense-in-depth HTTP interface with strict wire boundary limits,
CSRF mitigation, host-only secure cookies, and unauthenticated landing separation.
"""
from dataclasses import asdict, is_dataclass
from fractions import Fraction
import http.cookies
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import unicodedata
from urllib.parse import urlparse, parse_qs

from settletable.authority import (
    Authority, AuthorityError, Participant,
    ReplaceReceipt, SetOwnQuantity, AssignParticipantQuantity, SetItemAllocations, AllocationSpec, ReviewReceipt, Finalize,
    RevokeInvitation, RevokeSession, RevokeMembership,
    RecordContribution, ReverseContribution,
    RecordTransfer, ReverseTransfer,
    Receipt, ReceiptItem, ReceiptAdjustment,
)

# Status code mappings per Section 5 of SPEC.md
STATUS_MAP = {
    # 400 Bad Request
    'invalid_input': 400,
    'invalid_join_target': 400,
    'participant_inactive': 400,
    'join_request_expired': 400,
    'invalid_join_request': 400,
    'invalid_token': 400,
    'malformed_json': 400,
    'duplicate_key': 400,
    'invalid_number': 400,
    'missing_action_header': 400,
    'conflicting_credentials': 400,
    'malformed_request': 400,
    'invalid_host': 400,
    'invalid_command_kind': 400,
    'missing_receipt': 400,
    'missing_amount': 400,
    'subtotal_mismatch': 400,
    'receipt_total_mismatch': 400,
    'discount_over_base': 400,
    'zero_base': 400,
    'pending_claim': 400,
    'incomplete_quantity': 400,
    'quantity_capacity': 400,
    'claim_missing': 400,
    'unknown_item': 400,
    'review_required': 400,
    'calculation_rejected': 400,
    'unsupported_command': 400,
    'invalid_invitation': 400,
    'invalid_organizer_claim': 400,
    'organizer_claim_expired': 410,
    'organizer_claim_consumed': 409,
    'organizer_claim_revoked': 409,
    'organizer_not_found': 404,
    'invalid_image': 400,
    # 401 Unauthorized
    'invalid_session': 401,
    # 403 Forbidden
    'forbidden': 403,
    'origin_mismatch': 403,
    'organizer_join_prohibited': 403,
    # 404 Not Found
    'participant_not_found': 404,
    'join_request_not_found': 404,
    'meal_not_found': 404,
    'photo_not_found': 404,
    # 409 Conflict
    'ambiguous_participant_name': 409,
    'join_request_conflict': 409,
    'active_join_request_exists': 409,
    'command_conflict': 409,
    'revision_conflict': 409,
    'financial_revision_conflict': 409,
    'item_revision_conflict': 409,
    'receipt_digest_conflict': 409,
    'active_invitation_exists': 409,
    'already_revoked': 409,
    'finalized': 409,
    'meal_not_finalized': 409,
    'not_finalized': 409,
    'invalid_finalization_basis': 409,
    'overpayment_prohibited': 400,
    'invalid_contribution_status': 409,
    'contribution_not_found': 404,
    'self_transfer_prohibited': 400,
    'not_a_debtor': 400,
    'not_a_creditor': 400,
    'over_settlement_prohibited': 400,
    'transfer_not_found': 404,
    'invalid_transfer_status': 409,
    'active_peer_transfers_exist': 409,
    'invalid_participant': 400,
    'simulation_conflict': 409,
    'export_in_progress': 409,
    'claimed_item_deletion': 409,
    'retired_source': 409,
    'source_kind_conflict': 409,
    'meal_exists': 409,
    # 411 Length Required
    'missing_content_length': 411,
    # 413 Payload Too Large
    'payload_too_large': 413,
    # 429 Too Many Requests
    'resource_limit': 429,
    'notion_rate_limited': 429,
    # 431 Request Header Fields Too Large
    'header_too_large': 431,
    # 500 Internal Server Error
    'storage_error': 500,
    'photo_corrupted': 500,
    'internal_error': 500,
    # 502 Bad Gateway
    'notion_error': 502,
    # 503 Service Unavailable
    'commit_uncertain': 503,
    'busy': 503,
    'ocr_unavailable': 503,
    'simulation_disabled': 503,
    'notion_auth_error': 400,
}

MAX_BODY_BYTES = 1_048_576  # 1 MB
MAX_IMAGE_BYTES = 5_242_880  # 5 MB
MAX_HEADER_LINE_BYTES = 4_096  # 4 KB
MAX_TOTAL_HEADERS_BYTES = 16_384  # 16 KB
MAX_JSON_DEPTH = 10
MAX_INT_DIGITS = 19
TOKEN_REDACT_REGEX = re.compile(r'(/api/(?:meals/[^/]+/)?(?:invitations|organizer-claims)/)[A-Za-z0-9_-]{43}')
STATIC_DIR = Path(__file__).parent / 'static'
STATIC_FILES = {
    'style.css': 'text/css; charset=utf-8',
    'app.js': 'application/javascript; charset=utf-8',
    'favicon.svg': 'image/svg+xml',
}


def redact_log_string(s: str) -> str:
    # 1. Redact API token paths (invitations and organizer claims)
    s = re.sub(r'(/api/(?:meals/[^/]+/)?invitations/)[A-Za-z0-9_-]{43}', r'\1[REDACTED]', s)
    s = re.sub(r'(/api/organizer-claims/)[A-Za-z0-9_-]{43}', r'\1[REDACTED]', s)
    s = re.sub(r'(/api/meals/[^/]+/organizer-claims/)[A-Za-z0-9_-]{43}(/claim)?', r'\1[REDACTED]\2', s)
    # 2. Redact HTML landing routes with tokens
    s = re.sub(r'(/(?:claim-organizer|claim|invite)/)[A-Za-z0-9_-]{43}', r'\1[REDACTED]', s)
    # 3. HTTP Authorization headers
    s = re.sub(r'(Bearer\s+)[A-Za-z0-9_-]+', r'\1[REDACTED]', s, flags=re.IGNORECASE)
    # 4. Cookies
    s = re.sub(r'(settletable_session=)[A-Za-z0-9_-]+', r'\1[REDACTED]', s)
    # 5. Notion and integration tokens
    s = re.sub(r'(secret_|ntn_)[A-Za-z0-9_-]{10,}', r'\1[REDACTED]', s)
    # 6. Query strings: token, claim_token, cred, credential
    s = re.sub(r'([?&](?:token|claim_token|cred|credential)=)[A-Za-z0-9_-]+', r'\1[REDACTED]', s, flags=re.IGNORECASE)
    # 7. JSON fields in logged request/response payloads or diagnostic messages
    s = re.sub(r'"(?:token|claim_token|cred|credential|organizer_credential|settletable_session)"\s*:\s*"[^"]+"', r'"token":"[REDACTED]"', s)
    return s


class TransportError(Exception):
    def __init__(self, code, status=None):
        super().__init__(code)
        self.code = code
        self.status = status or STATUS_MAP.get(code, 400)


def _reject_duplicates(pairs):
    seen = set()
    result = {}
    for key, val in pairs:
        norm_key = unicodedata.normalize('NFC', key)
        if norm_key in seen:
            raise TransportError('duplicate_key', 400)
        seen.add(norm_key)
        result[key] = val
    return result


def _reject_float(val):
    raise TransportError('invalid_number', 400)


def _reject_constant(val):
    raise TransportError('invalid_number', 400)


def _check_nesting_depth(s):
    depth = 0
    max_d = 0
    in_str = False
    esc = False
    for char in s:
        if in_str:
            if esc:
                esc = False
            elif char == '\\':
                esc = True
            elif char == '"':
                in_str = False
        else:
            if char == '"':
                in_str = True
            elif char in ('{', '['):
                depth += 1
                if depth > max_d:
                    max_d = depth
            elif char in ('}', ']'):
                depth -= 1
    return max_d


def parse_strict_json(body_bytes):
    if len(body_bytes) > MAX_BODY_BYTES:
        raise TransportError('payload_too_large', 413)
    try:
        text = body_bytes.decode('utf-8')
    except UnicodeDecodeError:
        raise TransportError('malformed_json', 400) from None

    if _check_nesting_depth(text) > MAX_JSON_DEPTH:
        raise TransportError('malformed_json', 400)

    try:
        data = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except TransportError:
        raise
    except Exception:
        raise TransportError('malformed_json', 400) from None

    # Validate integer sizes to prevent quadratic CPU attacks
    _validate_int_bounds(data)
    return data


def _validate_int_bounds(val):
    if isinstance(val, int) and not isinstance(val, bool):
        if len(str(abs(val))) > MAX_INT_DIGITS:
            raise TransportError('invalid_number', 400)
    elif isinstance(val, dict):
        for v in val.values():
            _validate_int_bounds(v)
    elif isinstance(val, list):
        for item in val:
            _validate_int_bounds(item)


def json_serializer(obj):
    if isinstance(obj, Fraction):
        return [obj.numerator, obj.denominator]
    if is_dataclass(obj):
        return asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def serialize_json(data):
    return json.dumps(data, default=json_serializer, separators=(',', ':')).encode('utf-8')


class SettleTableApp:
    def __init__(self, db_path, allowed_hosts=('localhost:8000', '127.0.0.1:8000', 'testserver'),
                 server_origin='http://localhost:8000', clock=None, logger=None, ocr_engine=None,
                 notion_client=None, allow_sync_export=False, simulation_config=None, simulation_client=None,
                 storage_dir=None, session_ttl=None):
        self.db_path = str(db_path)
        self.storage_dir = Path(storage_dir) if storage_dir is not None else None
        self.allowed_hosts = set(allowed_hosts)
        self.server_origin = server_origin.rstrip('/')
        self.clock = clock if clock is not None else time.time
        self.logger = logger
        self.ocr_engine = ocr_engine
        self.notion_client = notion_client
        self.session_ttl = session_ttl
        from settletable.payment_simulation import SimulationConfig, KaiPayClient
        self.simulation_config = simulation_config if simulation_config is not None else SimulationConfig.from_env()
        self.simulation_client = (simulation_client or KaiPayClient(self.simulation_config)) if self.simulation_config else None
        self.allow_sync_export = (
            bool(allow_sync_export)
            or os.environ.get('SETTLETABLE_ALLOW_SYNC_EXPORT') == '1'
        )
        self._local = threading.local()

    def _get_session_ttl(self):
        if getattr(self, 'session_ttl', None) is not None:
            return self.session_ttl
        val = os.environ.get('SETTLETABLE_SESSION_TTL')
        if val:
            try:
                ttl = int(val)
                if 1 <= ttl <= 2592000:
                    return ttl
            except ValueError:
                pass
        return 604800

    def get_ocr_engine(self):
        if self.ocr_engine is not None:
            return self.ocr_engine
        try:
            from settletable.ocr import RapidOcrEngine
            return RapidOcrEngine()
        except Exception:
            raise TransportError('ocr_unavailable', 503)

    def get_notion_client(self):
        if self.notion_client is not None:
            return self.notion_client
        from settletable.notion import NotionHttpClient
        return NotionHttpClient()

    def get_authority(self):
        if not hasattr(self._local, 'authority') or self._local.authority is None:
            self._local.authority = Authority(self.db_path, clock=self.clock, storage_dir=self.storage_dir)
        return self._local.authority

    def close(self):
        if hasattr(self._local, 'authority') and self._local.authority is not None:
            try:
                self._local.authority.close()
            except Exception:
                pass
            self._local.authority = None

    def __call__(self, environ, start_response):
        try:
            status_code, headers, body_bytes = self._dispatch(environ)
        except TransportError as e:
            status_code, headers, body_bytes = self._format_error(e.code, e.status)
        except AuthorityError as e:
            status_code = STATUS_MAP.get(e.code, 500)
            status_code, headers, body_bytes = self._format_error(e.code, status_code)
        except Exception:
            status_code, headers, body_bytes = self._format_error('internal_error', 500)

        if self.logger:
            raw_path = environ.get('PATH_INFO', '/')
            method = environ.get('REQUEST_METHOD', 'GET').upper()
            safe_path = redact_log_string(raw_path)
            qs = environ.get('QUERY_STRING')
            if qs:
                safe_qs = redact_log_string(qs)
                safe_path = f"{safe_path}?{safe_qs}"
            self.logger(f"{method} {safe_path} -> {status_code}")

        status_line = f"{status_code} {self._status_text(status_code)}"
        start_response(status_line, headers)
        return [body_bytes]

    def _status_text(self, code):
        texts = {
            200: 'OK', 201: 'Created',
            400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
            404: 'Not Found', 409: 'Conflict', 411: 'Length Required',
            413: 'Payload Too Large', 429: 'Too Many Requests',
            431: 'Request Header Fields Too Large',
            500: 'Internal Server Error', 501: 'Not Implemented',
            503: 'Service Unavailable',
        }
        return texts.get(code, 'Unknown')

    def _format_error(self, code, status_code):
        headers = [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer'),
        ]
        if status_code == 401:
            headers.append(('WWW-Authenticate', 'Bearer error="invalid_token"'))
        elif status_code == 503:
            headers.append(('Retry-After', '1'))

        payload = {'ok': False, 'error': code, 'detail': None}
        return status_code, headers, serialize_json(payload)

    def _static_headers(self, content_type, cache_control='no-cache'):
        return [
            ('Content-Type', content_type),
            ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer'),
            ('Cache-Control', cache_control),
        ]

    def _dispatch(self, environ):
        method = environ.get('REQUEST_METHOD', 'GET').upper()
        raw_path = environ.get('PATH_INFO', '/')
        if '?' in raw_path:
            raw_path, qs_extra = raw_path.split('?', 1)
            if not environ.get('QUERY_STRING'):
                environ['QUERY_STRING'] = qs_extra
        path = raw_path.rstrip('/') or '/'

        # 0. Request Header boundaries (single line <= 4KB, total block <= 16KB)
        total_header_bytes = 0
        for k, v in environ.items():
            if k.startswith('HTTP_') or k in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                line_len = len(k) + len(str(v))
                if line_len > MAX_HEADER_LINE_BYTES:
                    raise TransportError('header_too_large', 431)
                total_header_bytes += line_len
        if total_header_bytes > MAX_TOTAL_HEADERS_BYTES:
            raise TransportError('header_too_large', 431)

        # Health check probe for container orchestrators and reverse proxies
        if method == 'GET' and path in ('/healthz', '/api/healthz'):
            return 200, self._default_headers(), serialize_json({'ok': True, 'status': 'healthy'})

        # 1. Host header validation
        host = environ.get('HTTP_HOST', '')
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise TransportError('invalid_host', 400)

        # 2. Extract credentials
        auth_header = environ.get('HTTP_AUTHORIZATION', '')
        bearer_cred = None
        if auth_header[:7].lower() == 'bearer ':
            bearer_cred = auth_header[7:].strip()

        cookie_header = environ.get('HTTP_COOKIE', '')
        cookie_cred = None
        if cookie_header:
            cookie = http.cookies.SimpleCookie()
            try:
                cookie.load(cookie_header)
                if 'settletable_session' in cookie:
                    cookie_cred = cookie['settletable_session'].value
            except Exception:
                pass

        if bearer_cred and cookie_cred and bearer_cred != cookie_cred:
            raise TransportError('conflicting_credentials', 400)

        active_cred = bearer_cred or cookie_cred
        used_cookie = bool(cookie_cred)

        # 3. CSRF & Action check on mutating requests (POST, DELETE)
        # Note: POST /api/organizer-claims/inspect is an unauthenticated, read-only query
        # using POST solely to keep the claim token in the request body rather than the URL line.
        is_read_only_post = bool(method == 'POST' and path == '/api/organizer-claims/inspect')
        if method in ('POST', 'DELETE') and not is_read_only_post:
            # Missing or chunked body check
            cl_header = environ.get('CONTENT_LENGTH')
            te_header = environ.get('HTTP_TRANSFER_ENCODING')

            if cl_header and te_header:
                raise TransportError('malformed_request', 400)
            if te_header:
                raise TransportError('not_implemented', 501)

            # Mandatory custom header check for all mutating endpoints
            action_hdr = environ.get('HTTP_X_SETTLETABLE_ACTION')
            if action_hdr != '1':
                raise TransportError('missing_action_header', 400)

            # Origin check: required if cookie was used OR if unauthenticated browser request
            if used_cookie or not bearer_cred:
                origin = environ.get('HTTP_ORIGIN')
                if origin:
                    if origin == 'null' or origin.rstrip('/') != self.server_origin:
                        raise TransportError('origin_mismatch', 403)
                else:
                    referer = environ.get('HTTP_REFERER')
                    if referer:
                        parsed = urlparse(referer)
                        ref_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
                        if ref_origin != self.server_origin:
                            raise TransportError('origin_mismatch', 403)
                    else:
                        # Missing both Origin and Referer on browser-context mutating request
                        raise TransportError('origin_mismatch', 403)

        # Read body for POST
        body_data = None
        raw_image_body = None
        is_image_upload = bool(method == 'POST' and (
            re.fullmatch(r'/api/meals/[A-Za-z0-9_-]+/ocr/extract', path) or
            re.fullmatch(r'/api/meals/[A-Za-z0-9_-]+/receipt/photo', path)
        ))
        if method == 'POST':
            cl = environ.get('CONTENT_LENGTH')
            if not cl:
                raise TransportError('missing_content_length', 411)
            try:
                length = int(cl)
            except ValueError:
                raise TransportError('malformed_request', 400)
            max_limit = MAX_IMAGE_BYTES if is_image_upload else MAX_BODY_BYTES
            if length > max_limit:
                raise TransportError('payload_too_large', 413)

            wsgi_input = environ.get('wsgi.input')
            raw_body = wsgi_input.read(length) if wsgi_input else b''
            if len(raw_body) != length:
                raise TransportError('malformed_request', 400)

            if is_image_upload:
                raw_image_body = raw_body
            else:
                body_data = parse_strict_json(raw_body) if raw_body else {}

        # 4. Route matching
        authority = self.get_authority()

        # Static asset serving (HTML shell and static files)
        if method == 'GET':
            if path == '/':
                index_path = STATIC_DIR / 'index.html'
                if index_path.exists():
                    return 200, self._static_headers('text/html; charset=utf-8', 'no-store, no-cache, must-revalidate'), index_path.read_bytes()
                raise TransportError('not_found', 404)

            # GET /invite/{token} serves HTML shell for invitation landing
            m_inv_shell = re.fullmatch(r'/invite/([A-Za-z0-9_-]{43})', path)
            if m_inv_shell:
                index_path = STATIC_DIR / 'index.html'
                if index_path.exists():
                    return 200, self._static_headers('text/html; charset=utf-8', 'no-store, no-cache, must-revalidate'), index_path.read_bytes()
                raise TransportError('not_found', 404)

            # GET /join/{meal_id} serves HTML shell for general meal join landing
            m_join_shell = re.fullmatch(r'/join/([A-Za-z0-9_-]+)', path)
            if m_join_shell:
                index_path = STATIC_DIR / 'index.html'
                if index_path.exists():
                    return 200, self._static_headers('text/html; charset=utf-8', 'no-store, no-cache, must-revalidate'), index_path.read_bytes()
                raise TransportError('not_found', 404)

            # GET /claim-organizer/{token} or /claim/{token} serves HTML shell for organizer claim landing
            m_claim_shell = re.fullmatch(r'/(?:claim-organizer|claim)/([A-Za-z0-9_-]{43})', path)
            if m_claim_shell:
                index_path = STATIC_DIR / 'index.html'
                if index_path.exists():
                    return 200, self._static_headers('text/html; charset=utf-8', 'no-store, no-cache, must-revalidate'), index_path.read_bytes()
                raise TransportError('not_found', 404)

            # GET /static/{filename}
            m_stat = re.fullmatch(r'/static/([A-Za-z0-9_.-]+)', path)
            if m_stat:
                filename = m_stat.group(1)
                if filename in STATIC_FILES:
                    fpath = STATIC_DIR / filename
                    if fpath.exists():
                        return 200, self._static_headers(STATIC_FILES[filename], 'no-cache'), fpath.read_bytes()
                raise TransportError('not_found', 404)

            if path == '/favicon.ico':
                fav = STATIC_DIR / 'favicon.svg'
                if fav.exists():
                    return 200, self._static_headers('image/svg+xml', 'no-cache'), fav.read_bytes()
                return 204, self._default_headers(), b''

        # Unauthenticated landing GET /api/invitations/{token}
        m = re.fullmatch(r'/api/invitations/([A-Za-z0-9_-]{43})', path)
        if m and method == 'GET':
            token = m.group(1)
            res = authority.inspect_invitation(token)
            out = {
                'ok': True,
                'valid': res.valid,
                'meal_id': res.meal_id,
                'participant_name': res.participant_name,
                'expires': res.expires,
                'reason': res.reason,
            }
            return 200, self._default_headers(), serialize_json(out)

        # Organizer claim inspection:
        # 1. POST /api/organizer-claims/inspect (token in JSON body to prevent URL logging)
        if path == '/api/organizer-claims/inspect' and method == 'POST':
            token = (body_data or {}).get('claim_token') or environ.get('HTTP_X_SETTLETABLE_CLAIM_TOKEN')
            if not token or not isinstance(token, str):
                raise TransportError('invalid_organizer_claim', 400)
            res = authority.inspect_organizer_claim(token)
            out = {
                'ok': True,
                'valid': res.valid,
                'meal_id': res.meal_id,
                'organizer_id': res.organizer_id,
                'organizer_name': res.organizer_name,
                'expires': res.expires,
                'reason': res.reason,
            }
            return 200, self._default_headers(), serialize_json(out)

        # 2. Legacy/direct GET /api/organizer-claims/{token}
        m_org_claim_inspect = re.fullmatch(r'/api/organizer-claims/([A-Za-z0-9_-]{43})', path)
        if m_org_claim_inspect and method == 'GET':
            token = m_org_claim_inspect.group(1)
            res = authority.inspect_organizer_claim(token)
            out = {
                'ok': True,
                'valid': res.valid,
                'meal_id': res.meal_id,
                'organizer_id': res.organizer_id,
                'organizer_name': res.organizer_name,
                'expires': res.expires,
                'reason': res.reason,
            }
            return 200, self._default_headers(), serialize_json(out)

        # Clear / Exit Session POST /api/session/clear or POST /api/meals/{meal_id}/session/exit
        if method == 'POST' and (path in ('/api/session/clear', '/api/session/exit') or re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/session/exit', path)):
            headers = self._default_headers()
            headers.append(('Set-Cookie', 'settletable_session=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT'))
            return 200, headers, serialize_json({'ok': True, 'cleared': True})

        # Redeem invitation POST /api/meals/{meal_id}/invitations/{token}/redeem
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/invitations/([A-Za-z0-9_-]{43})/redeem', path)
        if m and method == 'POST':
            meal_id, token = m.group(1), m.group(2)
            session_ttl = self._get_session_ttl()
            session_grant = authority.redeem_invitation(token, meal_id, session_ttl=session_ttl)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={session_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={session_ttl}'))
            out = {
                'ok': True,
                'meal_id': meal_id,
                'participant_id': session_grant.participant_id,
            }
            return 200, headers, serialize_json(out)

        # Create Join Request POST /api/meals/{meal_id}/join-requests
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/join-requests', path)
        if m and method == 'POST':
            meal_id = m.group(1)
            display_name = body_data.get('display_name')
            if not isinstance(display_name, str):
                raise TransportError('invalid_input', 400)
            req_id, token, part_id, name = authority.create_join_request(meal_id, display_name)
            headers = self._default_headers()
            out = {
                'ok': True,
                'request_id': req_id,
                'claim_token': token,
                'participant_id': part_id,
                'display_name': name,
                'status': 'pending',
            }
            return 201, headers, serialize_json(out)

        # Inspect Join Request GET /api/meals/{meal_id}/join-requests/{request_id}
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/join-requests/([A-Za-z0-9_-]+)', path)
        if m and method == 'GET':
            meal_id, request_id = m.group(1), m.group(2)
            qs = environ.get('QUERY_STRING', '')
            parsed_qs = parse_qs(qs)
            claim_token = parsed_qs.get('claim_token', [''])[0] or environ.get('HTTP_X_CLAIM_TOKEN', '')
            if not claim_token:
                raise TransportError('invalid_input', 400)
            info = authority.inspect_join_request(meal_id, request_id, claim_token)
            headers = self._default_headers()
            return 200, headers, serialize_json({'ok': True, **info})

        # Claim Join Request POST /api/meals/{meal_id}/join-requests/{request_id}/claim
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/join-requests/([A-Za-z0-9_-]+)/claim', path)
        if m and method == 'POST':
            meal_id, request_id = m.group(1), m.group(2)
            claim_token = body_data.get('claim_token')
            if not isinstance(claim_token, str):
                raise TransportError('invalid_input', 400)
            session_ttl = self._get_session_ttl()
            session_grant = authority.claim_join_request(meal_id, request_id, claim_token, session_ttl=session_ttl)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={session_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={session_ttl}'))
            out = {
                'ok': True,
                'meal_id': meal_id,
                'participant_id': session_grant.participant_id,
                'status': 'claimed',
            }
            return 200, headers, serialize_json(out)

        # Claim Organizer Session:
        # POST /api/meals/{meal_id}/organizer-claims/claim (token in JSON body to prevent URL logging) OR
        # POST /api/meals/{meal_id}/organizer-claims/{token}/claim (legacy URL path)
        m_org_claim_redeem_path = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/organizer-claims/([A-Za-z0-9_-]{43})/claim', path)
        m_org_claim_redeem_body = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/organizer-claims/claim', path)
        if (m_org_claim_redeem_path or m_org_claim_redeem_body) and method == 'POST':
            if m_org_claim_redeem_path:
                meal_id, token = m_org_claim_redeem_path.group(1), m_org_claim_redeem_path.group(2)
            else:
                meal_id = m_org_claim_redeem_body.group(1)
                token = (body_data or {}).get('claim_token') or environ.get('HTTP_X_SETTLETABLE_CLAIM_TOKEN')
                if not token or not isinstance(token, str):
                    raise TransportError('invalid_organizer_claim', 400)
            session_ttl = self._get_session_ttl()
            session_grant = authority.claim_organizer_session(token, meal_id, session_ttl=session_ttl)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={session_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={session_ttl}'))
            out = {
                'ok': True,
                'meal_id': meal_id,
                'participant_id': session_grant.participant_id,
                'status': 'claimed',
            }
            return 200, headers, serialize_json(out)

        # Bootstrap POST /api/meals/{meal_id}/bootstrap
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/bootstrap', path)
        if m and method == 'POST':
            # Ingress/Proxy header protection: a reverse proxy forwarding requests to loopback
            # would make untrusted external calls appear to originate from 127.0.0.1.
            # Reject if any proxy forwarding headers are present.
            proxy_headers = ('HTTP_X_FORWARDED_FOR', 'HTTP_X_FORWARDED_HOST',
                             'HTTP_X_FORWARDED_PROTO', 'HTTP_FORWARDED', 'HTTP_X_REAL_IP')
            if any(h in environ for h in proxy_headers):
                raise TransportError('forbidden', 403)

            remote_addr = environ.get('REMOTE_ADDR', '')
            if remote_addr not in ('127.0.0.1', '::1', 'localhost', 'testclient'):
                raise TransportError('forbidden', 403)
            meal_id = m.group(1)
            raw_participants = body_data.get('participants')
            if not isinstance(raw_participants, list) or not raw_participants:
                raise TransportError('invalid_input', 400)
            try:
                parts = []
                for p in raw_participants:
                    if not isinstance(p, dict):
                        raise TransportError('invalid_input', 400)
                    parts.append(Participant(p['id'], p['name'], p.get('organizer', False)))
            except (KeyError, TypeError):
                raise TransportError('invalid_input', 400)
            session_ttl = self._get_session_ttl()
            b_res = authority.bootstrap(meal_id, tuple(parts), session_ttl=session_ttl)
            organizer_session = next(s for s, p in zip(b_res.sessions, parts) if p.organizer)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={organizer_session.credential}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={session_ttl}'))
            # Defense against credential exposure: Never return all participant credentials
            # to an untrusted client. Only the provisioned organizer session is returned.
            # Diners must join via explicit invitations (issue_invitation -> redeem_invitation).
            out = {
                'ok': True,
                'meal_id': b_res.meal_id,
                'organizer_id': organizer_session.participant_id,
                'sessions': [{'participant_id': organizer_session.participant_id, 'credential': organizer_session.credential}],
            }
            if b_res.organizer_claim:
                out['organizer_claim'] = {
                    'token': b_res.organizer_claim.token,
                    'expires': b_res.organizer_claim.expires,
                    'claim_url': f"{self.server_origin}/#/claim-organizer/{b_res.organizer_claim.token}",
                }
            return 201, headers, serialize_json(out)

        # Snapshot GET /api/meals/{meal_id}/snapshot
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/snapshot', path)
        if m and method == 'GET':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            snapshot = authority.snapshot(active_cred, meal_id)
            out = asdict(snapshot)
            out['ok'] = True
            out['current_participant_id'] = part_id
            out['is_organizer'] = is_org
            out['payment_simulation_enabled'] = self.simulation_config is not None
            return 200, self._default_headers(), serialize_json(out)

        # Allocation simulation has its own organizer/self permission boundary.
        m_sim = re.fullmatch(r'/api/meals/([A-Za-z0-9][A-Za-z0-9_.:-]{0,63})/participants/([A-Za-z0-9][A-Za-z0-9_.:-]{0,63})/payment-simulation', path)
        if m_sim and method in ('POST', 'GET'):
            if not active_cred:
                raise TransportError('invalid_session', 401)
            if self.simulation_config is None:
                # Authenticate before disclosing even the feature's availability.
                authority.authenticate(active_cred, m_sim.group(1))
                raise TransportError('simulation_disabled', 503)
            if method == 'POST' and body_data != {}:
                raise TransportError('invalid_input', 400)
            from settletable.payment_simulation import perform_simulation
            result = perform_simulation(authority, active_cred, *m_sim.groups(),
                                        self.simulation_config, self.simulation_client, initiate=method == 'POST')
            code = 202 if result['state'] in ('PENDING', 'REQUEST_UNKNOWN') else 200
            return code, self._default_headers(), serialize_json({'ok': True, 'payment_simulation': result})

        # Rotate Session POST /api/meals/{meal_id}/session/rotate
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/session/rotate', path)
        if m and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            session_ttl = self._get_session_ttl()
            new_grant = authority.rotate_session(active_cred, meal_id, session_ttl=session_ttl)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={new_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={session_ttl}'))
            out = {
                'ok': True,
                'participant_id': new_grant.participant_id,
            }
            # Only return raw bearer credential if request was authenticated via Bearer token (programmatic client).
            # Cookie-authenticated browser clients receive the credential strictly via HttpOnly cookie to prevent XSS exfiltration.
            if bearer_cred and not used_cookie:
                out['credential'] = new_grant.credential
            return 200, headers, serialize_json(out)

        # Issue Organizer Recovery Link POST /api/meals/{meal_id}/organizer-claims
        m_org_claim_issue = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/organizer-claims', path)
        if m_org_claim_issue and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_org_claim_issue.group(1)
            claim_ttl = body_data.get('claim_ttl', self._get_session_ttl())
            if not isinstance(claim_ttl, int) or not (1 <= claim_ttl <= 2592000):
                raise TransportError('invalid_input', 400)
            grant = authority.issue_organizer_recovery(active_cred, meal_id, claim_ttl=claim_ttl)
            out = {
                'ok': True,
                'meal_id': grant.meal_id,
                'token': grant.token,
                'expires': grant.expires,
                'issue_id': grant.issue_id,
                'claim_url': f"{self.server_origin}/#/claim-organizer/{grant.token}",
            }
            return 201, self._default_headers(), serialize_json(out)

        # Issue Invitation POST /api/meals/{meal_id}/invitations
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/invitations', path)
        if m and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            participant_id = body_data.get('participant_id')
            invite_ttl = body_data.get('invite_ttl', 86400)
            issue_id = body_data.get('issue_id')
            grant = authority.issue_invitation(active_cred, meal_id, participant_id,
                                               invite_ttl=invite_ttl, issue_id=issue_id)
            out = {
                'ok': True,
                'meal_id': grant.meal_id,
                'participant_id': grant.participant_id,
                'token': grant.token,
                'expires': grant.expires,
            }
            return 201, self._default_headers(), serialize_json(out)

        # List Join Requests GET /api/meals/{meal_id}/join-requests
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/join-requests', path)
        if m and method == 'GET':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            reqs = authority.list_join_requests(active_cred, meal_id)
            out = {
                'ok': True,
                'join_requests': [asdict(r) for r in reqs],
            }
            return 200, self._default_headers(), serialize_json(out)

        # Review Join Request POST /api/meals/{meal_id}/join-requests/{request_id}/review
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/join-requests/([A-Za-z0-9_-]+)/review', path)
        if m and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id, request_id = m.group(1), m.group(2)
            action = body_data.get('action')
            if not isinstance(action, str):
                raise TransportError('invalid_input', 400)
            status = authority.review_join_request(active_cred, meal_id, request_id, action)
            out = {
                'ok': True,
                'request_id': request_id,
                'status': status,
            }
            return 200, self._default_headers(), serialize_json(out)

        # Apply Command POST /api/meals/{meal_id}/apply
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/apply', path)
        if m and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            # Earlier transports normalized invalid explicit scopes. Permit only
            # exact accepted-command replay under that historical normalization;
            # never use it to accept a new silently widened adjustment.
            legacy_scope = False
            omitted_scope_ids = []
            if isinstance(body_data, dict) and body_data.get('kind') == 'ReplaceReceipt':
                rcpt = body_data.get('receipt')
                if isinstance(rcpt, dict):
                    raw_items = rcpt.get('items', [])
                    raw_adjustments = rcpt.get('adjustments', [])
                    if not isinstance(raw_items, list) or not isinstance(raw_adjustments, list):
                        raise TransportError('invalid_input', 400)
                    ids = {i.get('id') for i in raw_items if isinstance(i, dict) and isinstance(i.get('id'), str)}
                    for index, adj in enumerate(raw_adjustments, start=1):
                        if isinstance(adj, dict) and adj.get('scope_mode') is None and adj.get('eligible_item_ids') is None:
                            omitted_scope_ids.append(str(adj.get('id') or f'adj-{index}'))
                        if isinstance(adj, dict) and adj.get('scope_mode') is None and adj.get('eligible_item_ids') is not None:
                            scope = adj['eligible_item_ids']
                            if not isinstance(scope, list) or not scope or any(not isinstance(i, str) or i not in ids for i in scope):
                                legacy_scope = True
            command = self._build_command(body_data, legacy_scope=legacy_scope)
            accepted = authority.apply(active_cred, meal_id, command, replay_only=legacy_scope,
                                       omitted_scope_ids=tuple(omitted_scope_ids))
            out = {
                'ok': True,
                'kind': accepted.kind,
                'revision': accepted.revision,
                'financial_revision': accepted.financial_revision,
                'changed_claims': accepted.changed_claims,
                'calculation': accepted.calculation,
            }
            if getattr(accepted, 'contribution_id', None) is not None:
                out['contribution_id'] = accepted.contribution_id
            if getattr(accepted, 'transfer_id', None) is not None:
                out['transfer_id'] = accepted.transfer_id
            return 200, self._default_headers(), serialize_json(out)

        # Extract Receipt OCR POST /api/meals/{meal_id}/ocr/extract
        m_ocr = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/ocr/extract', path)
        if m_ocr and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_ocr.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)

            ct = environ.get('CONTENT_TYPE', '').split(';')[0].strip().lower()
            if ct not in ('image/jpeg', 'image/png', 'image/webp', 'image/jpg'):
                raise TransportError('invalid_image', 400)

            engine = self.get_ocr_engine()
            try:
                from settletable.ocr import parse_malaysian_receipt, OcrUnavailableError, InvalidImageError, validate_image_payload
                detected_fmt, width, height = validate_image_payload(raw_image_body or b'', expected_mime=ct)
                photo_meta = authority.store_receipt_photo(active_cred, meal_id, raw_image_body or b'', ct, width, height)
                lines = engine.recognize(raw_image_body or b'')
                candidate = parse_malaysian_receipt(lines)
                out = {
                    'ok': True,
                    'candidate': candidate.to_dict(),
                    'photo': photo_meta,
                }
                return 200, self._default_headers(), serialize_json(out)
            except InvalidImageError:
                raise TransportError('invalid_image', 400) from None
            except OcrUnavailableError:
                raise TransportError('ocr_unavailable', 503) from None

        # Upload Receipt Photo POST /api/meals/{meal_id}/receipt/photo
        m_photo_post = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/receipt/photo', path)
        if m_photo_post and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_photo_post.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)

            ct = environ.get('CONTENT_TYPE', '').split(';')[0].strip().lower()
            if ct not in ('image/jpeg', 'image/png', 'image/webp', 'image/jpg'):
                raise TransportError('invalid_image', 400)

            try:
                from settletable.ocr import InvalidImageError, validate_image_payload
                detected_fmt, width, height = validate_image_payload(raw_image_body or b'', expected_mime=ct)
                photo_meta = authority.store_receipt_photo(active_cred, meal_id, raw_image_body or b'', ct, width, height)
                return 200, self._default_headers(), serialize_json({'ok': True, 'photo': photo_meta})
            except InvalidImageError:
                raise TransportError('invalid_image', 400) from None

        # Get Receipt Photo GET /api/meals/{meal_id}/receipt/photo
        m_photo_get = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/receipt/photo', path)
        if m_photo_get and method == 'GET':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_photo_get.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)

            img_bytes, meta = authority.get_receipt_photo(active_cred, meal_id)
            ext_map = {'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}
            ext = ext_map.get(meta['content_type'], 'jpg')
            headers = [
                ('Content-Type', meta['content_type']),
                ('Content-Length', str(len(img_bytes))),
                ('Content-Disposition', f'inline; filename="receipt.{ext}"'),
                ('X-Content-Type-Options', 'nosniff'),
                ('Cache-Control', 'private, no-cache, no-store, must-revalidate'),
            ]
            return 200, headers, img_bytes

        # Delete Receipt Photo DELETE /api/meals/{meal_id}/receipt/photo
        m_photo_del = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/receipt/photo', path)
        if m_photo_del and method == 'DELETE':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_photo_del.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)

            authority.delete_receipt_photo(active_cred, meal_id)
            return 200, self._default_headers(), serialize_json({'ok': True})

        # Check Notion Export Status GET /api/meals/{meal_id}/export/notion
        m_notion_get = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/export/notion', path)
        if m_notion_get and method == 'GET':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_notion_get.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)
            snap = asdict(authority.snapshot(active_cred, meal_id))
            rev = snap.get('finalized_revision') or snap.get('revision', 0)
            rec = authority.get_notion_export(meal_id, rev)
            if rec:
                return 200, self._default_headers(), serialize_json({'ok': True, 'export': rec})
            return 200, self._default_headers(), serialize_json({'ok': True, 'export': {'status': 'not_started'}})

        # Export Finalized Meal to Notion POST /api/meals/{meal_id}/export/notion
        m_notion = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/export/notion', path)
        if m_notion and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_notion.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)

            snap = asdict(authority.snapshot(active_cred, meal_id))
            if not snap.get('finalized'):
                raise TransportError('meal_not_finalized', 409)

            import os
            token = body_data.get('token') or os.environ.get('SETTLETABLE_NOTION_TOKEN')
            if not token:
                notion_cli = self.get_notion_client()
                if notion_cli.__class__.__name__ == 'MockNotionClient' or os.environ.get('SETTLETABLE_MOCK_NOTION') == '1':
                    token = 'secret_mock_notion_uat_testing_token_12345'

            raw_parent_id = body_data.get('parent_id') or os.environ.get('SETTLETABLE_NOTION_PARENT_ID')
            parent_type = body_data.get('parent_type', 'page_id')

            if not isinstance(token, str) or not (token.startswith('secret_') or token.startswith('ntn_')) or len(token) < 20 or len(token) > 128:
                raise TransportError('invalid_input', 400)
            if not isinstance(raw_parent_id, str):
                raise TransportError('invalid_input', 400)
            from settletable.notion.client import extract_notion_id
            parent_id = extract_notion_id(raw_parent_id)
            if not parent_id:
                raise TransportError('invalid_input', 400)
            if parent_type not in ('page_id', 'database_id'):
                raise TransportError('invalid_input', 400)

            rev = snap.get('finalized_revision') or snap.get('revision', 0)
            calc_digest = snap.get('calculation_digest') or ''
            include_photo = bool(body_data.get('include_receipt_photo'))
            photo_flag = "photo=1" if include_photo else "photo=0"
            export_digest = f"{calc_digest}:{photo_flag}"

            receipt_photo_data = None
            if include_photo:
                try:
                    img_bytes, meta = authority.get_receipt_photo(active_cred, meal_id)
                    receipt_photo_data = (img_bytes, meta['filename'], meta['content_type'])
                except AuthorityError as err:
                    if err.code == 'photo_not_found':
                        raise TransportError('photo_not_found', 404) from None
                    if err.code == 'photo_corrupted':
                        raise TransportError('photo_corrupted', 500) from None
                    raise TransportError(err.code, STATUS_MAP.get(err.code, 500)) from None
                except Exception:
                    raise TransportError('storage_error', 500) from None

            rec = authority.get_notion_export(meal_id, rev)
            existing_page_id = None
            if rec and rec.get('status') == 'completed':
                rec_digest = rec.get('export_digest', '')
                rec_has_photo = rec_digest.endswith(':photo=1')
                if rec_has_photo or not include_photo:
                    out = {
                        'ok': True,
                        'export': {
                            'ok': True,
                            'status': 'already_exported',
                            'page_id': rec['page_id'],
                            'page_url': rec['page_url'],
                            'blocks_created': 0,
                        },
                    }
                    return 200, self._default_headers(), serialize_json(out)
                else:
                    existing_page_id = rec.get('page_id')

            if rec and rec.get('status') == 'in_progress':
                elapsed = time.time() - rec.get('exported_at', 0)
                if elapsed < 60.0:
                    return 202, self._default_headers(), serialize_json({
                        'ok': True,
                        'export': {
                            'ok': True,
                            'status': 'in_progress',
                            'page_id': None,
                            'page_url': None,
                        }
                    })

            authority.record_notion_export_in_progress(meal_id, rev, export_digest)

            qs = environ.get('QUERY_STRING', '')
            requested_sync = ('sync=1' in qs) or (environ.get('HTTP_X_SETTLETABLE_SYNC_EXPORT') == '1')
            is_sync = requested_sync and self.allow_sync_export

            from settletable.notion import (
                NotionExportConfig,
                NotionRateLimitError,
                NotionAuthError,
                NotionNotFoundError,
                NotionValidationError,
                NotionError,
                export_finalized_meal,
            )
            from settletable.notion.client import sanitize_notion_error_message

            config = NotionExportConfig(
                token=token,
                parent_id=parent_id.strip(),
                parent_type=parent_type,
                mode=body_data.get('mode', 'compact'),
                include_receipt_photo=include_photo,
                receipt_photo_data=receipt_photo_data,
                existing_page_id=existing_page_id,
            )

            if is_sync:
                try:
                    client = self.get_notion_client()
                    result = export_finalized_meal(client, meal_id, snap, config)
                    if result.ok:
                        authority.record_notion_export_completed(
                            meal_id, rev, result.page_id or '', result.page_url or '', export_digest
                        )
                        out = {'ok': True, 'export': result.to_dict()}
                        return 200, self._default_headers(), serialize_json(out)
                    else:
                        authority.record_notion_export_failed(meal_id, rev, result.error or 'notion_error')
                        return 400, self._default_headers(), serialize_json({'ok': False, 'error': result.error or 'notion_error'})
                except NotionRateLimitError:
                    authority.record_notion_export_failed(meal_id, rev, 'notion_rate_limited')
                    raise TransportError('notion_rate_limited', 429) from None
                except NotionAuthError:
                    authority.record_notion_export_failed(meal_id, rev, 'notion_auth_error')
                    raise TransportError('notion_auth_error', 400) from None
                except NotionNotFoundError as err:
                    clean = sanitize_notion_error_message(str(err))
                    authority.record_notion_export_failed(meal_id, rev, f'page_not_found: {clean}'[:128])
                    raise TransportError('notion_page_not_found', 400) from None
                except NotionValidationError as err:
                    clean = sanitize_notion_error_message(str(err))
                    authority.record_notion_export_failed(meal_id, rev, f'validation_error: {clean}'[:128])
                    raise TransportError('invalid_input', 400) from None
                except NotionError as err:
                    clean = sanitize_notion_error_message(str(err))
                    authority.record_notion_export_failed(meal_id, rev, f'notion_error: {clean}'[:128])
                    raise TransportError('notion_error', 502) from None
                except Exception as err:
                    clean = sanitize_notion_error_message(str(err))
                    authority.record_notion_export_failed(meal_id, rev, f'unexpected_error: {clean}'[:128])
                    raise TransportError('notion_error', 502) from None
            else:
                # Asynchronous delivery: dispatch in background thread, return 202 immediately
                # to prevent WSGI worker thread starvation for live diners.
                # Ephemeral background worker thread (asynchronous execution, not durable queue persistence).
                # Does not survive process termination; uncompleted exports time out cleanly after 60s.
                def _bg_export():
                    bg_auth = self.get_authority()
                    try:
                        client = self.get_notion_client()
                        result = export_finalized_meal(client, meal_id, snap, config)
                        if result.ok:
                            bg_auth.record_notion_export_completed(
                                meal_id, rev, result.page_id or '', result.page_url or '', export_digest
                            )
                        else:
                            bg_auth.record_notion_export_failed(meal_id, rev, result.error or 'notion_error')
                    except NotionRateLimitError:
                        bg_auth.record_notion_export_failed(meal_id, rev, 'notion_rate_limited')
                    except NotionAuthError:
                        bg_auth.record_notion_export_failed(meal_id, rev, 'notion_auth_error')
                    except NotionNotFoundError as err:
                        clean = sanitize_notion_error_message(str(err))
                        bg_auth.record_notion_export_failed(meal_id, rev, f'page_not_found: {clean}'[:128])
                    except NotionValidationError as err:
                        clean = sanitize_notion_error_message(str(err))
                        bg_auth.record_notion_export_failed(meal_id, rev, f'validation_error: {clean}'[:128])
                    except NotionError as err:
                        clean = sanitize_notion_error_message(str(err))
                        bg_auth.record_notion_export_failed(meal_id, rev, f'notion_error: {clean}'[:128])
                    except Exception as err:
                        clean = sanitize_notion_error_message(str(err))
                        bg_auth.record_notion_export_failed(meal_id, rev, f'unexpected_error: {clean}'[:128])
                    finally:
                        self.close()

                bg_thread = threading.Thread(target=_bg_export, daemon=True)
                bg_thread.start()
                out = {
                    'ok': True,
                    'export': {
                        'ok': True,
                        'status': 'in_progress',
                        'page_id': None,
                        'page_url': None,
                        'message': 'Notion export running asynchronously in background',
                    }
                }
                return 202, self._default_headers(), serialize_json(out)

        raise TransportError('not_found', 404)

    def _default_headers(self):
        return [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer'),
        ]

    @staticmethod
    def _parse_quantity(qty, *, allow_none=False):
        if qty is None:
            if allow_none:
                return None
            raise TransportError('invalid_input', 400)
        if isinstance(qty, list) and len(qty) == 2:
            num, den = qty[0], qty[1]
            if type(num) is not int or type(den) is not int or num <= 0 or den <= 0:
                raise TransportError('invalid_input', 400)
            try:
                return Fraction(num, den)
            except (ValueError, ZeroDivisionError):
                raise TransportError('invalid_input', 400)
        if type(qty) is int:
            if qty <= 0:
                raise TransportError('invalid_input', 400)
            return qty
        if isinstance(qty, Fraction):
            if type(qty.numerator) is not int or type(qty.denominator) is not int or qty <= 0:
                raise TransportError('invalid_input', 400)
            return qty
        raise TransportError('invalid_input', 400)

    def _build_command(self, data, *, legacy_scope=False):
        if not isinstance(data, dict):
            raise TransportError('invalid_input', 400)
        # Actor/organizer spoofing defense: callers cannot provide actor/organizer
        if 'actor' in data or 'organizer' in data:
            raise TransportError('invalid_input', 400)

        kind = data.get('kind')
        cmd_id = data.get('command_id')
        if not kind or not cmd_id:
            raise TransportError('invalid_input', 400)

        try:
            if kind == 'ReplaceReceipt':
                rcpt_data = data.get('receipt')
                if not isinstance(rcpt_data, dict):
                    raise TransportError('invalid_input', 400)
                raw_items = rcpt_data.get('items', [])
                raw_adjustments = rcpt_data.get('adjustments', [])
                items = []
                for item in raw_items:
                    qty = self._parse_quantity(item.get('quantity', 1))
                    items.append(ReceiptItem(item['id'], item['label'], qty, item.get('line_sen')))
                item_id_set = {item.id for item in items}
                adjustments = []
                for idx, adj in enumerate(raw_adjustments, start=1):
                    mode = adj.get('scope_mode')
                    if mode not in (None, 'all_items', 'fixed_items'):
                        raise TransportError('invalid_input', 400)
                    raw_eligible = adj.get('eligible_item_ids')
                    if mode == 'fixed_items' and not isinstance(raw_eligible, list):
                        raise TransportError('invalid_input', 400)
                    if mode == 'all_items' or raw_eligible is None:
                        eligible = tuple(item.id for item in items)
                    elif legacy_scope:
                        if not raw_eligible:
                            raw_eligible = ()
                        if not isinstance(raw_eligible, (list, tuple, str, dict)):
                            raise TransportError('invalid_input', 400)
                        eligible = tuple(eid for eid in raw_eligible if isinstance(eid, str) and eid in item_id_set)
                        if not eligible:
                            eligible = tuple(item.id for item in items)
                    else:
                        eligible = tuple(raw_eligible)
                    adj_id = adj.get('id') or f"adj-{idx}"
                    label = adj.get('label') or adj.get('kind') or f"Adjustment {idx}"
                    rationale = adj.get('rationale')
                    if not rationale or not str(rationale).strip():
                        rationale = f"{label} adjustment"
                    else:
                        rationale = str(rationale).strip()
                    adjustments.append(ReceiptAdjustment(
                        id=str(adj_id),
                        label=str(label),
                        kind=adj['kind'],
                        amount_sen=adj.get('amount_sen'),
                        eligible_item_ids=eligible,
                        rationale=rationale,
                        scope_mode=mode,
                    ))
                receipt = Receipt(
                    items=tuple(items),
                    subtotal_sen=rcpt_data.get('subtotal_sen'),
                    total_sen=rcpt_data.get('total_sen'),
                    adjustments=tuple(adjustments),
                    included_tax_sen=rcpt_data.get('included_tax_sen', 0),
                )
                return ReplaceReceipt(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision', 0),
                    expected_financial_revision=data.get('expected_financial_revision', 0),
                    receipt=receipt,
                )
            elif kind == 'SetOwnQuantity':
                qty = self._parse_quantity(data.get('quantity'), allow_none=True)
                return SetOwnQuantity(
                    command_id=cmd_id,
                    item_id=data.get('item_id'),
                    quantity=qty,
                    expected_item_revision=data.get('expected_item_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                )
            elif kind == 'AssignParticipantQuantity':
                qty = self._parse_quantity(data.get('quantity'), allow_none=True)
                part_id = data.get('participant_id')
                if not part_id or not isinstance(part_id, str):
                    raise TransportError('invalid_input', 400)
                return AssignParticipantQuantity(
                    command_id=cmd_id,
                    participant_id=part_id,
                    item_id=data.get('item_id'),
                    quantity=qty,
                    expected_item_revision=data.get('expected_item_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                )
            elif kind == 'SetItemAllocations':
                item_id = data.get('item_id')
                if not item_id or not isinstance(item_id, str):
                    raise TransportError('invalid_input', 400)
                raw_allocs = data.get('allocations')
                if not isinstance(raw_allocs, (list, tuple)):
                    raise TransportError('invalid_input', 400)
                allocs = []
                for entry in raw_allocs:
                    if isinstance(entry, AllocationSpec):
                        qty = self._parse_quantity(entry.quantity, allow_none=False)
                        allocs.append(AllocationSpec(participant_id=entry.participant_id, quantity=qty))
                        continue
                    if not isinstance(entry, dict):
                        raise TransportError('invalid_input', 400)
                    part_id = entry.get('participant_id')
                    if not part_id or not isinstance(part_id, str):
                        raise TransportError('invalid_input', 400)
                    qty = self._parse_quantity(entry.get('quantity'), allow_none=False)
                    allocs.append(AllocationSpec(participant_id=part_id, quantity=qty))
                return SetItemAllocations(
                    command_id=cmd_id,
                    item_id=item_id,
                    allocations=tuple(allocs),
                    expected_item_revision=data.get('expected_item_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                )
            elif kind == 'ReviewReceipt':
                return ReviewReceipt(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                    receipt_digest=data.get('receipt_digest'),
                )
            elif kind == 'Finalize':
                return Finalize(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                )
            elif kind == 'RevokeInvitation':
                return RevokeInvitation(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    participant_id=data.get('participant_id'),
                )
            elif kind == 'RevokeSession':
                return RevokeSession(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    participant_id=data.get('participant_id'),
                )
            elif kind == 'RevokeMembership':
                return RevokeMembership(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    participant_id=data.get('participant_id'),
                )
            elif kind == 'RecordContribution':
                expected_rev = data.get('expected_revision')
                part_id = data.get('participant_id')
                amount_sen = data.get('amount_sen')
                method = data.get('payment_method')
                if expected_rev is None or not isinstance(expected_rev, int) or expected_rev < 0:
                    raise TransportError('invalid_input', 400)
                if not part_id or not isinstance(part_id, str):
                    raise TransportError('invalid_input', 400)
                if not isinstance(amount_sen, int) or amount_sen < 1 or amount_sen > 1_000_000_000:
                    raise TransportError('invalid_input', 400)
                if method is not None and method not in ('cash', 'card', 'ewallet', 'bank_transfer', 'other'):
                    raise TransportError('invalid_input', 400)
                return RecordContribution(
                    command_id=cmd_id,
                    expected_revision=expected_rev,
                    participant_id=part_id,
                    amount_sen=amount_sen,
                    payment_method=method,
                )
            elif kind == 'ReverseContribution':
                expected_rev = data.get('expected_revision')
                contrib_id = data.get('contribution_id')
                reason = data.get('reason')
                if expected_rev is None or not isinstance(expected_rev, int) or expected_rev < 0:
                    raise TransportError('invalid_input', 400)
                if not contrib_id or not isinstance(contrib_id, str):
                    raise TransportError('invalid_input', 400)
                if reason is not None and (not isinstance(reason, str) or len(reason) > 200):
                    raise TransportError('invalid_input', 400)
                return ReverseContribution(
                    command_id=cmd_id,
                    expected_revision=expected_rev,
                    contribution_id=contrib_id,
                    reason=reason,
                )
            elif kind == 'RecordTransfer':
                expected_rev = data.get('expected_revision')
                sender_id = data.get('sender_id')
                receiver_id = data.get('receiver_id')
                amount_sen = data.get('amount_sen')
                note = data.get('note')
                if expected_rev is None or not isinstance(expected_rev, int) or expected_rev < 0:
                    raise TransportError('invalid_input', 400)
                if not sender_id or not isinstance(sender_id, str):
                    raise TransportError('invalid_input', 400)
                if not receiver_id or not isinstance(receiver_id, str):
                    raise TransportError('invalid_input', 400)
                if sender_id == receiver_id:
                    raise TransportError('self_transfer_prohibited', 400)
                if not isinstance(amount_sen, int) or amount_sen < 1 or amount_sen > 1_000_000_000:
                    raise TransportError('invalid_input', 400)
                if note is not None and (not isinstance(note, str) or len(note) > 200):
                    raise TransportError('invalid_input', 400)
                return RecordTransfer(
                    command_id=cmd_id,
                    expected_revision=expected_rev,
                    sender_id=sender_id,
                    receiver_id=receiver_id,
                    amount_sen=amount_sen,
                    note=note,
                )
            elif kind == 'ReverseTransfer':
                expected_rev = data.get('expected_revision')
                transfer_id = data.get('transfer_id')
                reason = data.get('reason')
                if expected_rev is None or not isinstance(expected_rev, int) or expected_rev < 0:
                    raise TransportError('invalid_input', 400)
                if not transfer_id or not isinstance(transfer_id, str):
                    raise TransportError('invalid_input', 400)
                if reason is not None and (not isinstance(reason, str) or len(reason) > 200):
                    raise TransportError('invalid_input', 400)
                return ReverseTransfer(
                    command_id=cmd_id,
                    expected_revision=expected_rev,
                    transfer_id=transfer_id,
                    reason=reason,
                )
            else:
                raise TransportError('invalid_command_kind', 400)
        except (KeyError, TypeError):
            raise TransportError('invalid_input', 400)
