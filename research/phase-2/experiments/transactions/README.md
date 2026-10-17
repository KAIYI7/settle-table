# Disposable SQLite transaction probe

Run from the project root:

```powershell
python research/phase-2/experiments/transactions/probe.py
```

Python standard library only. Creates a new uniquely named `DISPOSABLE-transactions-<id>.sqlite` in this directory for each run and updates `results.json`. It never resets or deletes a prior database. All records are fictional. No HTTP, account, credential, hosted inference or production module is used.

The probe uses actual `BEGIN IMMEDIATE`, WAL and `synchronous=FULL`, two independently opened connections on concurrent threads, a deliberately held write transaction, injected Python exceptions, close/reopen and a fresh Python subprocess reading committed results. Results contain the exact source hash, SQLite/Python versions, configuration, accepted/conflicting outcomes, finalized amounts and final database snapshot.

It is deliberately one small item/meal: 1001 sen shared between two quantity units. It demonstrates persistence/transaction feasibility rather than the complete domain. Synthetic pre-confirmed transfer inputs avoid choosing a real settlement confirmation policy. It implements no authentication, HTTP transport, invitation, UI, migration, backup or production service.

Scratch SQLite files and sidecars are ignored and retained locally for inspection. Do not reuse this throwaway schema/controller unchanged. The [analysis and limitations](../../transaction-validation.md) specify what the checks establish.
