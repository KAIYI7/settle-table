# Feature Spec: Post-Finalization UX & Diner Access Improvements

## Background
Based on real-user feedback and the accepted investigation ("Real-User Feedback Investigation: Diner Permissions & Post-Finalization UX"), this feature addresses three bounded post-finalization areas in SettleTable:
1. Notion export reliability and diner visibility.
2. Diner funding and settlement UX clarity without degrading organizer-attested financial ledger integrity.
3. Organizer-controlled original receipt photo sharing with authenticated meal participants post-finalization.

## Scope 1 — Notion Export Reliability (High Priority)
- Export status and report URL persist across UI re-renders, snapshot polling, and browser refreshes.
- Support synchronous, already-exported, and asynchronous export responses.
- Resumes observation of in-progress exports after session restoration.
- Consistent timeout semantics: backend marks in-progress exports as timeout after 75.0s; frontend polls up to 70s.
- Prominent "Open Report in Notion ↗" action after successful export.
- Collapse bulky export form into `<details>` when already exported.
- For diners: show an indicator when organizer archived meal to Notion. Never expose integration tokens, credentials, or private workspace URLs to diners.
- Organizer can register a view-only published Notion link (`https://*.notion.site/*` or `https://*.notion.so/*`), validating HTTPS scheme, host, and <= 512 characters. Clearable with empty string.

## Scope 2 — Diner Funding & Settlement UX (Medium Priority)
- Authoritative financial ledger: organizer-attested ledger strictly preserved. Diners cannot execute `RecordContribution`, `ReverseContribution`, `RecordTransfer`, or `ReverseTransfer`.
- Display personalized outstanding balance for the authenticated diner (debt, credit, settled, or unfunded obligation).
- Reuse existing suggested transfers without inventing synthetic debtors/creditors.
- Add concise role notices explaining organizer counter-payment attestation.

## Scope 3 — Organizer-Controlled Receipt Photo Sharing (Medium Risk)
- Sharing disabled by default (`share_with_diners = 0`), including for existing finalized meals.
- Organizer can explicitly toggle sharing post-finalization with a privacy warning about physical receipts.
- Only active authenticated meal participants can access `GET /api/meals/{meal_id}/receipt/photo` when enabled.
- Diners cannot access photo before finalization.
- Diners never gain upload, replacement, or deletion permissions.
- Unauthenticated, inactive, revoked, and cross-meal sessions remain unauthorized.
- Existing photo integrity verification and `Cache-Control: private, no-store` headers intact.
- Storage in `receipt_photos.share_with_diners` guarantees zero change to `meals.state`, financial calculations, or revision numbers.
