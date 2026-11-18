"""Optional experimental checkout demo (synthetic); disabled without explicit config.

An organizer may ask an operator-run experimental checkout bridge to create one
synthetic, nonpayable checkout for a current suggested transfer whose receiver is
the organizer. SettleTable then only observes the bridge's outcome. This module
never writes a contribution, pending report or transfer and never changes accepted
command or result bytes, so settlement is unchanged by every outcome.

It is separate from ``payment_simulation``: its own configuration, namespace,
client, wire slot and suspension state. Only an opaque reference, an integer amount
and the literal currency are sent. It never provisions credentials or enables a
deployment.

Observed-evidence mode (``SETTLETABLE_CHECKOUT_DEMO_OBSERVED_EVIDENCE=true``) is a
separate opt-in for a bridge that observes the organizer's own wallet notification.
It stays display only. Every branch it adds is guarded by ``config.observed``; when
the variable is absent the behaviour is exactly the synthetic demo's.
"""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import sqlite3
import ssl
import threading
import time
from urllib.parse import urlsplit
import uuid

from .authority import AuthorityError, _id, _require, _verifier, _wire
from .funding import PayerContributionRecord, compute_net_balances
from .settlement import PeerTransferRecord, compute_settlement

PURPOSE = 'checkout-demo-v1'
PREFIX = 'SETTLETABLE_CHECKOUT_DEMO_'
CONFIG_ERROR = 'invalid_checkout_demo_configuration'
BASIS_ERROR = 'invalid_finalization_basis'
RESPONSE_LIMIT = 8192
MAX_ATTEMPTS = 50
CHECKOUT_PATH = '/api/integrations/checkouts/'
CHECKOUT_FIELDS = frozenset({'reference', 'checkoutId', 'amountMinor', 'status', 'evidence',
                             'createdAt', 'expiresAt', 'reviewExpiresAt', 'revision'})
# Stored local states. OBSERVED carries a bridge status that maps to a display state.
STORED_STATES = frozenset({'REQUEST_UNKNOWN', 'NOT_CREATED', 'OBSERVED', 'REFERENCE_LOST',
                           'CONFLICT', 'UNEXPECTED_STATUS'})
# Latched states stop automatic actions and all further wire I/O for that intent.
LATCHED = frozenset({'CONFLICT', 'UNEXPECTED_STATUS'})
# Terminal under the eligibility rule: a new attempt may follow.
TERMINAL = frozenset({'NOT_CREATED', 'CONFLICT', 'EXPIRED', 'MANUALLY_CONFIRMED'})
FINAL_BRIDGE = frozenset({'MANUALLY_CONFIRMED', 'EXPIRED', 'REVIEW_EXPIRED'})
# Observed-evidence mode only (KP-SETTLETABLE-TNG-02 D2).
OBSERVED_FLAG = PREFIX + 'OBSERVED_EVIDENCE'
EVIDENCE_MODE = 'OBSERVED_NOTIFICATION'
OBSERVED_FIELDS = CHECKOUT_FIELDS | {'evidenceMode'}
# Bridge refusals that create nothing; latched as CONFLICT with this reason.
OBSERVED_REFUSALS = frozenset({'OBSERVED_CHECKOUT_SPENT', 'OBSERVED_AMOUNT_MISMATCH'})
# A success body without the observed marker: latched as UNEXPECTED_STATUS with this reason.
MODE_MISMATCH = 'EVIDENCE_MODE_MISMATCH'
# One WSGI worker: keep a status read from racing a PUT inside this process and
# leave request threads free for ordinary meal work. Not shared with I06.
_wire_slot = threading.Lock()

_COLUMNS = ('attempt', 'finalize_actor_id', 'finalize_command_id', 'sender_id', 'receiver_id',
            'amount_sen', 'reference', 'state', 'not_created_reason', 'dispatch_count',
            'checkout_id', 'bridge_status', 'evidence', 'revision', 'bridge_created_at',
            'expires_at', 'review_expires_at', 'observed_at')


def canonical_uuid(value):
    if type(value) is not str or len(value) != 36 or str(uuid.UUID(value)) != value:
        raise ValueError('invalid_uuid')
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_field')
        result[key] = value
    return result


def _strict_json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


