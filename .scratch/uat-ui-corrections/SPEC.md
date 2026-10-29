# Bounded UAT UI corrections

Authorized by the owner on 29 October 2026, based on the independent computer-use report at `.scratch/independent-uat-20261029/REPORT.md`. Baseline: `76187b1fcb5e928e8f6cc78b3afc1c02477501ef`.

1. Receipt & Charges must use the existing rational formatter. Real receipt review DOM must show quantities 1, 2, 3, 1/2 and 1/3 correctly. Authoritative rational quantities and integer financial amounts remain unchanged.
2. Quick-assignment pills must convey unavailable whole-portion assignment before activation at full capacity. Keep a discoverable Details / Split path for reallocation. Preserve existing claims, organizer authorization and revision conflicts.

Implementation choice: native disabled buttons with subdued styling, an associated visible explanation, and the existing enabled Details / Split control. The same whole-portion availability rule applies when less than one portion remains; exact fractions remain available in Details / Split.

Risk: MEDIUM for the combined bounded UI correction (quantity Medium; affordance Low). No backend, financial engine, persistence, authorization, conflict handler, finalization, native confirmation behavior, or Concept C redesign changes.

Acceptance gates: reproduce both defects with failing real-browser assertions; pass focused DOM/capacity/reallocation/reload checks at desktop and mobile sizes; full Python and browser suites; independent standards and spec reviews of actual final source; successful hosted PR CI associated with the final reviewed head; premerge diff/base recheck and merge commit integration verified remotely.

Tests use a new temporary database and isolated Chrome profiles on loopback port 18879. Refuse occupied app/debugging ports; only terminate processes spawned by this harness. Do not inspect, change or delete the unknown UAT database/listener or unrelated resources.

The original independent UAT remains incomplete. This engineering regression run cannot close its finalization, export, collaboration, mobile or other untested scenarios. A separate independent retest is required; no production release or hosting is authorized.
