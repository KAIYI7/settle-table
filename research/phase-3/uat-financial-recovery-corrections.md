# Focused UAT financial and recovery corrections

31 October 2026. Baseline `73806f67338461ed169a47f4e639c02d71e56e56`; prior evidence: `.scratch/uat-gap-closure-20261029/REPORT.md`. This is a corrective milestone, not local MVP acceptance or deployment approval.

## Policy and implementation

The product owner confirmed existing draft adjustment scopes stay fixed unless an organizer explicitly changes them, and correction must be blocked if a fixed scope loses its last item. Historical finalized data is unchanged. New OCR service charges disclose the bill-wide assumption and allow a selected scope; accepted service charges can be explicitly changed in either direction. Bill-wide eligibility expands with receipt items, while the printed amount remains unchanged. The authoritative receipt records scope intent without adding fields to legacy canonical receipt/command data; the accepted calculator remains unchanged. Financial changes invalidate review.

The allocation sheet moves and contains keyboard focus and restores its trigger. Allocation conflicts report synchronization only after an accepted current snapshot, preserve drafts, and offer manual recovery when refresh fails. A stale edited service scope is visibly flagged. No mutation is automatically retried.

## Financial evidence

The original UAT totals (Bob, Chandra, Devi, Elaine, Farid, Alice) were 1303, 1302, 1215, 312, 312, 1604 sen. The original-amount synthetic browser fixture with corrected service scope yields 1332, 1330, 1332, 342, 342, 1370 sen, still totaling 6048. Its stable item IDs were reproduced to retain deterministic tie-breaking. The original rounding scope covered two items; the new fixture covers all four, and both allocate the one-sen rounding to Alice. Mock Notion blocks match the finalized balances and receipt amounts. The post-accept addition fixture also uses stable IDs; a separate staged fixed-scope case and the main and Concept C browser tests exercise actual generated IDs.

## Review and verification

- Independent financial security/source review: PASS after fixing historical replay, explicit scope correction, malformed inputs, omitted scope widening and self-claim command length. Organizer authorization and cross-actor replay denial exercised.
- Independent conflict/focus review: PASS after resolving superseded-refresh feedback, pristine versus edited scope state, and test-server ownership and cleanup issues. Duplicated test CDP setup is a nonblocking maintainability concern.
- Independent specification review: PASS after the focused same-millisecond self-claim regression and resolution of earlier accuracy and draft-preservation findings. The two identities act sequentially at current item revisions; the test covers command-ID uniqueness, not simultaneous writes.
- Local full Python suite: 216 tests passed. Full Chrome journey: 12 stages passed. Separate financial browser/export, competing-identities conflict/recovery and Concept C tests passed; the latter covers ten scenarios including diner self-claim on a generated item ID. Tests use disposable SQLite and loopback servers, mock OCR and mock Notion.
- Hosted exact-head CI [run 41276975790](https://github.com/KAIYI7/settle-table/actions/runs/41276975790) passed all Python and browser steps on `0cfb96119fc17cb21f0d77b76c0362b1fe8acfcb`. [PR #24](https://github.com/KAIYI7/settle-table/pull/24) merged as `7aaf2b32a72462d956f93e8f54adfd627a7ff86e`, verified on remote `main`.
- Physical mobile, screen-reader, and independent manual UAT remain unverified.