@dataclass(frozen=True)
class CheckoutDemoConfig:
    namespace: str
    base_url: str
    credential: str = field(repr=False)
    ca_file: str | None = None
    observed: bool = False

    def __post_init__(self):
        try:
            canonical_uuid(self.namespace)
            if type(self.observed) is not bool:
                raise ValueError()
            if type(self.credential) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', self.credential):
                raise ValueError()
            if type(self.base_url) is not str or not re.fullmatch(r'[!-~]{1,512}', self.base_url):
                raise ValueError()
            url = urlsplit(self.base_url)
            if (url.scheme not in ('http', 'https') or not url.hostname
                    or url.username is not None or url.password is not None
                    or url.path not in ('', '/') or '?' in self.base_url or '#' in self.base_url):
                raise ValueError()
            port = url.port if url.port is not None else (443 if url.scheme == 'https' else 80)
            if not 1 <= port <= 65535:
                raise ValueError()
            if url.scheme == 'http' and url.hostname != 'localhost' and not ipaddress.ip_address(url.hostname).is_loopback:
                raise ValueError()
            if self.ca_file is not None and (url.scheme != 'https' or type(self.ca_file) is not str
                                             or not self.ca_file):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(CONFIG_ERROR) from None

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        # Exactly "true" opts in; any other present value, or the flag without the demo, fails startup.
        observed = env.get(OBSERVED_FLAG)
        if observed is not None and observed != 'true':
            raise ValueError(CONFIG_ERROR)
        enabled = env.get(PREFIX + 'ENABLED', '0')
        if enabled == '0':
            if observed is not None:
                raise ValueError(CONFIG_ERROR)
            return None
        if enabled != '1':
            raise ValueError(CONFIG_ERROR)
        try:
            namespace = env[PREFIX + 'NAMESPACE']
            base_url = env[PREFIX + 'BASE_URL']
            has_direct = PREFIX + 'CREDENTIAL' in env
            secret_file = env.get(PREFIX + 'CREDENTIALS_FILE')
            if has_direct == (secret_file is not None):
                raise ValueError()
            if has_direct:
                credential = env[PREFIX + 'CREDENTIAL']
            else:
                # Container mode: a read-only mounted JSON file {"credential": "..."}.
                with open(secret_file, 'rb') as stream:
                    raw = stream.read(4097)
                if len(raw) > 4096:
                    raise ValueError()
                loaded = _strict_json(raw)
                if type(loaded) is not dict or set(loaded) != {'credential'}:
                    raise ValueError()
                credential = loaded['credential']
            ca_file = env.get(PREFIX + 'CA_FILE')
            if ca_file is not None and not ca_file:
                raise ValueError()
            # Its own namespace: never share the I06 installation namespace.
            if str(env.get('SETTLETABLE_KAIPAY_NAMESPACE', '')).lower() == str(namespace).lower():
                raise ValueError()
            if observed is not None:
                return cls(namespace, base_url, credential, ca_file, observed=True)
            return cls(namespace, base_url, credential, ca_file)
        except (KeyError, ValueError, TypeError, OSError, RecursionError):
            raise ValueError(CONFIG_ERROR) from None


def checkout_reference(namespace, meal_id, finalize_actor_id, finalize_command_id, sender_id, receiver_id, attempt):
    """UUIDv5 over the frozen basis. The amount never enters the reference."""
    _require(type(attempt) is int and 1 <= attempt <= MAX_ATTEMPTS, 'invalid_input')
    name = json.dumps([PURPOSE, meal_id, finalize_actor_id, finalize_command_id, sender_id, receiver_id, attempt],
                      ensure_ascii=True, separators=(',', ':'))
    return str(uuid.uuid5(uuid.UUID(namespace), name))


def display_status(status, evidence, observed=False):
    """Evidence-checked mapping. The evidence check takes precedence on every row."""
    if observed:
        return _observed_display_status(status, evidence)
    if evidence not in ('NONE', 'SYNTHETIC'):
        return 'UNEXPECTED_STATUS'
    if status == 'AWAITING_PAYMENT' and evidence == 'NONE':
        return 'AWAITING_EVIDENCE'
    if status in ('PAYMENT_DETECTED', 'AWAITING_VERIFICATION') and evidence == 'SYNTHETIC':
        return 'EVIDENCE_DETECTED'
    if status == 'AMBIGUOUS':
        return 'NEEDS_REVIEW'
    if status == 'MANUALLY_CONFIRMED' and evidence == 'SYNTHETIC':
        return 'MANUALLY_CONFIRMED'
    if status in ('EXPIRED', 'REVIEW_EXPIRED'):
        return 'EXPIRED'
    return 'UNEXPECTED_STATUS'


