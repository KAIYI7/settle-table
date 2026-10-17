"""DISPOSABLE SQLite transaction probe; no production imports, HTTP or accounts.

Run: python research/phase-2/experiments/transactions/probe.py
Each run creates a uniquely named scratch DB here, never resets an existing DB.
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_MONEY = 10**9  # Experimental bound (sen), not a final product policy.


class Conflict(ValueError):
    pass


def integer(value, name, minimum=0, maximum=MAX_MONEY):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be a bounded integer')
    return value


def body_text(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def connect(path, timeout=5):
    db = sqlite3.connect(path, timeout=timeout, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA synchronous=FULL')
    return db


def create(path):
    db = connect(path)
    assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
    db.executescript('''
      CREATE TABLE meals(id TEXT PRIMARY KEY, total_sen INTEGER NOT NULL
        CHECK(total_sen BETWEEN 0 AND 1000000000), revision INTEGER NOT NULL,
        finalized_revision INTEGER) STRICT;
      CREATE TABLE items(id TEXT PRIMARY KEY, meal TEXT NOT NULL REFERENCES meals(id),
        quantity INTEGER NOT NULL CHECK(quantity>0), line_sen INTEGER NOT NULL
        CHECK(line_sen BETWEEN 0 AND 1000000000), revision INTEGER NOT NULL) STRICT;
      CREATE TABLE claims(item TEXT REFERENCES items(id), person TEXT,
        units INTEGER NOT NULL CHECK(units>0), PRIMARY KEY(item,person)) STRICT;
      CREATE TABLE commands(actor TEXT, meal TEXT REFERENCES meals(id), command_id TEXT,
        body TEXT NOT NULL, digest TEXT NOT NULL, result TEXT NOT NULL,
        PRIMARY KEY(actor,meal,command_id)) STRICT;
      CREATE TRIGGER command_no_update BEFORE UPDATE ON commands
        BEGIN SELECT RAISE(ABORT,'immutable command result'); END;
      CREATE TRIGGER command_no_delete BEFORE DELETE ON commands
        BEGIN SELECT RAISE(ABORT,'immutable command result'); END;
      CREATE TABLE transfers(actual_id TEXT PRIMARY KEY, meal TEXT REFERENCES meals(id),
        sender TEXT NOT NULL, recipient TEXT NOT NULL, amount_sen INTEGER NOT NULL
        CHECK(amount_sen>0 AND amount_sen<=1000000000), CHECK(sender<>recipient)) STRICT;
      INSERT INTO meals VALUES('meal',1001,0,NULL);
      INSERT INTO items VALUES('dish','meal',2,1001,0);
    ''')
    db.close()


def snapshot(db):
    return {table: [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY 1,2')]
            for table in ('meals', 'items', 'claims', 'commands', 'transfers')}


def apply(db, actor, command_id, body, failpoint=None):
    """Synthetic trusted actors: this does NOT implement invitation authorization."""
    encoded = body_text(body)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        previous = db.execute('SELECT body,digest,result FROM commands WHERE actor=? AND meal=? AND command_id=?',
                              (actor, 'meal', command_id)).fetchone()
        if previous:
            if previous['body'] != encoded or previous['digest'] != digest:
                raise Conflict('command identity reused for changed body')
            db.execute('COMMIT')
            return previous['result']
        meal = db.execute('SELECT * FROM meals WHERE id=?', ('meal',)).fetchone()
        kind = body['kind']
        if kind in ('claim', 'finalize'):
            integer(body['expected_revision'], 'expected_revision')
            if body['expected_revision'] != meal['revision']:
                raise Conflict('stale meal revision')
            revision = meal['revision'] + 1
        if kind == 'claim':
            units = integer(body['units'], 'units', maximum=1000)
            item = db.execute('SELECT * FROM items WHERE id=?', ('dish',)).fetchone()
            integer(body['expected_item_revision'], 'expected_item_revision')
            if body['expected_item_revision'] != item['revision']:
                raise Conflict('stale item revision')
            db.execute('DELETE FROM claims WHERE item=? AND person=?', ('dish', actor))
            if units:
                db.execute('INSERT INTO claims VALUES(?,?,?)', ('dish', actor, units))
            used = db.execute('SELECT COALESCE(SUM(units),0) FROM claims WHERE item=?', ('dish',)).fetchone()[0]
            if used > item['quantity']:
                raise Conflict('item capacity exceeded')
            db.execute('UPDATE items SET revision=revision+1 WHERE id=?', ('dish',))
            db.execute('UPDATE meals SET revision=?,finalized_revision=NULL WHERE id=?', (revision, 'meal'))
            result = {'status': 'accepted', 'revision': revision,
                      'item_revision': item['revision'] + 1, 'person': actor, 'units': units}
        elif kind == 'finalize':
            totals = {}
            items = db.execute('SELECT * FROM items WHERE meal=? ORDER BY id', ('meal',)).fetchall()
            if sum(item['line_sen'] for item in items) != meal['total_sen']:
                raise Conflict('receipt component mismatch')
            for item in items:
                claims = db.execute('SELECT person,units FROM claims WHERE item=? ORDER BY person', (item['id'],)).fetchall()
                if sum(claim['units'] for claim in claims) != item['quantity']:
                    raise Conflict('unassigned quantity')
                floors = {claim['person']: item['line_sen'] * claim['units'] // item['quantity'] for claim in claims}
                order = sorted(claims, key=lambda claim: (-(item['line_sen'] * claim['units'] % item['quantity']), claim['person']))
                remainder = item['line_sen'] - sum(floors.values())
                for claim in order[:remainder]:
                    floors[claim['person']] += 1
                for person, amount in floors.items():
                    totals[person] = totals.get(person, 0) + amount
            if sum(totals.values()) != meal['total_sen']:
                raise Conflict('allocation conservation failed')
            db.execute('UPDATE meals SET revision=?,finalized_revision=? WHERE id=?', (revision, revision, 'meal'))
            result = {'status': 'finalized', 'revision': revision, 'total_sen': meal['total_sen'], 'person_sen': totals}
        elif kind == 'record_already_confirmed_transfer':
            amount = integer(body['amount_sen'], 'amount_sen', minimum=1)
            facts = (body['actual_id'], 'meal', body['sender'], body['recipient'], amount)
            previous_transfer = db.execute('SELECT * FROM transfers WHERE actual_id=?', (body['actual_id'],)).fetchone()
            if previous_transfer and tuple(previous_transfer) != facts:
                raise Conflict('actual transfer identity changed facts')
            if not previous_transfer:
                db.execute('INSERT INTO transfers VALUES(?,?,?,?,?)', facts)
            result = {'status': 'recorded', 'actual_id': body['actual_id'], 'amount_sen': amount}
        else:
            raise ValueError('unknown synthetic command')
        if failpoint == 'after_state':
            raise RuntimeError('injected exception after state mutation')
        serialized = body_text(result)
        db.execute('INSERT INTO commands VALUES(?,?,?,?,?,?)', (actor, 'meal', command_id, encoded, digest, serialized))
        if failpoint == 'after_result':
            raise RuntimeError('injected exception after command result insert')
        db.execute('COMMIT')
        return serialized
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise


def expect_error(fn, error, message=None):
    try:
        fn()
    except error as exc:
        if message:
            assert message in str(exc), (message, str(exc))
        return
    raise AssertionError(f'expected {error.__name__}')


def main():
    path = ROOT / f'DISPOSABLE-transactions-{uuid.uuid4().hex}.sqlite'
    create(path)
    db = connect(path)
    checks = []

    def passed(name):
        checks.append({'case': name, 'passed': True})

    contender = connect(path, timeout=0)
    db.execute('BEGIN IMMEDIATE')
    expect_error(lambda: contender.execute('BEGIN IMMEDIATE'), sqlite3.OperationalError, 'locked')
    db.execute('ROLLBACK')
    contender.execute('BEGIN IMMEDIATE')
    contender.execute('ROLLBACK')
    contender.close()
    passed('real_second_connection_blocked_by_immediate_writer_then_recovers')

    before = snapshot(db)
    expect_error(lambda: apply(db, 'organizer', 'empty-finalize', {'kind':'finalize','expected_revision':0}), Conflict, 'unassigned')
    assert snapshot(db) == before
    passed('underassigned_finalization_rolls_back_without_result')

    start = threading.Barrier(2)
    body = {'kind':'claim','expected_revision':0,'expected_item_revision':0,'units':1}

    def race(person):
        connection = connect(path)
        start.wait(timeout=5)
        try:
            return person, 'accepted', apply(connection, person, f'initial-{person}', body)
        except Conflict as exc:
            return person, 'conflict', str(exc)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(race, ('A', 'B')))
    assert sorted(outcome[1] for outcome in outcomes) == ['accepted', 'conflict']
    winner = next(outcome for outcome in outcomes if outcome[1] == 'accepted')
    loser = next(outcome for outcome in outcomes if outcome[1] == 'conflict')
    assert db.execute('SELECT COUNT(*) FROM claims').fetchone()[0] == 1
    assert db.execute('SELECT revision FROM meals').fetchone()[0] == 1
    passed('two_real_connections_same_revision_exactly_one_accepts_no_lost_claim')

    retry = {**body, 'expected_revision':1,'expected_item_revision':1}
    apply(db, loser[0], 'retry-after-conflict', retry)
    assert db.execute('SELECT SUM(units) FROM claims').fetchone()[0] == 2
    passed('explicit_retry_current_revision_preserves_both_diners')

    assert apply(db, winner[0], f'initial-{winner[0]}', body) == winner[2]
    assert db.execute('SELECT revision FROM meals').fetchone()[0] == 2
    passed('exact_old_command_result_replayed_after_newer_revision_without_reapply')
    expect_error(lambda: apply(db,winner[0],f'initial-{winner[0]}',{**body,'units':0}), Conflict, 'changed body')
    passed('same_command_id_altered_body_rejected')

    for point in ('after_state', 'after_result'):
        before = snapshot(db)
        expect_error(lambda: apply(db,'A',f'fault-{point}',{**body,'expected_revision':2,'expected_item_revision':2,'units':0},point),RuntimeError,'injected')
        assert snapshot(db) == before
        assert not db.in_transaction
        passed(f'{point}_exception_rolls_back_state_and_command_result')

    before = snapshot(db)
    expect_error(lambda:apply(db,'A','capacity',{**body,'expected_revision':2,'expected_item_revision':2,'units':2}),Conflict,'capacity')
    assert snapshot(db) == before
    passed('capacity_error_restores_deleted_previous_claim')

    db.execute('UPDATE meals SET total_sen=1002 WHERE id=?', ('meal',))
    before = snapshot(db)
    expect_error(lambda:apply(db,'organizer','mismatch-finalize',{'kind':'finalize','expected_revision':2}),Conflict,'component mismatch')
    assert snapshot(db) == before
    db.execute('UPDATE meals SET total_sen=1001 WHERE id=?', ('meal',))
    passed('receipt_total_mismatch_prevents_finalization_without_committed_result')

    finalized = apply(db,'organizer','finalize',{'kind':'finalize','expected_revision':2})
    result = json.loads(finalized)
    assert result['person_sen'] == {'A':501,'B':500}
    assert sum(result['person_sen'].values()) == result['total_sen'] == 1001
    passed('atomic_finalize_conserves_odd_sen_with_deterministic_residue')

    db.close()
    restarted = subprocess.run([sys.executable, '-c',
        "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute(\"SELECT result FROM commands WHERE actor='organizer' AND command_id='finalize'\").fetchone()[0]); db.close()",
        str(path)], check=True, capture_output=True, text=True, timeout=10)
    assert restarted.stdout.strip() == finalized
    passed('separate_python_process_reads_exact_durable_committed_result')
    db = connect(path)
    assert apply(db,'organizer','finalize',{'kind':'finalize','expected_revision':2}) == finalized
    assert db.execute('SELECT finalized_revision FROM meals').fetchone()[0] == 3
    passed('close_reopen_reconnect_replays_exact_committed_result')

    for invalid in (True, 1.5):
        before = snapshot(db)
        expect_error(lambda:apply(db,'A','bad-money',{'kind':'record_already_confirmed_transfer','actual_id':'bad','sender':'A','recipient':'B','amount_sen':invalid}),ValueError,'integer')
        assert snapshot(db) == before
    passed('boolean_and_fractional_money_rejected_before_financial_write')
    expect_error(lambda: db.execute('UPDATE meals SET total_sen=1001.5'),sqlite3.IntegrityError)
    passed('strict_sql_integer_column_rejects_fractional_money')

    transfer = {'kind':'record_already_confirmed_transfer','actual_id':'actual-001','sender':'B','recipient':'A','amount_sen':200,'suggestion_batch':'batch-old'}
    apply(db,'synthetic-confirmed-import','transfer-first',transfer)
    apply(db,'synthetic-confirmed-import','transfer-new-batch',{**transfer,'suggestion_batch':'batch-new'})
    assert db.execute('SELECT COUNT(*),SUM(amount_sen) FROM transfers').fetchone()[:] == (1,200)
    passed('same_actual_transfer_across_suggestion_batches_counted_once')
    expect_error(lambda:apply(db,'synthetic-confirmed-import','transfer-mutated',{**transfer,'amount_sen':201}),Conflict,'changed facts')
    passed('same_actual_transfer_id_changed_facts_rejected')
    expect_error(lambda:db.execute("UPDATE commands SET result='{}'"),sqlite3.IntegrityError,'immutable')
    expect_error(lambda:db.execute('DELETE FROM commands'),sqlite3.IntegrityError,'immutable')
    passed('accepted_command_results_cannot_update_or_delete_via_schema')

    apply(db,'A','post-final-edit',{**body,'expected_revision':3,'expected_item_revision':2,'units':1})
    assert db.execute('SELECT finalized_revision FROM meals').fetchone()[0] is None
    assert db.execute('SELECT COUNT(*) FROM transfers').fetchone()[0] == 1
    passed('later_accepted_edit_invalidates_finalize_without_erasing_actual_transfer')

    integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    assert integrity == 'ok'
    passed('database_integrity_check')
    final_snapshot = snapshot(db)
    config = {'journal_mode':db.execute('PRAGMA journal_mode').fetchone()[0],
              'synchronous':db.execute('PRAGMA synchronous').fetchone()[0],
              'foreign_keys':db.execute('PRAGMA foreign_keys').fetchone()[0]}
    db.close()
    evidence = {'scope':'DISPOSABLE real-file SQLite; synthetic actors and data; no HTTP',
                'python':sys.version.split()[0], 'sqlite':sqlite3.sqlite_version,
                'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'database':path.name, 'configuration':config, 'passed':len(checks), 'failed':0,
                'checks':checks, 'concurrent_outcomes':outcomes,
                'finalized_result':result, 'final_snapshot':final_snapshot,
                'limitations':['No OS/process kill or power-loss test','No browser, network, auth, invitation or account flow',
                  'One host, one SQLite file, two threaded independent connections; no multiprocess load test',
                  'Whole-meal revisions are deliberately conservative; no independent-item concurrency proof',
                  'One positive integer-quantity item only; full charges, rationals, refunds and settlement consent not modeled',
                  'Rejected command outcomes are not persisted; accepted outcomes only are replayed',
                  'Synthetic already-confirmed transfer facts do not select who may confirm real transfers']}
    (ROOT/'results.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps({key:evidence[key] for key in ('database','passed','failed','configuration')}))


if __name__ == '__main__':
    main()
