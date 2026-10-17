# First financial calculation slice

2026-10-16. Orchestrator-authorized seams: `calculate(immutable supplied meal facts)` → immutable deterministic result / structured rejection, and exact decimal-money text parser. No identity, human-review assertion, current persisted revision, funding, settlement, HTTP, UI, persistence, OCR or Notion behavior is implied. Source is independently implemented from the accepted [MVP specification](../phase-2/mvp-specification.md), not copied from a disposable runner or reference repository.

TDD/codebase-design skills read; glossary and domain-doc convention read. The orchestrator explicitly confirmed these seams under delegated authority, so no additional seam-permission prompt is required. Tests exercise public interfaces with independently worked literals. No glossary/ADR changes are necessary for this reversible module.

## Incremental execution evidence

1. **RED observed:** first quantity-allocation test, `python -m unittest discover -s tests -v`, failed with `ModuleNotFoundError: No module named 'tabwise'` (one test/error). The test expects the specified 1001-sen line at quantity 1:2 to yield A334/B667, without multiplying the line total again.

2. **GREEN observed:** minimal immutable facts/results and exact apportionment passed the first quantity test (1/1).
3. **RED observed:** quantity shares 1+1 against explicit quantity3 were incorrectly accepted (`ValueError not raised`, 1 failure/2 tests). Added a structured `CalculationError(code, path)` quantity conservation rejection; **GREEN observed:** 2/2 passed.

4. **RED observed:** boolean money was accepted (1 failure/3 tests); strict integer money checks made 3/3 green. A focused malformed identity/collection/quantity-bound test then exposed 6 failures/3 errors; bounded tuple/ID/exact-rational validation made 4/4 green.
5. **RED observed:** split modes were treated interchangeably and malformed assignments accepted (9 failures/3 errors across the focused mode contract test). Added distinct equal/weights/percent/exact/quantity conservation/type checks and zero-base handling; **GREEN observed:** 5/5 test methods passed, including the earlier quantity cases.

6. **RED observed:** the 3001−101+174+290+1 receipt example failed because adjustment facts did not exist. Added explicit scoped-or-split signed adjustments using immutable original rounded item bases; **GREEN observed:** 6/6 passed, including literal A1683/B1682 and component/input-order checks.
7. **RED observed:** receipt/subtotal mismatches, aggregate overflow and negative consumption were accepted (4 failures/8 methods). Added hard reconciliation/final-consumption gates; **GREEN observed:** 8/8 passed. The full 1-sen discount case and included-tax gross600 case passed without further changes.

8. **RED observed:** decimal parser test failed with absent `parse_money`; implemented bounded ASCII decimal parsing without floats. **GREEN observed:** 9/9 methods passed, including 5 accepted literals and malformed/sign/locale/precision/bound rejections.
9. Added targeted independent literal/check cases after the relevant behavior already existed: malformed adjustment scopes/signs/discount limits; stable digest residual/negative-sign symmetry; 25→26 paradox; zero-value item and explicit zero-base override; exact fractional quantities; immutable facts/results; all registry order variants and malformed typed fact shapes. No additional production behavior was needed. **GREEN observed:** 15/15 methods passed (subcases are not misreported as independent test methods).

## Implemented scope and limitations

Public [interface](../../docs/calculation-interface.md): immutable exact supplied financial facts, reconciled item/component allocation and final consumption, structured rejections, exact decimal-money parser. The implementation is independently written standard-library Python. No production reference-project source reuse or dependency installation occurred. No global/settings changes, framework, packaging scaffold, UI, web server, database, payer/settlement function, OCR or Notion implementation was created.

The result proves mathematical validity of supplied facts only. It does not establish reviewer identity/verification, accepted current revisions, authorization, durable atomic finalization, secure invitations, settlement policy, device behavior or release readiness. Required label/rationale limits and untrusted JSON validation belong to the later authority/transport adapter. Negative final consumption, refund/credit/sponsorship and compound/rate-derived promotion semantics reject or are unavailable under the accepted first-slice contract.

No glossary/ADR change was needed: existing terms suffice and the module's technical interface is documented without putting implementation details in the glossary. Independent review is pending; only the orchestrator may evaluate slice/phase completion.

## Reproduction and fixed review snapshot

From project root: `python -m unittest discover -s tests -v`. Final pre-review run: **Python3.14.6, 15 methods passed, 0 failures/errors**; measured unittest duration0.0183s including discovery/import overhead in the verification harness. [Machine record](calculation-verification.json) captures exact source hashes and output. The same15 methods also passed with the existing bundled **Python3.12.14** runtime (0.006s unittest report), checking compatibility with the measured OCR runtime without importing it or requiring its dependencies. These are tiny local functional tests, not a performance or concurrency benchmark.
