# Prepublication privacy and portability review

2026-10-17, Asia/Kuala_Lumpur. Independent advisory review for the orchestrator's clean GitHub baseline. **Initial disposition: FAIL for publication of the unchanged snapshot.** Disposable private Notion identifiers/links remain in research artifacts. This does not identify a leaked credential, and it does not authorize a push. The orchestrator performs sanitization and verifies the final staged tree/remote branch/tag.

## Scope and method

Read-only local inspection of 112 first-party text files across root documents, `research/`, `docs/`, scripts, JSON and tests. Also separately examined six generated receipt-source JSON files under the ignored image directory. Used category/count/line-only pattern reports; no matched credential, private identifier or private URL is reproduced here. No `.env` contents, account, Notion API or external service was accessed. The only file written by this workstream is this report.

Content inspection excluded `.git`, `.agents`, virtual environments, dependency/model caches, `node_modules`, vendor/upstream/download directories, bytecode and receipt-image binaries. Binary scratch databases were inventoried rather than opened. This is a heuristic privacy review, not proof that arbitrary secrets cannot exist. Installed third-party skills require their separate provenance/license audit.

## Findings in the initial snapshot

Line references/counts below precede the orchestrator's sanitization and may move afterward. URL/reference/UUID categories overlap; do not sum them as distinct records. No original identifier or replacement mapping is public evidence.

| File | Category and count | Initial lines |
|---|---|---|
| `research/phase-1/experiments/notion/connector-evidence.json` | 25 private Notion URLs; 156 collection/formula references; 194 UUID-shaped occurrences | URL starts 4; references start 21; UUIDs start 3 |
| `research/phase-1/experiments/notion/connector-roundtrip.json` | 107 private Notion URLs; 176 collection/formula references; 327 UUID-shaped occurrences | URL starts 5; references start 66; UUIDs start 4 |
| `research/phase-1/notion-validation.md` | 2 private destination URLs; 6 data-source UUIDs | 27, 89; IDs 51–56 |
| `research/phase-1/phase-1-recommendation.md` | 1 private experiment URL | 94 |
| `research/phase-1/README.md` | 1 private experiment URL | 53 |
| `research/phase-1/experiments/notion/README.md` | 1 private experiment URL | 5 |
| `research/agent-skills.md` | 1 local user path; 1 absolute workspace path | 16, 18 |
| `research/skill-installation-manifest.json` | 28 absolute installation paths | Starts 10, 23, 36; repeats per installed skill |
| `research/phase-2/experiments/collaboration/README.md` | 2 user-specific runtime/dependency paths presented in reproduction commands | 16, 17 |
| `research/repositories/notion-expense-automation.md` | 1 user-specific reference-checkout path | 9 |
| Ignored OCR install/smoke logs | 30 absolute workspace/runtime path occurrences across three logs | Logs remain excluded; no need to publish them |
| Ignored receipt-source JSON | 1 absolute machine path in one of six source metadata files | Source metadata line 44 |

The synthetic Notion records are not real diner data, but their actual workspace destinations and object identifiers are unnecessary public disclosures. Earlier redaction of account identity and attachment references did not remove these locations. Do not equate “synthetic values” with “safe to publish raw account traces.”

**Negative observations, bounded to inspected content:** no high-confidence Notion/GitHub/OpenAI/Hugging Face/Google/AWS credential pattern, JWT-shaped credential, private-key marker, long Bearer value, email-like contact, suspicious literal secret assignment or signed-URL parameter was detected. No `.env` or credential-key filename appeared in the walked first-party scope. The six inspected image-source JSON files contained no URL/query/credential pattern. These checks do not cover excluded cache/vendor content or establish secret absence by entropy analysis.

## Safe sanitization strategy

1. **Preserve private originals outside the publishable tree or in a positively ignored private evidence location.** Do not upload the original-to-alias map. Do not delete or modify the external Notion scratch page to solve a Git privacy problem.
2. **Use one consistent synthetic identity map across both connector traces and narrative reports.** Replace each actual page/data-source/database/upload/root ID in both UUID and compact forms, including nested JSON strings, relation arrays, schema strings, collection/formula references and ancestor links. Alias by a synthetic stable role/sequence, preserving relation consistency. Replacing top-level `root` alone is insufficient.
3. **Remove actionable destinations.** Replace private Notion URLs with nonresolving `example.invalid` evidence aliases or plain “private destination withheld” labels. Rewrite collection/formula identifiers to consistent documented synthetic aliases. Do not retain a valid private destination behind a changed link label.
4. **Keep the observed facts.** Preserve money as integers, statuses, schemas, error categories, corrected attachment shape, ordering and the distinction between connector observations and REST documentation. State that published traces have synthetic identifiers and cannot reconnect to the original account. Exact account cleanup/replay instructions belong in private local notes; public reproduction creates a fresh explicitly authorized disposable destination.
5. **Make paths portable.** Use repository-relative installation destinations in the manifest while retaining upstream revisions and installed-file hashes. Describe preserved user installations with a generic home-relative convention. Replace workstation-specific reproduction commands with a documented activated runtime/dependency environment and relative script paths. Record historical measured runtime versions separately; do not present a private bundled-runtime path as a portable prerequisite.
6. **Do not fabricate historical integrity claims.** Sanitized evidence/document hashes will change. Preserve production source/test hashes when their files are untouched; update affected trace/manifest verification records or label old evidence hashes as historical/private originals. Explain the redaction rather than claiming byte-for-byte identity to the private capture.

## Excluded locations that need staging safeguards

- `.agents/skills/`: installed third-party collection, excluded from this content audit; preserve its license/provenance decisions separately. Do not accidentally publish global backups or reference-repository caches.
- `research/phase-1/experiments/ocr/{.venv,node_modules,cache}/`: dependencies/model downloads and cache metadata; exclude whole directories from staging.
- `research/phase-1/experiments/ocr/data/images/`: six historical receipt images, four synthetic images and six source metadata files. Keep excluded; original image redistribution rights are not established by the privacy check. Reproduction uses the documented sources and hashes, subject to their rights.
- OCR `*.log`, bytecode and runtime temporary directories: diagnostic/local artifacts, not required public evidence.
- `research/phase-1/experiments/notion/simulation.sqlite`: fake-remote scratch database; generated and reproducible from the script. The initial root ignore file did not itself exclude this file. Add an explicit ignore rule rather than rely on its fictional contents.
- `research/phase-2/experiments/transactions/DISPOSABLE-transactions-*.sqlite` and WAL/SHM sidecars: local scratch files already covered by that experiment's ignore file; verify the staged set nevertheless.
- `.git/`: metadata is outside this content audit. Remote authentication must use the credential mechanism, never a committed credential or token-bearing remote URL.

## Required final check

Before publication, inspect the **actual staged paths and staged contents**, not just working-tree search results: all affected Notion links/IDs must be absent or consistently synthetic, portable commands repaired, generated/cache/private artifacts excluded and JSON still parseable. Rerun token/signed-URL/private-destination checks over the staged first-party tree. Confirm that sanitization did not change accepted financial source/tests or numeric experiment outcomes. Record the successful post-sanitization check independently of this initial review.

This report intentionally retains the initial blocking finding. The orchestrator may close it after reviewing actual sanitized artifacts and final staging evidence; no next-feature work or phase authorization is supplied by this review.
