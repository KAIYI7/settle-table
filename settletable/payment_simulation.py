"""Optional nonfinancial allocation authorization; disabled without explicit config.

Only an amount and opaque reference are sent to a fixed operator-owned KaiPay
destination. This module never provisions credentials or enables a deployment.
"""
from dataclasses import dataclass, field
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

    def __post_init__(self):
        canonical_uuid(self.integration_id)
        canonical_uuid(self.namespace)
        if not re.fullmatch(r'kp_int_[A-Za-z0-9_-]{1,32}\.[A-Za-z0-9_-]{43}', self.credential):
            raise ValueError('invalid_simulation_configuration')
        try:
            url = urlsplit(self.base_url)
            if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
                    or url.path not in ('', '/') or url.query or url.fragment or len(self.base_url) > 512):
                raise ValueError()
            port = url.port or (443 if url.scheme == 'https' else 80)
            if not 1 <= port <= 65535:
                raise ValueError()
            if url.scheme == 'http' and url.hostname != 'localhost' and not ipaddress.ip_address(url.hostname).is_loopback:
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
            return cls(*(os.environ['SETTLETABLE_KAIPAY_' + name]
                         for name in ('INTEGRATION_ID', 'NAMESPACE', 'BASE_URL', 'CREDENTIAL')))
        except (KeyError, ValueError, TypeError):
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
    out['retryReady'] = out['state'] == 'REQUEST_UNKNOWN_CHECKED'
    if out['retryReady']:
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
    """Authority-owned short transaction: authorize, freeze or validate, commit."""
    attempted = False
    try:
        authority._db.execute('BEGIN IMMEDIATE' if create else 'BEGIN')
        basis = authority._finalized_allocation(credential, meal_id, participant_id, initiate=create)
        reference = client_reference(config.namespace, basis)
        basis_bytes = _wire(basis)
        row = _select(authority, config, reference)
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
        result = _projection(basis, reference, row[1:] if row else None)
        result['exists'] = row is not None
        authority._hook('simulation_before_intent_commit')
        attempted = True
        authority._db.execute('COMMIT')
        authority._hook('simulation_after_intent_commit')
        return result
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
            if outcome != 'NOT_SENT' or current['state'] == 'NOT_SENT':
                authority._db.execute('''UPDATE payment_simulations SET outcome=?,retry_after=?
                    WHERE integration_id=? AND client_reference=?''',
                    (outcome, observation.get('retry_after'), config.integration_id, reference))
            elif outcome == 'NOT_SENT' and current['state'] == 'REQUEST_UNKNOWN' and observation.get('checked'):
                authority._db.execute('''UPDATE payment_simulations SET outcome='REQUEST_UNKNOWN_CHECKED'
                    WHERE integration_id=? AND client_reference=?''', (config.integration_id, reference))
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


class KaiPayClient:
    """Direct HTTP(S), pinned startup DNS, no environment proxies or redirects."""
    def __init__(self, config):
        self.config = config
        self.url = urlsplit(config.base_url)
        self.port = self.url.port or (443 if self.url.scheme == 'https' else 80)
        self.addresses = tuple(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(
            self.url.hostname, self.port, type=socket.SOCK_STREAM)))
        if not self.addresses or (self.url.scheme == 'http' and
                                 not all(ipaddress.ip_address(a).is_loopback for a in self.addresses)):
            raise ValueError('invalid_simulation_configuration')
        self.context = ssl.create_default_context() if self.url.scheme == 'https' else None
        self.slots = threading.BoundedSemaphore(4)
        self.admission_lock = threading.Lock()
        self.retry_not_before = 0
        self.suspended = False

    def request(self, method, reference, amount):
        canonical_uuid(reference)
        with self.admission_lock:
            if self.suspended:
                return {'outcome': 'UNAVAILABLE'}
            if time.monotonic() < self.retry_not_before:
                return {'outcome': 'UNAVAILABLE', 'retry_after': max(1, int(self.retry_not_before - time.monotonic()) + 1)}
        if method not in ('GET', 'PUT') or not self.slots.acquire(blocking=False):
            return {'outcome': 'UNAVAILABLE', 'retry_after': 2}
        connection = None
        timer = None
        sockets = []
        def abort():
            for active in sockets:
                try:
                    active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        try:
            deadline = time.monotonic() + 5
            sock = socket.create_connection((self.addresses[0], self.port), timeout=2)
            sockets.append(sock)
            timer = threading.Timer(max(0.001, deadline - time.monotonic()), abort)
            timer.daemon = True
            timer.start()
            if self.context:
                sock.settimeout(max(0.001, deadline - time.monotonic()))
                sock = self.context.wrap_socket(sock, server_hostname=self.url.hostname, do_handshake_on_connect=False)
                sockets.append(sock)
                sock.do_handshake()
            connection = http.client.HTTPConnection(self.url.hostname, self.port, timeout=2)
            connection.sock = sock
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            body = json.dumps({'amountCents': amount, 'currency': 'MYR'}, separators=(',', ':')) if method == 'PUT' else None
            connection.request(method, '/v1/integrations/payments/' + reference, body=body,
                               headers={'Authorization': 'Bearer ' + self.config.credential,
                                        'Content-Type': 'application/json', 'Accept': 'application/json',
                                        'Connection': 'close'})
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            response = connection.getresponse()
            raw = bytearray()
            # read1 closes the response fp as soon as Content-Length reaches
            # zero. With HTTP/1.0 that also releases the connection's socket;
            # never reset its timeout after the completed body has closed it.
            while not response.isclosed():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                sock.settimeout(remaining)
                chunk = response.read1(min(1024, 8193 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > 8192:
                    raise ValueError('invalid_payment_response')
            if response.length not in (None, 0):
                raise ValueError('invalid_payment_response')
            if response.status == 200:
                if response.getheader('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                    raise ValueError('invalid_payment_response')
                payload = json.loads(raw, object_pairs_hook=_pairs,
                                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if type(payload) is not dict or payload.get('success') is not True:
                    raise ValueError('invalid_payment_response')
                return {'remote': validate_remote(payload.get('data'), reference, amount)}
            if response.status == 404 and method == 'GET':
                return {'outcome': 'NOT_SENT', 'checked': True}
            if response.status == 409:
                return {'outcome': 'CONFLICT'}
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
            if connection:
                connection.close()
            elif 'sock' in locals():
                sock.close()
            self.slots.release()


def perform_simulation(authority, credential, meal_id, participant_id, config, client, *, initiate=False):
    intent = authority.payment_simulation(credential, meal_id, participant_id, config, create=initiate)
    if not intent['exists'] or intent['state'] == 'NO_PAYMENT_NEEDED' or (initiate and intent['state'] in TERMINAL):
        return intent
    intent = authority.payment_simulation(credential, meal_id, participant_id, config)
    if initiate:
        actor, organizer = authority.authenticate(credential, meal_id)
        _require(organizer, 'forbidden')
    _require(not authority._db.in_transaction, 'storage_error')
    method = 'PUT' if initiate else 'GET'
    if initiate and intent['state'] == 'REQUEST_UNKNOWN' and not intent['retryReady']:
        method = 'GET'
    observation = client.request(method, intent['clientReference'], intent['basis']['amountCents'])
    return authority.observe_payment_simulation(credential, meal_id, participant_id, config, observation)