def _observed_display_status(status, evidence):
    """Observed-mode mapping (design D2). Evidence first: SYNTHETIC or anything unknown is unexpected."""
    if evidence not in ('NONE', 'NOTIFICATION_UNVERIFIED'):
        return 'UNEXPECTED_STATUS'
    if status == 'AWAITING_PAYMENT' and evidence == 'NONE':
        return 'AWAITING_EVIDENCE'
    if status in ('PAYMENT_DETECTED', 'AWAITING_VERIFICATION') and evidence == 'NOTIFICATION_UNVERIFIED':
        return 'EVIDENCE_DETECTED'
    if status == 'MANUALLY_CONFIRMED' and evidence == 'NOTIFICATION_UNVERIFIED':
        return 'MANUALLY_CONFIRMED'
    if status == 'AMBIGUOUS':
        return 'NEEDS_REVIEW'
    if status in ('EXPIRED', 'REVIEW_EXPIRED'):
        return 'EXPIRED'
    return 'UNEXPECTED_STATUS'


def _timestamp(value, nullable=False):
    if value is None and nullable:
        return
    if (type(value) is not str or not 20 <= len(value) <= 40
            or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+(Z|[+-][0-9]{2}:[0-9]{2})', value)
            or datetime.fromisoformat(value).tzinfo is None):
        raise ValueError('invalid_checkout_response')


def validate_checkout(data, observed=False):
    """The bridge GET/PUT body is an exact allowlist.

    In observed mode the body may also carry ``evidenceMode``. Its value is not
    judged here: a missing or different marker is a latched mode mismatch, decided
    when the observation is stored, never a transient failure.
    """
    if type(data) is not dict or (set(data) != CHECKOUT_FIELDS
                                  and not (observed and set(data) == OBSERVED_FIELDS)):
        raise ValueError('invalid_checkout_response')
    canonical_uuid(data['reference'])
    canonical_uuid(data['checkoutId'])
    if (type(data['amountMinor']) is not int or not 1 <= data['amountMinor'] <= 1_000_000_000
            or type(data['revision']) is not int or not 0 <= data['revision'] <= 9_223_372_036_854_775_807):
        raise ValueError('invalid_checkout_response')
    for key in ('status', 'evidence'):
        if type(data[key]) is not str or not re.fullmatch(r'[A-Z][A-Z_]{0,39}', data[key]):
            raise ValueError('invalid_checkout_response')
    _timestamp(data['createdAt'])
    _timestamp(data['expiresAt'])
    _timestamp(data['reviewExpiresAt'], nullable=True)
    return data


