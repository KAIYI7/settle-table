"""Optional nonfinancial allocation authorization; disabled without explicit config.

Only an amount and opaque reference are sent to a fixed operator-owned KaiPay
destination. This module never provisions credentials or enables a deployment.
"""
from dataclasses import dataclass, field
from concurrent.futures import Future
from datetime import datetime
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

from .authority import AuthorityError, _require, _wire

PURPOSE = 'allocation-authorization-v1'
CHECKED_ABSENT = 'REQUEST_UNKNOWN_CONFIRMED_ABSENT'
LEGACY_UNCERTAIN = {'NOT_SENT', 'UNAVAILABLE', 'REQUEST_UNKNOWN_CHECKED'}
RESPONSE_LIMIT = 8192
# The deployment has one WSGI worker. Keep a status check from racing a PUT
# within that worker, and leave request threads free for ordinary meal work.
_wire_slot = threading.Lock()
TERMINAL = {'AUTHORIZED', 'DECLINED', 'FAILED', 'CONFLICT', 'UNEXPECTED_STATUS', 'NO_PAYMENT_NEEDED'}
REMOTE_STATES = {'CREATED': 'PENDING', 'PROCESSING': 'PENDING', 'AUTHORIZED': 'AUTHORIZED',
                 'DECLINED': 'DECLINED', 'FAILED': 'FAILED'}


def canonical_uuid(value):
    if type(value) is not str or len(value) != 36 or str(uuid.UUID(value)) != value:
        raise ValueError('invalid_simulation_configuration')
    return value


@dataclass(frozen=True)
class SimulationConfig:
    integration_id: str
    namespace: str
    base_url: str
    credential: str = field(repr=False)
    access_client_id: str | None = field(default=None, repr=False)
    access_client_secret: str | None = field(default=None, repr=False)

    def __post_init__(self):
        canonical_uuid(self.integration_id)
        canonical_uuid(self.namespace)
        if not re.fullmatch(r'kp_int_[A-Za-z0-9_-]{1,32}\.[A-Za-z0-9_-]{43}', self.credential):
            raise ValueError('invalid_simulation_configuration')
        try:
            url = urlsplit(self.base_url)
            if (url.scheme not in ('http', 'https') or not url.hostname
                    or url.username is not None or url.password is not None
                    or url.path not in ('', '/') or '?' in self.base_url or '#' in self.base_url
                    or not re.fullmatch(r'[!-~]{1,512}', self.base_url)):
                raise ValueError()
            if url.port is not None and url.port == 0:
                raise ValueError()
            if url.scheme == 'http' and url.hostname != 'localhost' and not ipaddress.ip_address(url.hostname).is_loopback:
                raise ValueError()
            access = (self.access_client_id, self.access_client_secret)
            if any(value is not None for value in access):
                if url.scheme != 'https' or not all(
                        isinstance(value, str) and re.fullmatch(r'[!-~]{1,512}', value) for value in access):
                    raise ValueError()
            if url.hostname.rstrip('.') == 'api.kybuilds.com' and (
                    not self.access_client_id or url.port not in (None, 443)):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('invalid_simulation_configuration') from None

    @classmethod
    def from_env(cls):
        enabled = os.environ.get('SETTLETABLE_KAIPAY_ENABLED', '0')
        if enabled == '0':
            return None
        if enabled != '1':
            raise ValueError('invalid_simulation_configuration')
        try:
            prefix = 'SETTLETABLE_KAIPAY_'
            binding = [os.environ[prefix + name] for name in ('INTEGRATION_ID', 'NAMESPACE', 'BASE_URL')]
            credentials = {name: os.environ[prefix + name.upper()]
                           for name in ('credential', 'access_client_id', 'access_client_secret')
                           if prefix + name.upper() in os.environ}
            secret_file = os.environ.get(prefix + 'CREDENTIALS_FILE')
            if secret_file:
                if credentials:
                    raise ValueError()
                with open(secret_file, 'rb') as stream:
                    raw = stream.read(4097)
                if len(raw) > 4096:
                    raise ValueError()
                credentials = json.loads(raw, object_pairs_hook=_pairs)
                if type(credentials) is not dict or not all(type(value) is str for value in credentials.values()):
                    raise ValueError()
            return cls(*binding, **credentials)
        except (KeyError, ValueError, TypeError, OSError, RecursionError):
            raise ValueError('invalid_simulation_configuration') from None


