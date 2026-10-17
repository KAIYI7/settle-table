"""Durable local draft acceptance. Not an Internet authentication endpoint."""
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
import unicodedata

from . import calculation as calc


class AuthorityError(ValueError):
    """Safe public failure. Never includes credentials, commands or SQL."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Participant:
    id: str
    name: str
    organizer: bool = False


@dataclass(frozen=True, slots=True)
class SessionGrant:
    participant_id: str
    credential: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    meal_id: str
    sessions: tuple[SessionGrant, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class DraftSnapshot:
    meal_id: str
    revision: int
    financial_revision: int
    receipt_digest: str | None
    receipt: object
    items: tuple
    claims: tuple
    review: object
    calculation: calc.Calculation | None
    finalized: bool
    issues: tuple[str, ...]
    participants: tuple[Participant, ...]
    inactive_participant_ids: tuple[str, ...]


def _require(condition, code='invalid_input'):
    if not condition:
        raise AuthorityError(code)


def _id(value):
    _require(type(value) is str and 1 <= len(value) <= 64
             and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*', value) is not None)


def _text(value, maximum):
    _require(type(value) is str and 1 <= len(value) <= maximum)
    _require(not any(unicodedata.category(c) in ('Cc', 'Cs') for c in value))


def _tuple(value, maximum, minimum=0):
    _require(type(value) is tuple and minimum <= len(value) <= maximum)


def _wire(value):
    data = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')
    _require(len(data) <= 1_048_576, 'resource_limit')
    return data


def _verifier(credential):
    _require(type(credential) is str and len(credential) == 43
             and re.fullmatch(r'[A-Za-z0-9_-]{43}', credential) is not None,
             'invalid_session')
    return hashlib.sha256(b'settletable-local-session-v1\0' + credential.encode('ascii')).digest()


class Authority:
    """One SQLite connection; each instance may be used by its owning thread."""
    def __init__(self, path, *, clock=time.time, failure_hook=None):
        self._clock, self._failure_hook = clock, failure_hook
        self._db = None
        try:
            options = {'isolation_level': None, 'timeout': 1.0}
            if hasattr(sqlite3, 'LEGACY_TRANSACTION_CONTROL'):
                options['autocommit'] = sqlite3.LEGACY_TRANSACTION_CONTROL
            self._db = sqlite3.connect(path, **options)
            self._db.execute('PRAGMA foreign_keys=ON')
            self._db.executescript('''
                CREATE TABLE IF NOT EXISTS meals (
                    id TEXT PRIMARY KEY, state BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS participants (
                    meal_id TEXT NOT NULL REFERENCES meals(id), id TEXT NOT NULL,
                    name TEXT NOT NULL, organizer INTEGER NOT NULL, active INTEGER NOT NULL,
                    PRIMARY KEY(meal_id,id));
                CREATE TABLE IF NOT EXISTS sessions (
                    verifier BLOB PRIMARY KEY, meal_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                    expires REAL NOT NULL, revoked INTEGER NOT NULL,
                    UNIQUE(meal_id,participant_id),
                    FOREIGN KEY(meal_id,participant_id) REFERENCES participants(meal_id,id));
                CREATE TABLE IF NOT EXISTS commands (
                    meal_id TEXT NOT NULL, participant_id TEXT NOT NULL, command_id TEXT NOT NULL,
                    body BLOB NOT NULL, digest BLOB NOT NULL, result BLOB NOT NULL,
                    security INTEGER NOT NULL,
                    PRIMARY KEY(meal_id,participant_id,command_id),
                    FOREIGN KEY(meal_id,participant_id) REFERENCES participants(meal_id,id));
            ''')
        except sqlite3.Error:
            self.close()
            raise AuthorityError('storage_error') from None

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    def _now(self):
        value = self._clock()
        _require(type(value) in (int, float) and math.isfinite(value)
                 and abs(value) <= 1_000_000_000_000, 'storage_error')
        return value

    def _hook(self, stage):
        if self._failure_hook is not None:
            self._failure_hook(stage)

    def _rollback(self):
        if self._db is not None and self._db.in_transaction:
            self._db.execute('ROLLBACK')

    def _storage_failure(self, error):
        self._rollback()
        code = 'busy' if getattr(error, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else 'storage_error'
        raise AuthorityError(code) from None

    def bootstrap(self, meal_id, participants, *, session_ttl=3600):
        _id(meal_id)
        _tuple(participants, 100, 1)
        seen = set()
        for person in participants:
            _require(type(person) is Participant)
            _id(person.id)
            _text(person.name, 80)
            _require(type(person.organizer) is bool and person.id not in seen)
            seen.add(person.id)
        _require(sum(p.organizer for p in participants) == 1)
        _require(type(session_ttl) is int and 1 <= session_ttl <= 86400)
        grants = tuple(SessionGrant(p.id, secrets.token_urlsafe(32)) for p in participants)
        state = {'revision': 0, 'financial_revision': 0, 'receipt': None,
                 'item_revisions': {}, 'claims': [], 'review': None,
                 'calculation': None, 'retired_ids': []}
        committed = False
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            _require(self._db.execute('SELECT 1 FROM meals WHERE id=?', (meal_id,)).fetchone() is None, 'meal_exists')
            self._db.execute('INSERT INTO meals VALUES (?,?)', (meal_id, _wire(state)))
            expires = self._now() + session_ttl
            for person, grant in zip(participants, grants):
                self._db.execute('INSERT INTO participants VALUES (?,?,?,?,1)',
                                 (meal_id, person.id, person.name, int(person.organizer)))
                self._db.execute('INSERT INTO sessions VALUES (?,?,?,?,0)',
                                 (_verifier(grant.credential), meal_id, person.id, expires))
            self._hook('after_state')
            self._hook('before_commit')
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return BootstrapResult(meal_id, grants)
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('commit_uncertain' if committed else 'storage_error') from None

    def _authenticate(self, verifier, meal_id):
        row = self._db.execute('''SELECT p.id,p.organizer FROM sessions s
            JOIN participants p ON p.meal_id=s.meal_id AND p.id=s.participant_id
            WHERE s.verifier=? AND s.meal_id=? AND s.revoked=0 AND p.active=1 AND s.expires>?''',
            (verifier, meal_id, self._now())).fetchone()
        _require(row is not None, 'invalid_session')
        return row

    def snapshot(self, credential, meal_id):
        verifier = _verifier(credential)
        _id(meal_id)
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN')
            self._authenticate(verifier, meal_id)
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            people = self._db.execute('SELECT id,name,organizer,active FROM participants WHERE meal_id=? ORDER BY id', (meal_id,)).fetchall()
            result = DraftSnapshot(meal_id, state['revision'], state['financial_revision'], None, None,
                                   (), (), None, None, False, ('missing_receipt',),
                                   tuple(Participant(p[0], p[1], bool(p[2])) for p in people),
                                   tuple(p[0] for p in people if not p[3]))
            self._db.execute('COMMIT')
            return result
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None
