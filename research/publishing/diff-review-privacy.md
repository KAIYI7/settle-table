# Staged privacy/evidence diff review

2026-10-17. **PASS for the assigned sanitized publication scope; zero remaining blocking privacy/evidence findings.** This closes the initial unchanged-snapshot finding in [privacy-review.md](privacy-review.md), without erasing that historical finding. It does not authorize a push or a next feature. The orchestrator owns final staging, commit and remote branch/tag verification.

## Actual index reviewed

Reviewed full indexed blobs obtained with `git show :<path>`, not working-tree summaries, together with staged path/status metadata. All assigned files were new baseline additions. At the final check, the index contained **197 files**, of which **41** fell under `research/phase-1/**` or `research/publishing/**`. Full-blob automated inspection covered every assigned byte; targeted human reading covered publication qualifications, reproduction commands, acquisition/inference scripts, Notion evidence and the changed OCR report. JSON received structural/numeric comparisons rather than a claim that every large generated row was manually reread.

Assigned-scope snapshot fingerprint, SHA-256 of sorted `path<TAB>blob_sha256` rows joined by newlines: `8a146b6faadf4654dc87a41c01f77f68891a9b42c964ae58ded585bc3407fbde`. Per-file coverage is below. This report is new review output and was not included in its own input snapshot. Later audit-report regeneration changes that report's snapshot hash; the orchestrator must rerun final staging checks after all review records are staged.

## Checks and results

| Gate | Result and evidence |
|---|---|
| Actual private Notion identities | **PASS:** checked all 197 staged blobs against 24 canonical original identities, using the ignored map's 48 compact/hyphen spellings and decoded/case-insensitive comparison. Zero survivors. No original identifier or map is reproduced here. |
| Alias consistency | **PASS:** both spellings of each original identity map consistently; the assigned artifacts contain 24 synthetic aliases, all from that map. Private destinations now use `example.invalid`; these are intentionally nonreplayable evidence links. |
| Private backups and map | **PASS:** `git check-ignore` positively matches both private map and original-backup locations. Neither `.local/` nor its contents is in the index. |
| Credentials and signed URLs | **PASS within heuristic limits:** zero matching provider-token, long Bearer, signed-URL credential parameter or private-key patterns across the staged blobs inspected. This is not an entropy-based proof that arbitrary credentials cannot exist. No `.env` contents were read. |
| Local assets and receipt rights | **PASS:** no OCR images, raw receipt labels/transcriptions/engine proposals, preparation script, model/runtime cache, environment, dependency tree or local database appears in the staged path set. The public corpus manifest contains only selected identity/hash/provenance fields, not receipt entities/text. All ten records' selected fields exactly match their local original corpus records. Original rights remain qualified, not cleared by this review. |
| Numeric JSON preservation | **PASS:** all 13 assigned JSON files parse. Nine have private original backups; all **773 typed numeric leaves** match exactly at their structural paths, with zero differences. This includes 345 aggregate OCR metric values and 114 connector-roundtrip numbers. No historical-preservation claim is made for the newly authored manifest/audit metadata or dependency JSON lacking backups. |
| Embedded Notion observations | **PASS:** checked 610 corresponding string leaves across both connector traces, excluding URL/identity substrings; their 111 remaining numeric tokens are unchanged. The observed fractional-number probe, restored integer state, 3365-sen totals, revision/status observations and recovery-test values remain evidence rather than invented reruns. Private URL/markup/query placeholders changed; published traces are not byte-identical or account-replayable captures. |
| Portable commands | **PASS:** no absolute Windows/user-home path remains in the assigned indexed content. Reproduction uses relative experiment paths and reader-provided environments. OCR commands are explicitly historical and require separately provisioned permitted inputs/models; they are not advertised as a complete fresh-clone fixture pack. |
| Historical hashes and withheld links | **PASS after targeted correction:** the orchestrator added a publication qualification to `phase-1/ocr-validation.md` and replaced six links to deliberately withheld artifacts with plain local references plus available manifest/metrics links. The staged update was reread. Publishing and OCR guides distinguish original historical hashes/timings from sanitized current bytes and state that OCR was not rerun. |

Numeric checks compare actual staged JSON with ignored originals in memory; the originals, identity map and their values were not copied to the report. Numeric observations embedded in strings were compared after excluding URL/identity material so alias sequence numbers could not masquerade as changed financial evidence. Preserving aggregate results does not independently revalidate the withheld raw receipt labels or recognition outputs.

## Findings resolved and remaining limits

The initial raw private-destination disclosure is closed for this index snapshot. The only new documentation issue found was the six withheld-artifact links without a local publication qualification; the orchestrator corrected and staged that report, and this reviewer verified the replacement.

Original OCR images/labels/raw proposals remain unavailable in the public baseline by design. Public hashes/aggregate metrics support evidence identity and interpretation, not a complete independent recomputation from a clone. Published Notion traces retain synthetic observations but cannot open or clean up an account. Full release licensing, project-wide license choice and vendor attribution are separate rights-review responsibilities.

`staged-audit.json` is itself a historical audit snapshot and was inspected at the hash below; its then-recorded file count predates additional staged notices/reviews. Refresh the audit over the final index before commit rather than presenting the earlier count as the final baseline. This is a required orchestration check, not an unresolved private-data finding in the assigned source.