def client_reference(namespace, basis):
    name = json.dumps([PURPOSE, basis['meal_id'], basis['finalize_actor_id'],
                       basis['finalize_command_id'], basis['participant_id']],
                      ensure_ascii=True, separators=(',', ':'))
    return str(uuid.uuid5(uuid.UUID(namespace), name))


def _projection(basis, reference, row=None):
    out = {'state': 'NOT_SENT', 'clientReference': reference, 'basis': basis,
           'paymentId': None, 'paymentVersion': None, 'paymentStatus': None,
           'paymentUpdatedAt': None, 'observedAt': None, 'retryAfter': None, 'simulation': True}
    if row is not None:
        out.update(zip(('paymentId', 'paymentVersion', 'paymentStatus', 'paymentUpdatedAt',
                        'observedAt', 'state', 'retryAfter'), row))
    out['retryReady'] = out['state'] == CHECKED_ABSENT
    # Older versions could leave any of these states after a possible PUT.
    if out['retryReady'] or (row is not None and out['state'] in LEGACY_UNCERTAIN):
        out['state'] = 'REQUEST_UNKNOWN'
    if basis['amountCents'] == 0:
        out['state'] = 'NO_PAYMENT_NEEDED'
    return out


def _select(authority, config, reference):
    return authority._db.execute('''SELECT basis,payment_id,payment_version,payment_status,
        payment_updated_at,observed_at,outcome,retry_after FROM payment_simulations
        WHERE integration_id=? AND client_reference=?''', (config.integration_id, reference)).fetchone()


def _transaction_failure(authority, error, attempted):
    uncertain = attempted and not authority._db.in_transaction
    authority._rollback()
    if uncertain:
        raise AuthorityError('commit_uncertain') from None
    if isinstance(error, AuthorityError):
        raise error
    if isinstance(error, sqlite3.Error):
        authority._storage_failure(error)
    if isinstance(error, RuntimeError):
        raise AuthorityError('storage_error') from None
    raise AuthorityError('invalid_finalization_basis') from None


def simulation_intent(authority, credential, meal_id, participant_id, config, *, create=False):
    intent, _ = _simulation_intent(authority, credential, meal_id, participant_id, config, create=create)
    return intent


def _simulation_intent(authority, credential, meal_id, participant_id, config, *, create=False, prepare_put=False):
    """Authority-owned short transaction: authorize, freeze or validate, commit."""
    attempted = False
    try:
        authority._db.execute('BEGIN IMMEDIATE' if create else 'BEGIN')
        basis = authority._finalized_allocation(credential, meal_id, participant_id, initiate=create)
        reference = client_reference(config.namespace, basis)
        basis_bytes = _wire(basis)
        row = _select(authority, config, reference)
        prior = _projection(basis, reference, row[1:] if row else None)
        may_dispatch = prepare_put and basis['amountCents'] > 0 and (
            row is None or (prior['paymentVersion'] is None and prior['retryReady']))
        if row is None and create:
            authority._db.execute('''INSERT INTO payment_simulations
                (integration_id,meal_id,finalize_actor_id,finalize_command_id,participant_id,
                 purpose_version,client_reference,basis,outcome) VALUES (?,?,?,?,?,?,?,?,?)''',
                (config.integration_id, meal_id, basis['finalize_actor_id'], basis['finalize_command_id'],
                 participant_id, PURPOSE, reference, basis_bytes,
                 'NO_PAYMENT_NEEDED' if basis['amountCents'] == 0 else 'NOT_SENT'))
            row = _select(authority, config, reference)
        if row is not None:
            _require(row[0] == basis_bytes, 'simulation_conflict')
        if may_dispatch:
            # Consume any checked absence and durably mark possible dispatch
            # before leaving this transaction to send even the first byte.
            authority._db.execute('''UPDATE payment_simulations SET outcome=?,retry_after=NULL
                WHERE integration_id=? AND client_reference=?''',
                ('REQUEST_UNKNOWN', config.integration_id, reference))
            row = _select(authority, config, reference)
        result = _projection(basis, reference, row[1:] if row else None)
        result['exists'] = row is not None
        authority._hook('simulation_before_intent_commit')
        attempted = True
        authority._db.execute('COMMIT')
        authority._hook('simulation_after_intent_commit')
        return result, may_dispatch
    except Exception as error:
        _transaction_failure(authority, error, attempted)


