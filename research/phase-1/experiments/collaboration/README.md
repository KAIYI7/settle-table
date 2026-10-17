# Disposable collaboration/domain experiment

Run `python research/phase-1/experiments/collaboration/simulate.py`. Standard library only; no network, database, invitation link, production authentication, framework or UI. Results are 17 checks, including a real two-thread race, overclaim and stale revision rejection, exact duplicate replay, role restrictions and explicit amendment/review states.

The user selected private internet invitations, organizer control of financial amounts/finalization and diner control of their own assignments. The script tests consequences using hard-coded fictional actors and an in-process lock. It does **not** validate a deployed multi-user transport, access security, reconnect latency or durable persistence. Last-writer-wins loses a diner claim; a serial authority with explicit revisions is one viable model, not a final production architecture.

All amounts are integer sen. The full state is in `results.json` where relevant. No proposed transfer is recorded as actual money moved. This experiment complements the arithmetic runner and preserves separate domain, receipt, funding, settlement and sync concepts.