class CheckoutDemoClient:
    """Direct HTTP(S) to the pinned bridge; no environment proxies, redirects or cookies."""
    def __init__(self, config):
        self.config = config
        self.url = urlsplit(config.base_url)
        self.port = self.url.port if self.url.port is not None else (443 if self.url.scheme == 'https' else 80)
        try:
            self.addresses = tuple(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(
                self.url.hostname, self.port, type=socket.SOCK_STREAM)))
            if not self.addresses or (self.url.scheme == 'http' and
                                     not all(ipaddress.ip_address(a).is_loopback for a in self.addresses)):
                raise ValueError()
            # A client-only trust anchor. SSL_CERT_FILE is never consulted or set.
            self.context = (ssl.create_default_context(cafile=config.ca_file)
                            if self.url.scheme == 'https' else None)
        except (OSError, ValueError, ssl.SSLError):
            raise ValueError(CONFIG_ERROR) from None
        self.admission_lock = threading.Lock()
        self.retry_not_before = 0
        self.suspended = False

    def _transport(self, method, retry=None):
        return {'transport': 'REQUEST_UNKNOWN' if method == 'PUT' else 'UNAVAILABLE', 'retry_after': retry}

    def admission(self):
        """The refusal a request would get right now without any I/O, or None."""
        with self.admission_lock:
            if self.suspended:
                return {'transport': 'UNAVAILABLE', 'retry_after': None}
            if time.monotonic() < self.retry_not_before:
                return {'transport': 'UNAVAILABLE',
                        'retry_after': max(1, int(self.retry_not_before - time.monotonic()) + 1)}
        return None

    def _connect(self, deadline):
        """Try each pinned address in order inside the whole-request deadline."""
        for address in self.addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                return socket.create_connection((address, self.port), timeout=min(2, remaining))
            except OSError:
                continue
        raise TimeoutError()

    def request(self, method, reference, amount):
        """At most one request. Returns {'checkout'}, {'error'} or {'transport'}."""
        if method not in ('GET', 'PUT'):
            raise ValueError('invalid_method')
        canonical_uuid(reference)
        refused = self.admission()
        if refused is not None:
            return refused
        connection = None
        timer = None
        sock = None
        sockets = []

        def abort():
            for active in sockets:
                try:
                    active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        try:
            deadline = time.monotonic() + 5
            sock = self._connect(deadline)
            sockets.append(sock)
            timer = threading.Timer(max(0.001, deadline - time.monotonic()), abort)
            timer.daemon = True
            timer.start()
            if self.context:
                sock.settimeout(max(0.001, deadline - time.monotonic()))
                sock = self.context.wrap_socket(sock, server_hostname=self.url.hostname,
                                                do_handshake_on_connect=False)
                sockets.append(sock)
                sock.do_handshake()
            connection = http.client.HTTPConnection(self.url.hostname, self.port, timeout=2)
            connection.sock = sock
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            body = (json.dumps({'amountMinor': amount, 'currency': 'MYR'}, separators=(',', ':'))
                    if method == 'PUT' else None)
            headers = {'Authorization': 'Bearer ' + self.config.credential,
                       'Accept': 'application/json', 'Connection': 'close'}
            if body is not None:
                headers['Content-Type'] = 'application/json'
            connection.request(method, CHECKOUT_PATH + reference, body=body, headers=headers)
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            response = connection.getresponse()
            raw = bytearray()
            while not response.isclosed():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                sock.settimeout(remaining)
                chunk = response.read1(min(1024, RESPONSE_LIMIT + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > RESPONSE_LIMIT:
                    raise ValueError('invalid_checkout_response')
            if response.length not in (None, 0):
                raise ValueError('invalid_checkout_response')
            status = response.status
            json_body = response.getheader('Content-Type', '').split(';')[0].strip().lower() == 'application/json'
            if status in (200, 201) and json_body and (status == 200 or method == 'PUT'):
                return {'checkout': validate_checkout(_strict_json(raw), self.config.observed)}
            if json_body and status in (404, 409):
                payload = _strict_json(raw)
                code = payload.get('error') if type(payload) is dict and set(payload) == {'error'} else None
                if status == 404 and method == 'GET' and code == 'REFERENCE_NOT_FOUND':
                    return {'error': code}
                if status == 409 and method == 'PUT' and code in ('SAME_AMOUNT_HELD', 'REFERENCE_CONFLICT'):
                    return {'error': code}
                if status == 409 and method == 'PUT' and self.config.observed and code in OBSERVED_REFUSALS:
                    return {'error': code}
            retry = response.getheader('Retry-After', '')
            retry = max(1, min(120, int(retry))) if re.fullmatch(r'[0-9]{1,3}', retry) else None
            with self.admission_lock:
                if status in (400, 401, 403):
                    # Operator correction and a process restart are required.
                    self.suspended = True
                if status == 429:
                    retry = retry or 1
                    self.retry_not_before = max(self.retry_not_before, time.monotonic() + retry)
            if status in (400, 401, 403, 429):
                return {'transport': 'UNAVAILABLE', 'retry_after': retry}
            return self._transport(method, retry)
        except (OSError, ValueError, http.client.HTTPException, RecursionError):
            return self._transport(method)
        finally:
            if timer:
                timer.cancel()
            if connection:
                connection.close()
            if sock is not None:
                sock.close()


# --- Authority-side state (caller-owned short SQLite transactions) ---

def _finalize_basis(authority, meal_id, state):
    """The unique accepted Finalize actor and command, checked byte for byte."""
    found = []
    for actor, command_id, body, digest, result in authority._db.execute(
            'SELECT participant_id,command_id,body,digest,result FROM commands WHERE meal_id=? AND security=0',
            (meal_id,)):
        command = json.loads(body)
        accepted = json.loads(result)
        if command.get('kind') == 'Finalize' or accepted.get('kind') == 'Finalize':
            _require(command.get('kind') == accepted.get('kind') == 'Finalize', BASIS_ERROR)
            _require(_wire(command) == body and _wire(accepted) == result
                     and digest == hashlib.sha256(b'settletable-command-digest-v1\0' + body).digest(), BASIS_ERROR)
            _id(actor)
            _id(command_id)
            _require(command.get('command_id') == accepted.get('command_id') == command_id, BASIS_ERROR)
            # The same consistency checks as Authority._finalized_allocation.
            revision, financial_revision = accepted.get('revision'), accepted.get('financial_revision')
            _require(type(revision) is int and 1 <= revision <= state['revision']
                     and type(financial_revision) is int and financial_revision == state['financial_revision']
                     and command.get('expected_revision') == revision - 1
                     and command.get('expected_financial_revision') == financial_revision
                     and accepted.get('calculation') == state['calculation'], BASIS_ERROR)
            found.append((actor, command_id))
    _require(len(found) == 1, BASIS_ERROR)
    return found[0]


def current_suggestions(authority, meal_id, state):
    """Recompute suggestions exactly as the meal snapshot does (read only)."""
    db = authority._db
    people = db.execute('SELECT id,name,organizer,active FROM participants WHERE meal_id=?', (meal_id,)).fetchall()
    names = {p[0]: p[1] for p in people}
    contributions = tuple(
        PayerContributionRecord(
            contribution_id=r[0], command_id=r[1], participant_id=r[2], participant_name=names.get(r[2], r[2]),
            amount_sen=r[3], payment_method=r[4], created_at=r[5], created_by=r[6], status=r[7],
            reversed_at=r[8], reversed_by=r[9], reversal_command_id=r[10], reversal_reason=r[11])
        for r in db.execute('''SELECT contribution_id,command_id,participant_id,amount_sen,payment_method,
            created_at,created_by,status,reversed_at,reversed_by,reversal_command_id,reversal_reason
            FROM payer_contributions WHERE meal_id=? ORDER BY created_at ASC, contribution_id ASC''', (meal_id,)))
    funding, net_balances = compute_net_balances(
        consumption_records=[(p['participant_id'], p['sen']) for p in state['calculation']['consumption']],
        participant_names=names, active_participants={p[0] for p in people if p[3]},
        active_contributions=contributions, receipt_total_sen=state['receipt']['total_sen'])
    transfers = tuple(
        PeerTransferRecord(
            transfer_id=r[0], command_id=r[1], sender_id=r[2], receiver_id=r[3], amount_sen=r[4], note=r[5],
            created_at=r[6], created_by=r[7], status=r[8], reversed_at=r[9], reversed_by=r[10],
            reversal_command_id=r[11], reversal_reason=r[12])
        for r in db.execute('''SELECT transfer_id,command_id,sender_id,receiver_id,amount_sen,note,created_at,
            created_by,status,reversed_at,reversed_by,reversal_command_id,reversal_reason
            FROM peer_transfers WHERE meal_id=? ORDER BY created_at ASC, transfer_id ASC''', (meal_id,)))
    settlement = compute_settlement(base_net_balances=net_balances, transfers=transfers,
                                    unfunded_sen=funding.unfunded_sen)
    return tuple((s.sender_id, s.receiver_id, s.amount_sen) for s in settlement.suggested_transfers)


def _display(row, observed=False):
    if row['state'] == 'OBSERVED':
        return display_status(row['bridge_status'], row['evidence'], observed)
    if row['state'] == 'REFERENCE_LOST':
        return 'UNAVAILABLE'
    return row['state']


def _target(row):
    return (row['sender_id'], row['receiver_id'], row['amount_sen'])


def _context(authority, credential, meal_id, config):
    """Authorize the organizer and validate every frozen intent against its basis."""
    _id(meal_id)
    actor, organizer = authority._authenticate(_verifier(credential), meal_id)
    _require(bool(organizer), 'forbidden')
    state = json.loads(authority._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
    _require(state['calculation'] is not None, 'meal_not_finalized')
    final_actor, final_command = _finalize_basis(authority, meal_id, state)
    suggestions = current_suggestions(authority, meal_id, state)
    rows = []
    for values in authority._db.execute(
            f'SELECT {",".join(_COLUMNS)} FROM checkout_demos WHERE meal_id=? ORDER BY attempt', (meal_id,)):
        row = dict(zip(_COLUMNS, values))
        _require(row['attempt'] == len(rows) + 1 and row['state'] in STORED_STATES
                 and (row['finalize_actor_id'], row['finalize_command_id']) == (final_actor, final_command)
                 and row['reference'] == checkout_reference(config.namespace, meal_id, final_actor, final_command,
                                                            row['sender_id'], row['receiver_id'], row['attempt'])
                 and (row['state'] != 'OBSERVED' or row['checkout_id'] is not None),
                 'checkout_demo_conflict')
        rows.append(row)
    return {'meal_id': meal_id, 'actor': actor, 'finalize': (final_actor, final_command),
            'suggestions': suggestions, 'rows': rows, 'observed': config.observed}


def _decide(ctx, sender_id, amount_sen):
    """The single eligibility rule for both the eligible list and an explicit request."""
    observed = ctx['observed']
    target = (sender_id, ctx['actor'], amount_sen)
    _require(target in ctx['suggestions'], 'checkout_demo_stale')
    # No repeated "confirmed" demos for the same unchanged debt.
    _require(not any(_display(r, observed) == 'MANUALLY_CONFIRMED' and _target(r) == target for r in ctx['rows']),
             'checkout_demo_already_confirmed')
    latest = ctx['rows'][-1] if ctx['rows'] else None
    if latest is None:
        return 'NEW', None
    shown = _display(latest, observed)
    if shown not in TERMINAL:
        _require(_target(latest) == target and latest['state'] == 'REQUEST_UNKNOWN', 'checkout_demo_active')
        return 'CHECK', latest
    if observed:
        # One attempt per meal. The only further PUT is the identical same-reference re-PUT
        # after a checked absence, and only while no checkout was ever bound.
        _require(shown == 'NOT_CREATED' and latest['not_created_reason'] == 'REFERENCE_NOT_FOUND'
                 and latest['checkout_id'] is None and _target(latest) == target, 'resource_limit')
        return 'RETRY', latest
    if shown == 'NOT_CREATED' and _target(latest) == target:
        return 'RETRY', latest
    _require(latest['attempt'] < MAX_ATTEMPTS, 'resource_limit')
    return 'NEW', latest


def _eligible(ctx):
    out = []
    for sender, receiver, amount in ctx['suggestions']:
        if receiver != ctx['actor']:
            continue
        try:
            action, _ = _decide(ctx, sender, amount)
        except AuthorityError:
            continue
        if action != 'CHECK':
            out.append({'senderId': sender, 'receiverId': receiver, 'amountSen': amount, 'action': action})
    return out


def _projection(ctx, last_check=None, retry_after=None):
    latest = ctx['rows'][-1] if ctx['rows'] else None
    intent = None
    if latest is not None:
        shown = _display(latest, ctx['observed'])
        intent = {
            'attempt': latest['attempt'], 'reference': latest['reference'],
            'senderId': latest['sender_id'], 'receiverId': latest['receiver_id'], 'amountSen': latest['amount_sen'],
            'state': 'UNAVAILABLE' if last_check == 'UNAVAILABLE' and shown not in LATCHED else shown,
            'lastKnownState': shown, 'notCreatedReason': latest['not_created_reason'],
            'referenceLost': latest['state'] == 'REFERENCE_LOST',
            'checkoutId': latest['checkout_id'], 'bridgeStatus': latest['bridge_status'],
            'evidence': latest['evidence'], 'revision': latest['revision'],
            'createdAt': latest['bridge_created_at'], 'expiresAt': latest['expires_at'],
            'reviewExpiresAt': latest['review_expires_at'], 'observedAt': latest['observed_at'],
            'possibleDispatches': latest['dispatch_count'],
            'stale': _target(latest) not in ctx['suggestions'],
            'terminal': shown in TERMINAL, 'latched': shown in LATCHED,
        }
    result = {'enabled': True, 'synthetic': True, 'intent': intent, 'eligible': _eligible(ctx),
              'lastCheck': last_check, 'retryAfter': retry_after}
    if ctx['observed']:
        result.update(synthetic=False, observed=True, evidenceMode=EVIDENCE_MODE)
    return result


def _transaction_failure(authority, error, attempted):
    uncertain = attempted and authority._db is not None and not authority._db.in_transaction
    authority._rollback()
    if uncertain:
        raise AuthorityError('commit_uncertain') from None
    if isinstance(error, AuthorityError):
        raise error
    if isinstance(error, sqlite3.Error):
        authority._storage_failure(error)
    if isinstance(error, RuntimeError):
        raise AuthorityError('storage_error') from None
    raise AuthorityError(BASIS_ERROR) from None


def _transaction(authority, write, work, stage):
    attempted = False
    try:
        _require(authority._db is not None, 'storage_error')
        authority._db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        result = work()
        authority._hook(f'checkout_demo_before_{stage}_commit')
        attempted = True
        authority._db.execute('COMMIT')
        authority._hook(f'checkout_demo_after_{stage}_commit')
        return result
    except Exception as error:
        _transaction_failure(authority, error, attempted)


def _update(authority, ctx, row, **values):
    assignments = ','.join(f'{key}=?' for key in values)
    authority._db.execute(f'UPDATE checkout_demos SET {assignments} WHERE meal_id=? AND attempt=? AND reference=?',
                          (*values.values(), ctx['meal_id'], row['attempt'], row['reference']))
    row.update(values)


def _apply_observation(authority, ctx, row, method, observation):
    """Old responses cannot regress newer evidence; mismatches fail closed."""
    if row['state'] in LATCHED:
        return None
    now = authority._now()
    observed = ctx['observed']
    if 'checkout' in observation:
        data = observation['checkout']
        if observed and data.get('evidenceMode') != EVIDENCE_MODE:
            # A bridge in another mode answered: never bind it, and stop all further I/O.
            _update(authority, ctx, row, state='UNEXPECTED_STATUS', not_created_reason=MODE_MISMATCH,
                    observed_at=now)
            return 'OK'
        if data['reference'] != row['reference'] or data['amountMinor'] != row['amount_sen']:
            _update(authority, ctx, row, state='CONFLICT', observed_at=now)
            return 'OK'
        if row['checkout_id'] is not None:
            if data['checkoutId'] != row['checkout_id'] or data['createdAt'] != row['bridge_created_at']:
                _update(authority, ctx, row, state='CONFLICT', observed_at=now)
                return 'OK'
            if data['revision'] < row['revision']:
                return 'OK'
            if data['revision'] == row['revision'] and (
                    data['status'], data['evidence'], data['expiresAt'], data['reviewExpiresAt']) != (
                    row['bridge_status'], row['evidence'], row['expires_at'], row['review_expires_at']):
                _update(authority, ctx, row, state='CONFLICT', observed_at=now)
                return 'OK'
            terminal_change = (row['bridge_status'] in FINAL_BRIDGE and data['status'] != row['bridge_status'])
        else:
            terminal_change = False
        shown = display_status(data['status'], data['evidence'], observed)
        _update(authority, ctx, row,
                state='UNEXPECTED_STATUS' if shown == 'UNEXPECTED_STATUS' or terminal_change else 'OBSERVED',
                not_created_reason=None, checkout_id=data['checkoutId'], bridge_status=data['status'],
                evidence=data['evidence'], revision=data['revision'], bridge_created_at=data['createdAt'],
                expires_at=data['expiresAt'], review_expires_at=data['reviewExpiresAt'], observed_at=now)
        return 'OK'
    code = observation.get('error')
    if observed and code in OBSERVED_REFUSALS and method == 'PUT':
        # Nothing was created: a latched terminal refusal, never NOT_CREATED, so no RETRY follows.
        _update(authority, ctx, row, state='CONFLICT', observed_at=now,
                not_created_reason=code if row['checkout_id'] is None else None)
        return 'OK'
    if code == 'REFERENCE_CONFLICT' and method == 'PUT':
        _update(authority, ctx, row, state='CONFLICT', observed_at=now)
        return 'OK'
    if code == 'SAME_AMOUNT_HELD' and method == 'PUT':
        if row['checkout_id'] is None:
            _update(authority, ctx, row, state='NOT_CREATED', not_created_reason='SAME_AMOUNT_HELD', observed_at=now)
        else:
            _update(authority, ctx, row, state='CONFLICT', observed_at=now)
        return 'OK'
    if code == 'REFERENCE_NOT_FOUND' and method == 'GET':
        if row['checkout_id'] is not None:
            # Snapshot loss: shown as unavailable until the operator decides. Never recreated.
            _update(authority, ctx, row, state='REFERENCE_LOST', observed_at=now)
        elif row['state'] == 'REQUEST_UNKNOWN':
            # Checked absence: one explicit, identical re-PUT becomes possible.
            _update(authority, ctx, row, state='NOT_CREATED', not_created_reason='REFERENCE_NOT_FOUND',
                    observed_at=now)
        else:
            _update(authority, ctx, row, observed_at=now)
        return 'OK'
    _require(observation.get('transport') in ('REQUEST_UNKNOWN', 'UNAVAILABLE'), 'invalid_input')
    return observation['transport']


def _store(authority, credential, meal_id, config, attempt, reference, method, observation):
    def work():
        ctx = _context(authority, credential, meal_id, config)
        row = next((r for r in ctx['rows'] if r['attempt'] == attempt), None)
        _require(row is not None and row['reference'] == reference, 'checkout_demo_conflict')
        check = _apply_observation(authority, ctx, row, method, observation)
        return _projection(ctx, check, observation.get('retry_after'))
    return _transaction(authority, True, work, 'observation')


def _read(authority, credential, meal_id, config):
    return _transaction(authority, False, lambda: _context(authority, credential, meal_id, config), 'read')


def checkout_demo_status(authority, credential, meal_id, config, client):
    """Organizer status read: at most one bridge GET, never a PUT."""
    if not _wire_slot.acquire(blocking=False):
        return _projection(_read(authority, credential, meal_id, config), 'BUSY', 2)
    try:
        ctx = _read(authority, credential, meal_id, config)
        latest = ctx['rows'][-1] if ctx['rows'] else None
        if latest is None or latest['state'] in LATCHED:
            return _projection(ctx)
        _require(not authority._db.in_transaction, 'storage_error')
        observation = client.request('GET', latest['reference'], latest['amount_sen'])
        return _store(authority, credential, meal_id, config, latest['attempt'], latest['reference'],
                      'GET', observation)
    finally:
        _wire_slot.release()


def request_checkout_demo(authority, credential, meal_id, config, client, sender_id, amount_sen):
    """Explicit organizer action: freeze in BEGIN IMMEDIATE, then at most one PUT or GET."""
    if not _wire_slot.acquire(blocking=False):
        return _projection(_read(authority, credential, meal_id, config), 'BUSY', 2)
    try:
        # A suspended or cooling-down client would send nothing: freeze nothing either.
        refused = client.admission()
        if refused is not None:
            ctx = _read(authority, credential, meal_id, config)
            _decide(ctx, sender_id, amount_sen)  # Still report stale/active/confirmed refusals.
            return _projection(ctx, 'UNAVAILABLE', refused.get('retry_after'))

        def work():
            ctx = _context(authority, credential, meal_id, config)
            action, latest = _decide(ctx, sender_id, amount_sen)
            if action == 'CHECK':
                return 'GET', latest
            if action == 'RETRY':
                _update(authority, ctx, latest, state='REQUEST_UNKNOWN', not_created_reason=None,
                        dispatch_count=latest['dispatch_count'] + 1)
                return 'PUT', latest
            attempt = 1 if latest is None else latest['attempt'] + 1
            final_actor, final_command = ctx['finalize']
            reference = checkout_reference(config.namespace, meal_id, final_actor, final_command,
                                           sender_id, ctx['actor'], attempt)
            # The durable possible-dispatch marker is written before any byte is sent.
            authority._db.execute('''INSERT INTO checkout_demos
                (meal_id,attempt,finalize_actor_id,finalize_command_id,sender_id,receiver_id,amount_sen,
                 reference,initiated_by,created_at,state,dispatch_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)''',
                (meal_id, attempt, final_actor, final_command, sender_id, ctx['actor'], amount_sen,
                 reference, ctx['actor'], authority._now(), 'REQUEST_UNKNOWN'))
            return 'PUT', {'attempt': attempt, 'reference': reference, 'amount_sen': amount_sen}
        method, row = _transaction(authority, True, work, 'intent')
        # Recheck current organizer access after releasing the write lock.
        _require(authority.authenticate(credential, meal_id)[1], 'forbidden')
        _require(not authority._db.in_transaction, 'storage_error')
        observation = client.request(method, row['reference'], row['amount_sen'])
        return _store(authority, credential, meal_id, config, row['attempt'], row['reference'], method, observation)
    finally:
        _wire_slot.release()