def store_observation(authority, credential, meal_id, participant_id, config, observation):
    """Old responses and transport outcomes cannot regress newer remote evidence."""
    attempted = False
    try:
        authority._db.execute('BEGIN IMMEDIATE')
        basis = authority._finalized_allocation(credential, meal_id, participant_id)
        reference = client_reference(config.namespace, basis)
        row = _select(authority, config, reference)
        _require(row is not None and row[0] == _wire(basis), 'simulation_conflict')
        current = _projection(basis, reference, row[1:])
        remote = observation.get('remote')
        if remote is not None:
            validate_remote(remote, reference, basis['amountCents'])
            old_version = current['paymentVersion']
            if current['paymentId'] is not None:
                _require(remote['paymentId'] == current['paymentId'], 'simulation_conflict')
            if old_version is not None and remote['version'] == old_version:
                _require((remote['status'], remote['updatedAt']) ==
                         (current['paymentStatus'], current['paymentUpdatedAt']), 'simulation_conflict')
            if old_version is None or remote['version'] > old_version:
                if old_version is not None:
                    _require(current['paymentStatus'] not in ('AUTHORIZED', 'DECLINED', 'FAILED')
                             or current['paymentStatus'] == remote['status']
                             or remote['status'] not in REMOTE_STATES, 'simulation_conflict')
                    _require(not (current['paymentStatus'] == 'PROCESSING' and remote['status'] == 'CREATED'),
                             'simulation_conflict')
                authority._db.execute('''UPDATE payment_simulations SET payment_id=?,payment_version=?,
                    payment_status=?,payment_updated_at=?,observed_at=?,outcome=?,retry_after=NULL
                    WHERE integration_id=? AND client_reference=?''',
                    (remote['paymentId'], remote['version'], remote['status'], remote['updatedAt'], authority._now(),
                     REMOTE_STATES.get(remote['status'], 'UNEXPECTED_STATUS'), config.integration_id, reference))
        elif current['paymentVersion'] is None and current['state'] not in TERMINAL:
            outcome = observation.get('outcome')
            _require(outcome in ('REQUEST_UNKNOWN', 'UNAVAILABLE', 'CONFLICT', 'NOT_SENT'), 'invalid_input')
            if outcome == 'NOT_SENT' and observation.get('checked') is True:
                outcome = CHECKED_ABSENT
            elif outcome != 'CONFLICT':
                outcome = 'REQUEST_UNKNOWN'
            authority._db.execute('''UPDATE payment_simulations SET outcome=?,retry_after=?
                WHERE integration_id=? AND client_reference=?''',
                (outcome, observation.get('retry_after'), config.integration_id, reference))
        authority._hook('simulation_before_observation_commit')
        attempted = True
        authority._db.execute('COMMIT')
        authority._hook('simulation_after_observation_commit')
    except Exception as error:
        _transaction_failure(authority, error, attempted)
    return simulation_intent(authority, credential, meal_id, participant_id, config)


def validate_remote(data, reference, amount):
    if type(data) is not dict or set(data) != {'clientReference', 'paymentId', 'amountCents', 'currency',
                                              'status', 'version', 'simulation', 'updatedAt'}:
        raise ValueError('invalid_payment_response')
    canonical_uuid(data['paymentId'])
    if (data['clientReference'] != reference or type(data['amountCents']) is not int
            or data['amountCents'] != amount or data['currency'] != 'MYR' or data['simulation'] is not True
            or type(data['version']) is not int or not 0 <= data['version'] <= 9_223_372_036_854_775_807
            or type(data['status']) is not str or not re.fullmatch(r'[A-Z][A-Z_]{0,39}', data['status'])
            or type(data['updatedAt']) is not str or not 20 <= len(data['updatedAt']) <= 40
            or datetime.fromisoformat(data['updatedAt'].replace('Z', '+00:00')).tzinfo is None):
        raise ValueError('invalid_payment_response')
    return data


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('invalid_payment_response')
        result[key] = value
    return result


