# Independent UAT follow-up: two focused UI corrections

Date: 29 October 2026 (Asia/Kuala Lumpur). Authorized scope: [bounded specification](../../.scratch/uat-ui-corrections/SPEC.md). Baseline `76187b1fcb5e928e8f6cc78b3afc1c02477501ef`. Risk MEDIUM overall: receipt display Medium, assignment affordance Low.

## Exact changes

- `settletable/static/app.js`, `renderOrganizerSection`: pass receipt quantity to existing `formatRat`. Review displays `(x1)`, `(x2)`, `(x3)`, `(x½)` and `(x⅓)` while preserving the rational arrays and integer sen amounts.
- `renderClaimsSection`: enable whole-portion quick assignment only when at least one portion remains. Native disabled unassigned diner pills have an associated visible explanation and descriptive title. Fully allocated items say “Fully allocated. Use Details / Split to reallocate.” Fractional remaining capacity directs to exact fractions. Existing allocated diner pills and Details / Split remain usable.
- `settletable/static/style.css`: dim disabled available pills and suppress their active hover treatment. No Concept C redesign.
- `tools/e2e_browser_test.mjs`: add one regression stage to the existing hosted browser suite and a `--ui-regressions-only` option. Refuse occupied application/debugging ports, and use unbuffered runner output to expose the new temporary database path. Existing tests remain included.

No changes to backend calculation, receipt quantities/amounts, persistence, organizer authorization, conflict handlers, finalization or native confirmation implementation. No changes to the unknown original UAT database, port 18765 listener or unrelated resources.

## Reproduction and verification

Both symptoms were reproduced before their corrections with:

```text
node tools/e2e_browser_test.mjs --port 18879 --ui-regressions-only
Receipt DOM quantity 1: expected (x1), got (x1,1)
```

After the formatter correction alone, the five quantity checks passed and the next assertion reproduced the second issue:

```text
Full-capacity quick assignment must be disabled before clicking
```

After both corrections:

- Focused Chrome CDP regression PASS. The actual Receipt & Charges DOM is checked for all five quantities before sealing, after sealing and after reload; every line remains RM 6.00 and the serialized authoritative receipt stays identical.
- Quick assignment works with whole capacity, is natively disabled at full/fractional capacity, and has an accessible explanation. Attempted disabled activation preserves the snapshot and does not open the editor. Existing assigned pills and desktop Details open the drawer. Mobile Details opens the existing bottom sheet; clearing an assignment re-enables quick assignment; reassignment persists after reload.
- `python -m unittest discover -s tests -v`: **213 tests PASS**, initial run 49.415s; post-review full rerun 50.797s. Includes allocation authorization and capacity rejection, stale revision conflict/recovery, unchanged diner provenance, concurrency, rollback, and persistence tests.
- Full Chrome suite, with task-local `ARTIFACT_DIR` and port 18879: **12 stages PASS** (11 existing plus the new regression stage). This suite uses mock OCR and mock Notion, and its existing finalization tests replace `window.confirm` in the browser.
- `git diff --check`: PASS. Impeccable detector on the changed production UI files returned `[]` (zero mechanical findings).
- Rendered captures inspected at desktop 1280 × 900 and mobile 375 × 667: [receipt quantities](../../.scratch/uat-ui-corrections/evidence/receipt-quantities.png), [desktop capacity](../../.scratch/uat-ui-corrections/evidence/capacity-desktop.png), [mobile capacity](../../.scratch/uat-ui-corrections/evidence/capacity-mobile.png), [mobile details](../../.scratch/uat-ui-corrections/evidence/capacity-mobile-details.png).

Each harness run used a newly created `settletable-e2e-*` temporary directory with its own `e2e.sqlite` and separate Chrome profiles. Startup printed the absolute database path. Cleanup targeted only its child process handles and its generated temporary directory. The first full browser attempt stopped at the existing Windows screenshot path outside the writable workspace; rerunning with `ARTIFACT_DIR=C:/LKY_Project/TabWise/.scratch/uat-ui-corrections/evidence` passed without changing that unrelated path behavior.

## Independent review and integration

- [Standards/source review](uat-ui-corrections-standards-review.md): PASS, zero documented violations or actionable baseline smells.
- [Specification review](uat-ui-corrections-spec-review.md): PASS, zero findings. The independent reviewer also reran the focused Chrome regression successfully (3.23s) and inspected receipt/mobile captures.
- Reviewed production/test source commit: `3b24faa4bdd5a705854b4c31b2fa58d36597e69e`. Subsequent evidence-only commits preserve these source bytes.
- Final [PR #23](https://github.com/KAIYI7/settle-table/pull/23) head `e00f914c49e04c72e13a57c58fc0cb70463a9cc7` preserves independently reviewed production/test bytes. [Hosted CI run 40820110948](https://github.com/KAIYI7/settle-table/actions/runs/40820110948), check/job `123270342737`, completed successfully with that exact check head SHA. Untruncated logs confirm 213 Python tests (30.375s) and all 12 browser stages pass.
- Orchestrator rechecked the actual hosted PR diff, source-byte equivalence, remote head and unchanged remote base `76187b1fcb5e928e8f6cc78b3afc1c02477501ef`; all integration gates PASS.
- **MERGED:** `449dc8c2322c7b64a429e28db8290da38f141975`, verified on remote main. Its two parents are exactly premerge main and final PR head. Merge tree `53f9483d653160805ca9792d5d3121d2b2c62356` equals the reviewed PR-head tree. [Acceptance gates](../../docs/agents/phase-transitions.md).

## Original independent UAT remains incomplete

The 29 October report is retained unchanged at `.scratch/independent-uat-20261029/REPORT.md`. These engineering regressions do **not** mark its incomplete scenarios passed. Finalization/native-dialog outcome, final displayed cent conservation, mock export in that UAT journey, isolated invitation/self-claim journeys, genuine stale-state interaction, room-level mobile/keyboard/accessibility and other untested negative scenarios still require a **separate independent retest in a confirmed isolated environment**. No public-release gate is cleared here.
