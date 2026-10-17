# Independent engineering and correctness review

2026-10-16. **No material finding for the first pure-calculation slice.** Advisory review only; the main orchestrator decides acceptance and transitions. This does not assess the later collaborative authority, receipt processing, payment confirmation, UI, external integration or deployment.

## Reviewed baseline and standards

Reviewed actual complete files against [the fixed snapshot](review-baseline.json), [C1–C4](../phase-2/mvp-specification.md), [interface documentation](../../docs/calculation-interface.md), current `AGENTS.md`, governance and glossary. There is no Git diff baseline; this is a full-file review of the new isolated slice, not a claimed commit/branch review. No separate `CODING_STANDARDS.md` or `CONTRIBUTING.md` was found in the inspected project scope. Scope/financial invariants and the documented interface supply the binding standards; code-smell heuristics were considered without manufacturing findings.

| File | SHA-256 at inspection and final recheck |
|---|---|
| `tabwise/calculation.py` | `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a` |
| `tests/test_calculation.py` | `70d6dab36179bc2672712b236eea54d0313c85a2fd5a54480e03aefdbefea80c` |
| `docs/calculation-interface.md` | `e447998ff254f1e9e6267b020a9777a599131eef1c7333b4c2f620134a9c2173` |
| `research/phase-2/mvp-specification.md` | `4de5af56ea05a71ef894ee08accea375655dcae1f7888a45825bf80b43faf711` |

## Standards and engineering assessment

**PASS for this bounded seam; zero actionable findings.**

- [Money/text validation](../../tabwise/calculation.py:16) requires exact `int`, excluding `bool`; parser length and ASCII grammar precede bounded decimal conversion. No float roundtrip, tolerance or hidden balancing line.
- [Collection/identity/rational validation](../../tabwise/calculation.py:34) rejects mutable/subclass collections before iteration, bounds exact tuple counts and string lengths, and validates normalized `int`/`Fraction` precision before use in allocation. IDs remain exact ASCII rather than normalized aliases. Item/adjustment source IDs share a checked namespace.
- [Inputs/results](../../tabwise/calculation.py:85) use frozen slotted dataclasses. Accepted nested facts contain exact tuples and validated immutable leaves; constructed-but-invalid dataclasses are rejected by `calculate`. Unknown constructor fields reject. The documentation correctly distinguishes construction from validation and does not claim to validate arbitrary JSON.
- [Apportionment](../../tabwise/calculation.py:142) uses exact quotas and compact ASCII JSON domain separation for the source/person digest; ordered results and deterministic tie handling do not depend on registry order. Negative components allocate magnitude before negation.
- [Calculation](../../tabwise/calculation.py:192) has no file, network, database, ambient identity, clock or random operation. Its imports and call paths match a pure deterministic seam. No `reviewed=True` flag claims authority.
- Production tests call public `calculate`/`parse_money` with worked literal expectations, malformed cases, conservation and the largest-remainder nonmonotonic counterexample. They do not duplicate the implementation to manufacture expected shares.

## Targeted independent execution

Ran `python research/phase-3/engineering_probes.py`: **11 check groups passed, zero failed**. [Probe source](engineering_probes.py), [results and checked hashes](engineering-probes.json). No production module/test mutation and no full-suite repetition; the orchestrator independently owns the suite rerun.

The groups exercise twenty distinct one-sen item/discount identity pairs; signed adjustment symmetry; zero-base participants among 100 diners; exact documented maxima of 100 participants/500 items/100 adjustments; money/quantity/text boundaries; exact fractional percentages; independently valid overlapping discounts that would create negative consumption; explicit discount limits despite a compensating charge; tuple subclasses whose iteration raises; malformed IDs and rational types/bounds; and frozen nested facts/results with mutable shares rejected. The probes use the public interface and mathematical invariants/literals rather than reproducing apportionment as an oracle.

## Correctness and security boundary

**C1:** scoped components derive original rounded item shares and do not compound earlier adjustments. Tiny full discounts return zero for both diners across the tested identity variants; zero bases receive no residual fee.

**C2:** the implemented digest encoding and final stable-ID order match the specified unambiguous tie contract. Identity validation and shared source namespace precede financial allocation.

**C3:** bounded exact types, tuple registries, rational precision and money/text limits are implemented. Aggregate subtotal/receipt/final consumption checks prevent accepted overflow or negative totals. Boundary probes support the documented limits, but are not a throughput/denial-of-service benchmark.

**C4:** kind/sign matrix, exactly-one scope-or-explicit-split, item-only quantity mode, discount caps and negative final-consumption rejection match the accepted restriction. Included tax remains informational. Unsupported refund, gift, prepaid-voucher and compounding semantics were not silently introduced.

The Python model intentionally accepts already-created `Fraction` objects; it cannot bound work a caller performed before calling the seam. Frozen dataclasses are application immutability, not protection against privileged Python reflection. A future untrusted JSON adapter still needs body/shape/label limits and rational parsing before construction. Those are documented future adapter obligations, not missing functionality in this slice. Passing mathematical calculation does not establish human review, identity, current revision or finalization permission.

**Recommendation:** accept the isolated calculation seam after the orchestrator reviews these artifacts and its independent suite result. Do not infer acceptance of the whole MVP or any future transport/authentication/deployment capability. Standards axis: 0 findings. Correctness/security review of the bounded contract: 0 material findings.
