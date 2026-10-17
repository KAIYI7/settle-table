"""Disposable old-package/new-package SQLite compatibility, not routine CI.

Needs local authority-v1-accepted Git history. Only safe summaries leave the
driver; generated credentials travel through captured child-process pipes.
"""
import argparse
from contextlib import closing
from dataclasses import fields, is_dataclass
from fractions import Fraction
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
EXPECTED = {
    'calculation.py': '4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a',
    'authority.py': '1eef9e7959639de5407bc445e9344f3ef7e0bb9502bafcfb2026d2c794ed81f0',
}


def require(condition):
    if not condition:
        raise RuntimeError('compatibility assertion failed')


def normalize(value):
    if is_dataclass(value):
        return {f.name: normalize(getattr(value, f.name)) for f in fields(value)}
    if type(value) is Fraction:
        return [value.numerator, value.denominator]
    if type(value) is bytes:
        return {'hex': value.hex()}
    if type(value) in (tuple, list):
        return [normalize(v) for v in value]
    if type(value) is dict:
        return {k: normalize(v) for k, v in value.items()}
    return value


def persisted(path):
    with closing(sqlite3.connect(path)) as db:
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        tables = {name: db.execute('SELECT * FROM ' + name + ' ORDER BY ' + order).fetchall()
                  for name, order in (('meals', '1'), ('participants', '1,2'),
                                      ('sessions', '1'), ('commands', '1,2,3'))}
    return normalize({'schema': schema, 'tables': tables})


def vectors(calc):
    split = calc.Split('equal', (calc.Share('A', 1), calc.Share('B', 1)))
    tiny = calc.Meal(('A', 'B'), (calc.Item('tiny', 1, split),), 1, 1)
    require(tuple(p.sen for p in calc.calculate(tiny).consumption) == (0, 1))
    base = calc.Item('base', 2, calc.Split('exact', (calc.Share('A', 1), calc.Share('B', 1))))
    for amount, expected in ((1, (1, 2)), (-1, (1, 0))):
        meal = calc.Meal(('A', 'B'), (base,), 2, 2 + amount,
                         (calc.Adjustment('tiny', 'rounding', amount, split=split),))
        require(tuple(p.sen for p in calc.calculate(meal).consumption) == expected)


def commands(auth, meal, digest):
    receipt = auth.Receipt((auth.ReceiptItem('dish', 'Shared rice', 3, 1001),), 1001, 1001)
    initial = [('O', auth.ReplaceReceipt('receipt', 0, 0, receipt))]
    if meal == 'final':
        return initial + [
            ('A', auth.SetOwnQuantity('claim-a', 'dish', 1, 1, 1)),
            ('B', auth.SetOwnQuantity('claim-b', 'dish', 2, 2, 1)),
            ('O', auth.ReviewReceipt('review', 3, 1, digest)),
            ('O', auth.Finalize('finalize', 4, 1)),
        ]
    if meal == 'draft':
        return initial + [('A', auth.SetOwnQuantity('claim-a', 'dish', Fraction(1, 1), 1, 1))]
    return initial + [
        ('B', auth.SetOwnQuantity('claim-b', 'dish', 1, 1, 1)),
        ('O', auth.RevokeSession('revoke-session', 2, 'B')),
        ('O', auth.RevokeMembership('revoke-membership', 3, 'B')),
    ]