No other file was modified by this reviewer. No commit, push, credential action, Notion/external request, implementation change or next-feature work was performed.

## Per-file coverage

Every row passed full staged-content privacy/path inspection. JSON rows also passed parsing; backed-up numeric evidence received the comparisons above. Hashes are SHA-256 prefixes identifying the exact reviewed blobs, not hashes of private originals.

| Indexed file | SHA-256 prefix | Lines | Result |
|---|---|---:|---|
| `research/phase-1/README.md` | `0c41b9ec691c4a2a` | 57 | PASS |
| `research/phase-1/architecture-decision.md` | `a26e1f919010720c` | 72 | PASS |
| `research/phase-1/architecture-evidence.md` | `c7833bd7372bb959` | 16 | PASS |
| `research/phase-1/domain-model.md` | `be425d90f9d542b4` | 112 | PASS |
| `research/phase-1/experiments/README.md` | `6bde3a612a6b3c7f` | 9 | PASS |
| `research/phase-1/experiments/collaboration/README.md` | `d9a69877a19b3d62` | 7 | PASS |
| `research/phase-1/experiments/collaboration/results.json` | `bb914b2d44c33098` | 146 | PASS |
| `research/phase-1/experiments/collaboration/simulate.py` | `4d4b5fd07bf23c34` | 200 | PASS |
| `research/phase-1/experiments/domain/README.md` | `71e315ccc33410d8` | 16 | PASS |
| `research/phase-1/experiments/domain/results.json` | `1ceb5c9593051b5d` | 1199 | PASS |
| `research/phase-1/experiments/domain/validate_domain.py` | `112d0c6f73906e49` | 580 | PASS |
| `research/phase-1/experiments/domain/verification.json` | `6f02e862014326bd` | 13 | PASS |
| `research/phase-1/experiments/notion/README.md` | `6b362292bfe67cfe` | 21 | PASS |
| `research/phase-1/experiments/notion/connector-evidence.json` | `7115d78746f5d87d` | 255 | PASS |
| `research/phase-1/experiments/notion/connector-roundtrip.json` | `a7aba3f1eb4d31e8` | 1494 | PASS |
| `research/phase-1/experiments/notion/retry_simulation.py` | `22aca725a826064a` | 196 | PASS |
| `research/phase-1/experiments/notion/simulation-results.json` | `9a957f437acdf2bd` | 79 | PASS |
| `research/phase-1/experiments/notion/synthetic-receipt.svg` | `9ed3dc351689d70a` | 1 | PASS |
| `research/phase-1/experiments/ocr/.gitignore` | `e0e4d76722472fbf` | 7 | PASS |
| `research/phase-1/experiments/ocr/README.md` | `b2cd423f726ccd08` | 43 | PASS |
| `research/phase-1/experiments/ocr/acquire.py` | `965700233e5830af` | 44 | PASS |
| `research/phase-1/experiments/ocr/add_perspective.py` | `aef4a5df54f147e0` | 43 | PASS |
| `research/phase-1/experiments/ocr/data/corpus-manifest.json` | `ece2249905e0f3b4` | 87 | PASS |
| `research/phase-1/experiments/ocr/package-lock.json` | `aaec2788a765ea14` | 126 | PASS |
| `research/phase-1/experiments/ocr/package.json` | `8e0dcea1ed059e49` | 5 | PASS |
| `research/phase-1/experiments/ocr/parse_evaluate.py` | `096a3de2cf0aa21a` | 243 | PASS |
| `research/phase-1/experiments/ocr/requirements-frozen.txt` | `c4a3abffb8235610` | 77 | PASS |
| `research/phase-1/experiments/ocr/results/metrics.json` | `8963ab0582505f7d` | 546 | PASS |
| `research/phase-1/experiments/ocr/run_local.py` | `80d7dda86386c18c` | 67 | PASS |
| `research/phase-1/experiments/ocr/run_tesseract.cjs` | `304b8539e0c88af5` | 35 | PASS |
| `research/phase-1/experiments/ocr/verification.json` | `eec0848c250e6943` | 42 | PASS |
| `research/phase-1/notion-validation.md` | `068ff57cf6fe67a9` | 107 | PASS |
| `research/phase-1/ocr-validation.md` | `43700c084ddfd66c` | 98 | PASS |
| `research/phase-1/phase-1-recommendation.md` | `6470846f0bc43ba0` | 96 | PASS |
| `research/phase-1/requirements.md` | `6cc472d105a80d7a` | 80 | PASS |
| `research/phase-1/verification.json` | `e0e00c964c10981d` | 36 | PASS |
| `research/phase-1/verification.md` | `c985b7ae3edb26f9` | 45 | PASS |
| `research/publishing/README.md` | `aa92abe4a7af241e` | 29 | PASS |
| `research/publishing/privacy-review.md` | `8462bfe5764fc07d` | 57 | PASS |
| `research/publishing/rights-review.md` | `d009efe5dc5687f1` | 45 | PASS |
| `research/publishing/staged-audit.json` | `87bab4ce57ee1ea2` | 978 | PASS |