def _read_absence_body(response):
    """Require the gateway's unambiguous framing before trusting absence."""
    lengths = [value.strip(' \t') for value in response.headers.get_all('Content-Length', [])]
    encodings = [value.strip(' \t').lower() for value in response.headers.get_all('Transfer-Encoding', [])]
    if response.headers.defects:
        raise ValueError('invalid_payment_response')
    if len(lengths) == 1 and not encodings and re.fullmatch(r'0|[1-9][0-9]{0,3}', lengths[0]):
        if int(lengths[0]) <= RESPONSE_LIMIT:
            return response.read()
    if lengths or encodings != ['chunked'] or response.version != 11:
        raise ValueError('invalid_payment_response')

    # http.client tolerates EOF before the terminating trailer and discards
    # chunk separators without checking them. Use its buffered wire stream
    # here to enforce the same chunk framing as the KaiPay gateway.
    raw = bytearray()
    while True:
        size = response.fp.readline(11)
        if not re.fullmatch(rb'[0-9A-Fa-f]{1,8}\r\n', size):
            raise ValueError('invalid_payment_response')
        count = int(size, 16)
        if count > RESPONSE_LIMIT - len(raw):
            raise ValueError('invalid_payment_response')
        chunk = response.fp.read(count + 2)
        if len(chunk) != count + 2 or not chunk.endswith(b'\r\n'):
            raise ValueError('invalid_payment_response')
        if count == 0:
            return raw
        raw.extend(chunk[:-2])


