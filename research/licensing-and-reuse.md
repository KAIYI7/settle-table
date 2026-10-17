# Licensing and reuse decisions

Access date 2026-10-16. This is a source-evidence and project reuse policy assessment, not a blanket legal clearance. Exact commits, license links, dependencies and uncertainties are recorded in each linked report. No candidate application source has been copied into this workspace.

## Application sources

| Candidate | Verified evidence | Reuse decision |
|---|---|---|
| [BillSplit](repositories/billsplit.md) | Complete MIT license | Selected source may be adapted with notices; prefer UX patterns over its fee/persistence engine. |
| [Spliit](repositories/spliit.md) | Complete MIT license | Selected helpers/test patterns eligible with notices and provenance review; avoid wholesale single-payer model adoption. |
| [SplitPro](repositories/split-pro.md) | Complete MIT license | Eligible at repository level, but independently trace attributed third-party algorithm origins before copying helpers. |
| [Malaysian Receipt Splitter](repositories/malaysian-receipt-splitter.md) | Complete MIT license | Eligible with notices; arithmetic and multilingual/fallback defects make direct adaptation unattractive. |
| [ReceiptIQ](repositories/receiptiq.md) | No explicit license grant in inspected tree/README | **Reference-only. No source reuse.** Independently express general pipeline ideas. |
| [Notion Expense Automation](repositories/notion-expense-automation.md) | No explicit license; metadata license null | **Reference-only. No source reuse.** Independently design outbox/journal concepts. |
| [Ai-bill-splitter](repositories/ai-bill-splitter.md) | README labels MIT; no full grant/copyright/license file | **Ambiguous; reference-only pending clarification.** Do not falsely claim no license mention exists, or treat the label as sufficient clearance. |

**Verified policy basis:** public visibility alone is not permission to reproduce or distribute source. GitHub documents default copyright restrictions absent a license and distinguishes GitHub viewing/forking rights. GitHub also acknowledges README license statements: therefore the Ai-bill-splitter finding is ambiguity, not a categorical statement that a separate LICENSE file is universally required. [GitHub licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

**Inference/decision:** use patterns, not copied snippets, from unlicensed/ambiguous projects. If source reuse becomes desirable, obtain an explicit upstream grant before adoption; no maintainer messages have been sent. MIT project reuse can generally coexist in a new product with retained notices, but does not clear every dependency, model, font, photo, fixture or copied algorithm.

## Installed agent content

Matt Pocock's inspected collection is MIT. Impeccable is Apache-2.0; preserve its license/notice information and mark any local modifications. Their code and companion files are agent tooling, not automatically application dependencies. Full installation records and checksums: [agent skills](agent-skills.md). No global license or skill installation was rewritten.

Vercel evaluation is scoped: its React skill declares MIT; do not assume every package or external fetched guideline has the same license. It was inspected but not installed. See [technology options](technology-options.md).

## OCR and model boundary

Refer to [OCR evaluation](ocr-evaluation.md) for engine/wrapper licenses and exact source limitations. Engine license, converted model weights, training data and a hosted service's terms are separate questions. ReceiptIQ's PyMuPDF dependency is a particular review trigger; it is unnecessary for an initial image-only scope. Gemma model terms are distinct from the Malaysian sample's MIT app license. Do not copy upstream sample receipts into a distributable benchmark without confirming rights and removing personal data.

## Adoption checklist for the approved next phase

For every actual copied file, record origin repo/SHA/path, license/notice, changes and dependency/asset provenance. Retain required notices in source/distribution and create a third-party notice inventory. Resolve unclear helper attribution and model licenses before adding them. Choose the new project's own license deliberately; this research does not select or publish one. No dependency SBOM or full transitive license audit has been performed because no application dependency graph exists.
