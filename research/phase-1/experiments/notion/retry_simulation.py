"""Disposable Phase 1 experiment. SQLite fake remote; NO HTTP or Notion SDK.

Run: python research/phase-1/experiments/notion/retry_simulation.py
Writes local synthetic evidence only. This is not an application sync adapter.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_SAFE_INTEGER = 2**53 - 1
MAX_ATTEMPTS = 4


def validate_money(payload):
    for key, value in payload.items():
        if key.endswith('_sen'):
            if type(value) is not int or abs(value) > MAX_SAFE_INTEGER:
                raise ValueError(f'{key} must be an integer within safe transport bounds')
    if payload['subtotal_sen'] - payload['discount_sen'] + payload['sst_sen'] + payload['service_sen'] + payload['rounding_sen'] != payload['final_sen']:
        raise ValueError('printed component reconciliation failed')


def canonical(payload):
    validate_money(payload)
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return body, hashlib.sha256(body.encode()).hexdigest()


def open_db(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS journal (
        operation TEXT PRIMARY KEY, body TEXT, digest TEXT, state TEXT,
        remote_id INTEGER, attempts INTEGER DEFAULT 0, retry_at INTEGER DEFAULT 0);
      CREATE TABLE IF NOT EXISTS fake_remote (
        id INTEGER PRIMARY KEY, operation TEXT, body TEXT);
    ''')
    return db


def enqueue(db, operation, payload):
    body, digest = canonical(payload)
    existing = db.execute('SELECT * FROM journal WHERE operation=?', (operation,)).fetchone()
    if existing and existing['digest'] != digest:
        raise ValueError('same operation/revision reused with a different payload')
    if not existing:
        db.execute('INSERT INTO journal(operation,body,digest,state) VALUES(?,?,?,?)', (operation, body, digest, 'pending'))
        db.commit()


def step(db, operation, now=0, outcome='success'):
    row = db.execute('SELECT * FROM journal WHERE operation=?', (operation,)).fetchone()
    if row['state'] in ('confirmed', 'blocked'):
        return row['state']
    if row['state'] == 'uncertain':
        matches = db.execute('SELECT * FROM fake_remote WHERE operation=?', (operation,)).fetchall()
        if len(matches) == 1 and matches[0]['body'] == row['body']:
            db.execute('UPDATE journal SET state=?,remote_id=? WHERE operation=?', ('confirmed', matches[0]['id'], operation))
        elif matches:
            db.execute('UPDATE journal SET state=? WHERE operation=?', ('blocked', operation))
        db.commit()
        return db.execute('SELECT state FROM journal WHERE operation=?', (operation,)).fetchone()[0]
    if now < row['retry_at']:
        return 'waiting'
    if row['attempts'] >= MAX_ATTEMPTS:
        db.execute('UPDATE journal SET state=? WHERE operation=?', ('blocked', operation))
        db.commit()
        return 'blocked'
    # Persist uncertainty BEFORE fake network activity; restart must reconcile.
    db.execute('UPDATE journal SET state=?,attempts=attempts+1 WHERE operation=?', ('uncertain', operation))
    db.commit()
    if outcome in ('429', '529'):
        # Fake server explicitly rejected before commit. Fake Retry-After = 17.
        db.execute('UPDATE journal SET state=?,retry_at=? WHERE operation=?', ('pending', now + 17, operation))
        db.commit()
        return 'rate-limited'
    if outcome == '403-plan':
        db.execute('UPDATE journal SET state=? WHERE operation=?', ('blocked', operation))
        db.commit()
        return 'blocked'
    if outcome == 'crash-before-send':
        return 'uncertain'
    cursor = db.execute('INSERT INTO fake_remote(operation,body) VALUES(?,?)', (operation, row['body']))
    remote_id = cursor.lastrowid
    db.commit()
    if outcome == 'commit-then-503':
        return 'uncertain'
    db.execute('UPDATE journal SET state=?,remote_id=? WHERE operation=?', ('confirmed', remote_id, operation))
    db.commit()
    return 'confirmed'


def main():
    path = ROOT / 'simulation.sqlite'
    db = open_db(path)
    # Reset only tables in this experiment's exact dedicated SQLite file.
    db.execute('DELETE FROM journal')
    db.execute('DELETE FROM fake_remote')
    db.commit()
    payload = dict(subtotal_sen=3001, discount_sen=101, sst_sen=174,
                   service_sen=290, rounding_sen=1, final_sen=3365)
    results = []

    for bad in (2000.5, True, MAX_SAFE_INTEGER + 1):
        try:
            validate_money({**payload, 'probe_sen': bad})
            raise AssertionError('invalid minor units accepted')
        except ValueError:
            results.append({'case': 'invalid_minor_units_rejected', 'value': bad, 'passed': True})

    for status in ('429', '529'):
        op = f'rate-{status}:r1'
        enqueue(db, op, payload)
        assert step(db, op, now=100, outcome=status) == 'rate-limited'
        assert step(db, op, now=116) == 'waiting'
        assert step(db, op, now=117) == 'confirmed'
        assert step(db, op, now=200) == 'confirmed'
        count = db.execute('SELECT COUNT(*) FROM fake_remote WHERE operation=?', (op,)).fetchone()[0]
        assert count == 1
        results.append({'case': f'{status}_retry_after', 'retry_at': 117, 'remote_rows': count, 'passed': True})

    op = 'uncertain-commit:r1'
    enqueue(db, op, payload)
    assert step(db, op, outcome='commit-then-503') == 'uncertain'
    db.close()
    db = open_db(path)  # Real SQLite reopen: durable restart, not memory-only.
    assert step(db, op) == 'confirmed'
    count = db.execute('SELECT COUNT(*) FROM fake_remote WHERE operation=?', (op,)).fetchone()[0]
    assert count == 1
    results.append({'case': 'commit_then_503_restart_reconcile', 'remote_rows': count, 'passed': True})

    op = 'uncertain-unsent:r1'
    enqueue(db, op, payload)
    assert step(db, op, outcome='crash-before-send') == 'uncertain'
    assert step(db, op) == 'uncertain'  # Zero matches cannot prove non-commit.
    assert db.execute('SELECT COUNT(*) FROM fake_remote WHERE operation=?', (op,)).fetchone()[0] == 0
    results.append({'case': 'zero_match_uncertainty_stays_manual', 'remote_rows': 0, 'passed': True})

    op = 'duplicate-matches:r1'
    enqueue(db, op, payload)
    assert step(db, op, outcome='commit-then-503') == 'uncertain'
    body = canonical(payload)[0]
    db.execute('INSERT INTO fake_remote(operation,body) VALUES(?,?)', (op, body))
    db.commit()
    assert step(db, op) == 'blocked'
    results.append({'case': 'multiple_matches_block_recreation', 'remote_rows': 2, 'passed': True})

    op = 'plan-limit:r1'
    enqueue(db, op, payload)
    assert step(db, op, outcome='403-plan') == 'blocked'
    assert step(db, op, now=9999) == 'blocked'
    results.append({'case': 'plan_error_not_retry_loop', 'passed': True})

    op = 'exhausted-retries:r1'
    enqueue(db, op, payload)
    for attempt in range(MAX_ATTEMPTS):
        assert step(db, op, now=attempt * 17, outcome='529') == 'rate-limited'
    assert step(db, op, now=MAX_ATTEMPTS * 17) == 'blocked'
    assert db.execute('SELECT attempts FROM journal WHERE operation=?', (op,)).fetchone()[0] == 4
    results.append({'case': 'retry_budget_exhaustion_blocks', 'attempts':4, 'passed':True})

    try:
        enqueue(db, 'uncertain-commit:r1', {**payload, 'final_sen':3366, 'rounding_sen':2})
        raise AssertionError('changed payload reused operation revision')
    except ValueError:
        results.append({'case': 'immutable_revision_rejects_mutation', 'passed': True})

    # A corrected revision is independent; completion waits for every child op.
    correction = {**payload, 'final_sen':3366, 'rounding_sen':2}
    operations = ['meal:r2', 'allocation-a:r2', 'allocation-b:r2']
    for operation in operations:
        enqueue(db, operation, correction)
    step(db, operations[0])
    step(db, operations[1])
    partial = [db.execute('SELECT state FROM journal WHERE operation=?', (x,)).fetchone()[0] for x in operations]
    assert not all(state == 'confirmed' for state in partial)
    step(db, operations[2])
    complete = all(db.execute('SELECT state FROM journal WHERE operation=?', (x,)).fetchone()[0] == 'confirmed' for x in operations)
    assert complete
    results.append({'case': 'new_revision_complete_only_after_all_children', 'partial_states': partial, 'complete': complete, 'passed': True})

    evidence = {'scope':'FAKE REMOTE ONLY; no network/API calls', 'money':'integer sen',
                'cases':results, 'passed':len(results), 'failed':0,
                'limitations':['No distributed worker locking', 'No real API retry, rate-limit or idempotency test',
                               'Fake reconciliation lookup is exact and immediate; real search can be stale',
                               'Complete marker is a projection convention, not a remote multi-page transaction']}
    (ROOT / 'simulation-results.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    db.close()
    print(json.dumps({'passed':len(results), 'failed':0, 'scope':evidence['scope']}))


if __name__ == '__main__':
    main()