def worker(mode, payload):
    sys.path.insert(0, payload['package_root'])
    auth = importlib.import_module(payload['namespace'] + '.authority')
    calc = importlib.import_module(payload['namespace'] + '.calculation')
    vectors(calc)
    path = Path(payload['database'])
    authority = auth.Authority(path, clock=lambda: 1000)
    try:
        if mode == 'prepare':
            credentials, snapshots, saved = {}, {}, {}
            for meal in ('final', 'draft', 'revoked'):
                grants = authority.bootstrap(meal, (
                    auth.Participant('O', 'Organizer', True), auth.Participant('A', 'Alice'),
                    auth.Participant('B', 'Bob'))).sessions
                credentials[meal] = {g.participant_id: g.credential for g in grants}
                rows = []
                for actor, command in commands(auth, meal, '0' * 64):
                    if type(command) is auth.ReviewReceipt:
                        digest = authority.snapshot(credentials[meal]['O'], meal).receipt_digest
                        command = auth.ReviewReceipt('review', 3, 1, digest)
                    result = authority.apply(credentials[meal][actor], meal, command)
                    rows.append(result.canonical_bytes.hex())
                saved[meal] = rows
                snapshots[meal] = normalize(authority.snapshot(credentials[meal]['O'], meal))
            grant = authority.bootstrap('expired', (auth.Participant('O', 'Organizer', True),), session_ttl=1).sessions[0]
            credentials['expired'] = {'O': grant.credential}
            return {'credentials': credentials, 'snapshots': snapshots, 'saved': saved,
                    'persisted': persisted(path)}

        old = payload['old']
        credentials = old['credentials']
        require(persisted(path) == old['persisted'])
        replay_count = 0
        for meal in ('final', 'draft', 'revoked'):
            snapshot = authority.snapshot(credentials[meal]['O'], meal)
            require(normalize(snapshot) == old['snapshots'][meal])
            digest = snapshot.receipt_digest
            for index, (actor, command) in enumerate(commands(auth, meal, digest)):
                if meal == 'revoked' and actor == 'B':
                    try:
                        authority.apply(credentials[meal][actor], meal, command)
                    except auth.AuthorityError as error:
                        require(error.code == 'invalid_session')
                    else:
                        require(False)
                    continue
                result = authority.apply(credentials[meal][actor], meal, command)
                require(result.canonical_bytes.hex() == old['saved'][meal][index])
                replay_count += 1
            require(normalize(authority.snapshot(credentials[meal]['O'], meal)) == old['snapshots'][meal])
        require(persisted(path) == old['persisted'])
        try:
            authority.apply(credentials['draft']['O'], 'draft', auth.ReplaceReceipt('receipt', 0, 0, auth.Receipt()))
        except auth.AuthorityError as error:
            require(error.code == 'command_conflict')
        else:
            require(False)
        require(persisted(path) == old['persisted'])
        for operation in (
            lambda: authority.snapshot(credentials['revoked']['B'], 'revoked'),
            lambda: authority.apply(credentials['revoked']['B'], 'revoked', commands(auth, 'revoked', None)[1][1]),
        ):
            try:
                operation()
            except auth.AuthorityError as error:
                require(error.code == 'invalid_session')
            else:
                require(False)
        expired = auth.Authority(path, clock=lambda: 1001)
        try:
            try:
                expired.snapshot(credentials['expired']['O'], 'expired')
            except auth.AuthorityError as error:
                require(error.code == 'invalid_session')
            else:
                require(False)
        finally:
            expired.close()
        before = persisted(path)
        result = authority.apply(credentials['draft']['B'], 'draft',
                                 auth.SetOwnQuantity('new-after-rename', 'dish', 2, 2, 1))
        require((result.revision, result.financial_revision) == (3, 1))
        require(authority.snapshot(credentials['draft']['O'], 'draft').revision == 3)
        after = persisted(path)
        require(before['schema'] == after['schema'])
        require(all(row in after['tables']['commands'] for row in before['tables']['commands']))
        require(before['tables']['sessions'] == after['tables']['sessions'])
        return {'authorized_exact_replays': replay_count, 'old_snapshots_equal': 3,
                'revoked_and_expired_denied': True, 'changed_payload_denied': True,
                'history_schema_verifiers_unchanged': True, 'new_draft_command_revision': 3,
                'tie_and_signed_vectors': 'PASS'}
    finally:
        authority.close()


def child(mode, payload):
    process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', mode],
                             input=json.dumps(payload), text=True, capture_output=True,
                             cwd=payload['package_root'], timeout=30)
    # Child diagnostics could include ambient information; never forward them.
    require(process.returncode == 0 and not process.stderr)
    return json.loads(process.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('prepare', 'verify'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.worker:
        try:
            response = worker(args.worker, json.load(sys.stdin))
        except Exception:
            print('compatibility worker failed', file=sys.stderr)
            return 1
        print(json.dumps(response))
        return 0
    scratch = ROOT / '.local' / 'namespace-compatibility'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        temporary = Path(temporary)
        old_root = temporary / 'accepted'
        old_package = old_root / 'tabwise'
        old_package.mkdir(parents=True)
        for filename in ('__init__.py', 'calculation.py', 'authority.py'):
            source = subprocess.run(['git', 'show', 'authority-v1-accepted:tabwise/' + filename],
                                    cwd=ROOT, capture_output=True, timeout=15)
            require(source.returncode == 0)
            if filename in EXPECTED:
                require(hashlib.sha256(source.stdout).hexdigest() == EXPECTED[filename])
                require(hashlib.sha256((ROOT / 'settletable' / filename).read_bytes()).hexdigest() == EXPECTED[filename])
            (old_package / filename).write_bytes(source.stdout)
        database = temporary / 'compatibility.sqlite'
        old = child('prepare', {'package_root': str(old_root), 'namespace': 'tabwise', 'database': str(database)})
        result = child('verify', {'package_root': str(ROOT), 'namespace': 'settletable', 'database': str(database), 'old': old})
        # Inspect every disposable file after all child connections are closed.
        for path in temporary.rglob('*'):
            if path.is_file():
                data = path.read_bytes()
                for grants in old['credentials'].values():
                    require(all(credential.encode('ascii') not in data for credential in grants.values()))
        result.update(status='PASS', baseline='authority-v1-accepted', source_sha256=EXPECTED,
                      raw_credentials_in_disposable_files=False,
                      credential_transport='transient captured subprocess pipes only')
    safe = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(safe, encoding='utf-8')
    print(safe, end='')
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception:
        print('namespace compatibility failed; no private diagnostics emitted', file=sys.stderr)
        code = 1
    raise SystemExit(code)
