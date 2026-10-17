# Repository foundation evidence

2026-10-17. **Orchestrator acceptance: PASS for separate CI and namespace foundation changes.** No new product capability. Current objectives: [project status](../../PROJECT_STATUS.md); authority checkpoint: annotated `authority-v1-accepted` at merge `af7ba147642b8b8e9a5aee973a95c59d46c38b9a`.

| Workstream | Decision / evidence |
|---|---|
| Minimal full-suite CI | [PR #2](https://github.com/KAIYI7/settle-table/pull/2), merge `a4dd5302f93b41bbf72cbf29ecd596bc7bb7c1aa`; [research/cost gate](ci.md), [independent review](ci-review.md), [active workflow](../../.github/workflows/python-tests.yml). Single Ubuntu24.04/Python3.14 job, full discovery, immutable official actions, read-only contents, no supplied secret/upload/cache or test filtering. |
| Account authority | Owner confirms included minutes remain and no valid payment method is attached. Official documented quota blocking applies. Browser was signed out and connector has no billing read: this is owner-supplied evidence, not a fabricated account measurement. No billing/payment settings changed. Exhaustion fails; do not buy usage or skip tests. |
| Naming and compatibility | [Assessment](package-naming.md), [implementation/evidence](package-refactor.md), [coordinator actual-source review](package-refactor-review.md), [safe compatibility result](package-compatibility.json), [experimental script](experiments/namespace_compatibility.py). [PR #3](https://github.com/KAIYI7/settle-table/pull/3), merge `91b824f395d062a994056e905f475fe83f52b3a8`. Source files unchanged bytes; only import paths/callers/current docs change. |
| Next plan | [Independent challenge](../phase-3/transport-identity-challenge.md), [orchestrator plan](../phase-3/next-slice-plan.md): integrated invitation/session lifecycle, then same-origin transport. No OCR/Notion/UI implementation. |

## Observed hosted runs

- [CI PR run39042759050](https://github.com/KAIYI7/settle-table/actions/runs/39042759050), head `556ce39eb9d293db7f35abc2299acbfe66bae8f1`: completed **success**; all60 tests28.299s, Python3.14.8 on Linux. Actual job logs inspected for the test summary; runtime variation from local3.14.6 is explicit.
- [Main CI run39042884843](https://github.com/KAIYI7/settle-table/actions/runs/39042884843), commit `a4dd5302f93b41bbf72cbf29ecd596bc7bb7c1aa`: completed **success**, push trigger.
- [Namespace PR run39042972976](https://github.com/KAIYI7/settle-table/actions/runs/39042972976), head `a50fa4585e91b8b8eadcf51177f545366b90f7d0`: completed **success**, logs show all60 tests30.151s.
- [Renamed main run39043128511](https://github.com/KAIYI7/settle-table/actions/runs/39043128511), commit `91b824f395d062a994056e905f475fe83f52b3a8`: completed **success**, push trigger after the namespace merge.

These are point-in-time functional results, not statistical coverage, throughput or a promise that future runs cannot exhaust shared quota. Every main push triggers full discovery; cancelled/timed-out runs are not passing evidence. A green workflow is not branch protection; no protection/account policy was changed.

## Preserved constraints and limitations

`settletable/calculation.py` SHA256 remains `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`; `settletable/authority.py` remains `1eef9e7959639de5407bc445e9344f3ef7e0bb9502bafcfb2026d2c794ed81f0`. `tabwise-apportion-v1` and all four authority/security/canonical domains stay unchanged. Existing SQLite schema/history/session/review/calculation/replay survive the package move. Historical metadata keys and failed-run narratives remain historical; source links pin the accepted commit.

The intended subagent final rename review/session was interrupted; the orchestrator explicitly completed exact-byte/caller comparisons, source/script review, independent compatibility execution and a fresh60-test run. No interrupted result is manufactured as a PASS. The naming import change intentionally does not promise support for undeclared outside callers or Python pickle paths. No production migration, account recovery, public exposure or external private data operation occurred.