class KaiPayClient:
    """Direct HTTP(S) to one configured origin, without proxies or redirects."""
    def __init__(self, config):
        self.config = config
        self.url = urlsplit(config.base_url)
        self.port = self.url.port or (443 if self.url.scheme == 'https' else 80)
        self.context = ssl.create_default_context() if self.url.scheme == 'https' else None
        self.resolver_lock = threading.Lock()
        self.lookup = None
        self.admission_lock = threading.Lock()
        self.retry_not_before = 0
        self.suspended = False

    def _resolve(self, deadline):
        # getaddrinfo has no per-call timeout. Share at most one outstanding
        # lookup and let it finish without keeping a WSGI thread waiting.
        with self.resolver_lock:
            if self.lookup is None or self.lookup.done():
                lookup = Future()
                self.lookup = lookup

                def resolve():
                    try:
                        lookup.set_result(socket.getaddrinfo(self.url.hostname, self.port, type=socket.SOCK_STREAM))
                    except (OSError, ValueError) as error:
                        lookup.set_exception(error)

                threading.Thread(target=resolve, daemon=True).start()
            else:
                lookup = self.lookup
        addresses = tuple(dict.fromkeys((family, address) for family, _, _, _, address in
                                       lookup.result(timeout=max(0, deadline - time.monotonic()))))
        if not addresses or (self.context is None and not all(
                ipaddress.ip_address(address[0]).is_loopback for _, address in addresses)):
            raise ValueError('invalid_simulation_destination')
        return addresses[:4]

    def _connect(self, deadline):
        addresses = self._resolve(deadline)
        for index, (family, address) in enumerate(addresses):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            attempt_deadline = time.monotonic() + remaining / (len(addresses) - index)
            sock = None
            try:
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.settimeout(max(0.001, attempt_deadline - time.monotonic()))
                sock.connect(address)
                if self.context:
                    sock = self.context.wrap_socket(sock, server_hostname=self.url.hostname,
                                                    do_handshake_on_connect=False)
                    sock.settimeout(max(0.001, attempt_deadline - time.monotonic()))
                    sock.do_handshake()
                return sock
            except (OSError, ValueError):
                if sock is not None:
                    sock.close()
        raise OSError('simulation_connection_unavailable')

    def request(self, method, reference, amount):
        canonical_uuid(reference)
        with self.admission_lock:
            if self.suspended:
                return {'outcome': 'UNAVAILABLE'}
            if time.monotonic() < self.retry_not_before:
                return {'outcome': 'UNAVAILABLE', 'retry_after': max(1, int(self.retry_not_before - time.monotonic()) + 1)}
        if method not in ('GET', 'PUT'):
            return {'outcome': 'UNAVAILABLE', 'retry_after': 2}
        connection = None
        response = None
        sock = None
        timer = None

        def abort():
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        try:
            started = time.monotonic()
            deadline = started + 5
            # Resolve and try candidate connections before handing the socket
            # to HTTP. There is no address fallback once sending can begin.
            sock = self._connect(started + 2)
            timer = threading.Timer(max(0.001, deadline - time.monotonic()), abort)
            timer.daemon = True
            timer.start()
            connection = http.client.HTTPConnection(self.url.hostname, self.port, timeout=2)
            connection.sock = sock
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            headers = {'Authorization': 'Bearer ' + self.config.credential, 'Accept': 'application/json',
                       'Connection': 'close'}
            if self.config.access_client_id is not None:
                headers.update({'CF-Access-Client-Id': self.config.access_client_id,
                                'CF-Access-Client-Secret': self.config.access_client_secret})
            body = None
            if method == 'PUT':
                headers['Content-Type'] = 'application/json'
                body = json.dumps({'amountCents': amount, 'currency': 'MYR'}, separators=(',', ':'))
            connection.request(method, '/v1/integrations/payments/' + reference, body=body, headers=headers)
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            response = connection.getresponse()
            if response.status == 404 and method == 'GET':
                raw = _read_absence_body(response)
            else:
                raw = bytearray()
                # read1 can close the response file and its HTTP/1.0 socket
                # once Content-Length reaches zero.
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
                        raise ValueError('invalid_payment_response')
                if response.length not in (None, 0):
                    raise ValueError('invalid_payment_response')
            if time.monotonic() >= deadline:
                raise TimeoutError()
            if response.status in (200, 404, 409):
                types = response.headers.get_all('Content-Type', [])
                if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
                    raise ValueError('invalid_payment_response')
                payload = json.loads(raw, object_pairs_hook=_pairs,
                                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if type(payload) is not dict:
                    raise ValueError('invalid_payment_response')
                if response.status == 200 and payload.get('success') is True:
                    return {'remote': validate_remote(payload.get('data'), reference, amount)}
                # The KaiPay error contract has no reference field. It applies
                # to the canonical reference in this request's exact path.
                if (set(payload) == {'success', 'status', 'code', 'message'} and payload['success'] is False
                        and type(payload['status']) is int and payload['status'] == response.status
                        and type(payload['message']) is str and payload['message']):
                    if response.status == 404 and method == 'GET' and payload['code'] == 'NOT_FOUND':
                        return {'outcome': 'NOT_SENT', 'checked': True}
                    if response.status == 409 and payload['code'] in ('IDEMPOTENCY_CONFLICT', 'RECOVERY_REQUIRED'):
                        return {'outcome': 'CONFLICT'}
                raise ValueError('invalid_payment_response')
            retry = response.getheader('Retry-After', '')
            retry = max(1, min(120, int(retry))) if re.fullmatch(r'[0-9]{1,3}', retry) else None
            with self.admission_lock:
                if response.status in (400, 401, 403):
                    self.suspended = True
                if response.status == 429:
                    retry = retry or 1
                    self.retry_not_before = max(self.retry_not_before, time.monotonic() + retry)
            return {'outcome': 'UNAVAILABLE' if response.status in (400, 401, 403, 429) else
                    'REQUEST_UNKNOWN' if method == 'PUT' else 'UNAVAILABLE', 'retry_after': retry}
        except (OSError, ValueError, http.client.HTTPException, RecursionError):
            return {'outcome': 'REQUEST_UNKNOWN' if method == 'PUT' else 'UNAVAILABLE'}
        finally:
            if timer:
                timer.cancel()
            if response:
                response.close()
            if connection:
                connection.close()
            if sock is not None:
                sock.close()


def perform_simulation(authority, credential, meal_id, participant_id, config, client, *, initiate=False):
    if not _wire_slot.acquire(blocking=False):
        if initiate:
            _require(authority.authenticate(credential, meal_id)[1], 'forbidden')
        intent = simulation_intent(authority, credential, meal_id, participant_id, config)
        if intent['state'] not in TERMINAL and (initiate or intent['exists']):
            intent.update(retryAfter=2, retryReady=False)
            if not intent['exists']:
                intent['state'] = 'UNAVAILABLE'
        return intent
    try:
        intent, may_dispatch = _simulation_intent(authority, credential, meal_id, participant_id, config,
                                                   create=initiate, prepare_put=initiate)
        if not intent['exists'] or intent['state'] == 'NO_PAYMENT_NEEDED' or (initiate and intent['state'] in TERMINAL):
            return intent
        if initiate:
            _require(authority.authenticate(credential, meal_id)[1], 'forbidden')
        _require(not authority._db.in_transaction, 'storage_error')
        method = 'PUT' if may_dispatch else 'GET'
        observation = client.request(method, intent['clientReference'], intent['basis']['amountCents'])
        return authority.observe_payment_simulation(credential, meal_id, participant_id, config, observation)
    finally:
        _wire_slot.release()
