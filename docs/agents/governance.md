# Project governance

Effective 2026-10-16, by the user's explicit delegation. This replaces earlier requirements for user approval at each numbered phase. Historical research snapshots retain their evidence and original authorization context; they do not govern current phase authority.

## Authority and delegation

The main Codex agent owns project direction within the agreed receipt-splitting objective, phase planning, bounded delegation, review/integration of actual artifacts, architecture and implementation decisions, go/no-go decisions and durable project state. Use parallel and independent agents where they improve quality; give each scope, context, output paths and acceptance criteria. Independently challenge important financial-correctness, architecture and security decisions. Subagents may research, prototype, implement, test or review; they cannot authorize phase transitions. A summary alone is not reviewed evidence.

## Transition procedure

1. Identify current phase exit criteria and the proposed next scope. Gates must be specific to the capability being authorized: extraction accuracy is not the same as manual financial correctness or public-release readiness.
2. Review actual artifacts and reproducible results. Distinguish verified facts, experimental evidence, conclusions, assumptions and unknowns. Preserve counter-evidence; do not manufacture passing evidence or repeat completed research without a reason.
3. Record **PASS**, **CONDITIONAL PASS** or **FAIL** for each material gate, with evidence links, unresolved risks, blocking status and the exact scope a condition permits. Conditional passes need an enforceable restriction or follow-up criterion; they do not waive a failed safety invariant.
4. The orchestrator records the decision in `docs/agents/phase-transitions.md` and updates `PROJECT_STATUS.md`. Proceed directly when sufficient. Otherwise perform targeted closure work, or revise the strategy if evidence contradicts it. Routine phase completion is not a human escalation.
5. Before production implementation, record the bounded MVP specification, chosen reversible architecture, invariants and validation/review criteria. Build small vertical slices. Before broadening a slice, verify its behavior, security boundaries and conformance to the specification. Experiments remain clearly separated from production code.

## Human escalation

Ask the user only when the action genuinely needs their authority or preference:

- Paid services or material recurring expenditure.
- Public/production deployment exposing services or data externally.
- Credentials or account actions requiring the user.
- Destructive changes to existing personal/external data, private-information sharing or irreversible production migrations.
- Unclear/incompatible licensing before source reuse.
- Material changes to the product objective.
- Unresolved product-policy choices with multiple reasonable outcomes that fundamentally depend on user preference.

Complete independent, authorized work while an escalation is pending. Ordinary reversible engineering choices belong to the orchestrator. Prefer a documented technical decision to a routine permission question. Existing explicit authorizations remain effective; never infer private-data or spend consent merely from phase authority. Localhost-only validation is not public deployment.

## Standing product constraints

Several diners collaborate through private internet invitations with meal access checks. Organizer controls receipt amounts/charges and finalization; diners edit their own assignments. All financial amounts use integer minor units; rational quantities/weights remain separate. Human receipt verification remains required. OCR runs on devices or infrastructure controlled by the project; no third-party hosted image/vision calls. Notion reporting is distinct from receipt processing and requires its own data/retention decisions. Read `research/phase-1/requirements.md`, `GLOSSARY.md` and the current specification before domain work.

## Durable state

`PROJECT_STATUS.md` is the current phase/objectives/gates/risks/stack/next-work source of truth. The transition ledger records decisions and evidence; `research/README.md` indexes evidence. Keep each current before ending a major workstream. Historical approval wording in research is not active governance. Skill invocation policies still apply; skill workflows cannot grant authority or transfer transition decisions to subagents.

When an engineering workflow asks for confirmation of an ordinary technical choice (for example a test interface or numbered-phase boundary), the user's explicit delegation authorizes the orchestrator to decide and record it. This does not implicitly invoke an explicit-only skill or replace any human escalation above.
