# SettleTable baseline publication

Prepared2026-10-17, Asia/Kuala_Lumpur. Repository: [KAIYI7/settle-table](https://github.com/KAIYI7/settle-table). This work establishes a clean accepted checkpoint before the next implementation slice. The local filesystem directory is unchanged. The calculator's accepted source/tests and versioned rounding identity are unchanged; `tabwise` remains its technical Python namespace.

**Verified checkpoint:** baseline `69895457d9e3524c90df24f3a21c284ea70cef6c`, annotated `phase2-accepted`. Actual remote `main` and peeled tag target matched before any next-slice work resumed; [verification record](checkpoint.json). Subsequent status/documentation commits may advance `main` without moving the checkpoint.

## Included versus local-only

Include project guidance/specifications/research, independently written code/tests/prototypes, sanitized Notion connector observations, aggregate OCR metrics, corpus identity/hash manifest, dependency locks and original verification hashes. Matt's complete published27-skill manifest is retained with its MIT license and invocation metadata. No project-wide open-source license is inferred from dependency/skill licenses.

Preserve locally and ignore: all OCR images (real and synthetic), receipt-level transcriptions/labels/raw engine proposals and the combined local preparation script, model/runtime caches, environments/dependencies, local databases/WAL/SHM, logs, temporary/build output, private prepublication backups and the complete Impeccable installed payload. No questionable-provenance binary fixture or executable belongs in this baseline. The synthetic text-only Notion SVG contains no external image/font and is retained as authored evidence.

See independent [rights review](rights-review.md) and [initial privacy review](privacy-review.md). Their initial FAIL/qualified findings are preserved; closure depends on the actual sanitized staged tree, not merely an ignore rule.

## Sanitization and historical integrity

Published private Notion IDs use consistent `synthetic-notion-id-NNN` aliases; private destination URLs use nonresolving `example.invalid` links. These traces preserve schema, relations, money/status/error observations but cannot connect to the original account. Private originals and the alias map remain only in positively ignored `.local/prepublish/`. External Notion content was not changed. Public reproduction needs a fresh authorized destination; account cleanup uses the owner's private records.

Installation destinations are project-relative. Reproduction commands use a reader-provided Python/Node/Playwright environment, with measured versions recorded separately. Host-specific cache paths are not prerequisites. Historical labels may retain the former project name inside measured evidence.

Sanitization changes document/trace/installation-manifest bytes. Original recorded hashes remain historical observations, not claims that sanitized files have identical bytes or that benchmarks were rerun. The publication audit records current staged hashes separately. The accepted calculator/test hashes remain exact. Missing raw receipt assets are an explicit reproducibility limit; source IDs/revisions/hashes are retained without presenting input rights as cleared.

## Skills on another checkout

Matt source is vendored at its pinned revision with license. Impeccable remains installed on the originating workstation but is excluded from Git pending third-party notice/bundle review. Its Apache license, NOTICE, upstream revision/version and engine checksum records are retained. This is a distribution decision, not removal of the user's installation or a claim that upstream is proprietary.

To restore Impeccable on a new machine, obtain the official [pbakaus/impeccable](https://github.com/pbakaus/impeccable) source at `5bf0a069dc857e1b5f4b090e004d9d5b231416ca`, review its license/NOTICE and current official installation instructions, and place the provider-neutral `.agents/skills/impeccable` collection under this project's `.agents/skills/impeccable`. Preserve any existing destination rather than overwriting it. Provision the platform engine through its official launcher; compare the recorded engine/release checksum before execution. See [installation provenance](../agent-skills.md) and [manifest](../skill-installation-manifest.json). No globals or provider hooks need to change for repository establishment.

## Acceptance procedure

Audit all staged/untracked/ignored paths, scan staged content without logging secret values, validate JSON and exact accepted calculator/test hashes, review the complete staged diff, then commit on `main`. Push only to the supplied origin without force. Create annotated `phase2-accepted` pointing to that baseline; verify both remote branch SHA and the tag's peeled target. Only after verification record the baseline SHA in project status and resume the next objective. This user-authorized repository publication is distinct from application deployment.
