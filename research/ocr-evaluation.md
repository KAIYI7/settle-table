# OCR options and recommendation

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../docs/agents/governance.md) and the [transition ledger](../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

Status: document comparison complete; empirical benchmark remains a proposed next-phase gate. Accessed 2026-10-16. No receipt benchmark or application implementation has been performed. **No numerical Malaysian accuracy or latency claim is established.** Context7 was queried for PaddleOCR, RapidOCR, Tesseract, Tesseract.js, Google ML Kit, Apple Vision and Gemini API.

## Recommendation (inference)

Evaluate a **hybrid local OCR → deterministic receipt parser/reconciliation → human correction**, with a budgeted, opt-in vision fallback for unreadable/ambiguous receipts. Do not send every image to a paid API. The local engine depends on delivery platform: native device OCR is attractive in a native shell; RapidOCR/PaddleOCR is a strong CPU/self-hosted candidate; Tesseract.js offers a browser baseline. Select after a small representative Malaysian test set, not upstream marketing benchmarks.

## Comparison

Accuracy assessments below are expected failure modes and test hypotheses, not measurements. “Offline” means required models/assets are already present. Local server OCR keeps data out of a model vendor but still uploads receipts to our service; it is not on-device privacy.

| Option | Verified capabilities | Malaysian suitability / uncertainty | Privacy/offline | Complexity and cost inference |
|---|---|---|---|---|
| Native Apple Vision / Google ML Kit | On-device image text; Apple has accurate/fast modes and ranked confidence candidates; ML Kit supports Latin and Chinese recognizers. | Promising Latin English/Malay and mixed Chinese receipts; query Apple language support at runtime and test mixed scripts. Script support is not proof of receipt-field accuracy. | Local inference; offline after provisioning models. ML Kit bundled versus download delivery must be chosen deliberately. | No per-receipt OCR API bill. Native integration and device QA; not a standard browser API. |
| PaddleOCR | Detection/recognition pipelines, scores and multilingual models; PP-OCRv5 Latin model explicitly includes Malay; Chinese/English models exist. | Good candidate for varied layouts/mixed scripts; model selection/routing and thermal print quality require tests. Newer model defaults in main may differ from pinned v5 examples. | Can run local CPU/server with models downloaded; browser-native deployment not assumed. | Larger ML/runtime/packaging burden than Tesseract; no required per-call fee, but server CPU/RAM and maintenance are recurring costs. |
| RapidOCR | Offline cross-platform OCR using converted models; boxes/text/scores; default Chinese/English, other model selection explicit. | Strong practical CPU baseline hypothesis. Verify the exact converted Latin/Malay model and its license; do not assume default Chinese recognizer covers Malay equally well. | Local/server; provision model cache for offline use. | ONNX-oriented deployment may simplify operations versus full Paddle; benchmark memory/cold start. No mandatory per-call fee. |
| Tesseract engine / Tesseract.js | Offline engine, multilingual traineddata including `eng`, `msa`, `chi_sim`/`chi_tra`; TSV gives word boxes/confidence. JS wrapper enables browser/Node use. | Useful transparent baseline; official quality guidance requires attention to skew, borders, binarization and segmentation. Receipt columns/abbreviations/low contrast need parsing and preprocessing. | Browser worker can keep image local after assets/models are cached; server alternative still uploads. | Lowest-infrastructure browser route but model download, memory and mobile latency need measurement. No required OCR service fee. |
| Direct vision LLM | Image plus prompt can produce structured fields; schema-constrained syntax does not prove values true. | Can interpret irregular layout/multilingual abbreviations; can omit/hallucinate lines, normalize away evidence or confuse subtotal/tender/change. Must reconcile all amounts and retain manual review. | Hosted: online and image goes to provider, subject to its terms. Self-hosted vision: offline possible after model provisioning, with model/license/hardware verification. | Hosted: recurring image/input/output/retry token charges and drift. Self-hosted: RAM/GPU/CPU cost and deployment work, no assumed hosted-model accuracy equivalence. |
| Hybrid | Local text/boxes/scores plus deterministic evidence checks; optional image-aware fallback. | Best balance hypothesis, not proven best accuracy. Fallback with original crop can recover text that an OCR-text-only LLM never received correctly. | Offline local path; explicit privacy transition for cloud fallback. | More pipeline/testing work; spending scales with escalation fraction rather than every receipt. |

## Proposed extraction contract and fallback gates (inference)

Preserve four layers: original image, raw OCR with geometry, proposed structured fields, and user-approved financial values. Retain Unicode labels; do not strip non-ASCII text or silently substitute sample/demo receipts on failure.

| Extracted entity | Required evidence / uncertainty behavior |
|---|---|
| Document | Receipt hash, source dimensions/orientation, engine/model revision, locale/currency candidates, raw text, capture/extraction time. Never infer MYR from a dollar sign alone. |
| Field | Raw token string, parsed candidate value, source bounding boxes/line IDs, method (`ocr`, deterministic, vision, manual), score if available, warnings and reviewed flag. Nullable unknowns; no default 6%/8%/10% rates. |
| Line item | Raw/corrected label, quantity and unit amount only if printed or explicitly confirmed, line total, linked discount/adjustment if identifiable. Preserve multi-line item continuations, modifier lines and fractional quantities. |
| Totals | Printed subtotal, SST/tax amount and label, service charge, discounts, rounding, final total; separate cash tender/change. Mark inclusive versus exclusive tax unknown until supported by evidence. |

Use OCR scores as **ranking features**, not calibrated probabilities of financial correctness. An LLM's self-reported confidence is also uncalibrated. Combine low-score amount tokens, missing/duplicate lines, quantity × price disagreement, unexpected negative amounts, competing total candidates, and exact cent reconciliation. A plausible arithmetic sum alone cannot prove that the right items were read.

1. Crop/rotate/perspective-correct with reversible image provenance; attempt native PDF text extraction for digital PDFs before OCR. Render image-only PDFs before Tesseract.js, which does not accept PDF input directly.
2. OCR locally; parse spatial price columns and Malaysian label variants (e.g. RM/MYR, SST, service/caj perkhidmatan, discount/diskaun, round/rounding). These are parser vocabulary examples, not a claim that every merchant uses them.
3. Classify **review-needed** on field evidence and reconciliation. Thresholds must be tuned on the benchmark; do not adopt the automation sample's 15% mismatch tolerance or an invented “90% reliable” cutoff. Display receipt crop next to editable fields even when all checks pass.
4. When user policy permits, retry a targeted crop or use an image-capable LLM for unresolved fields; give it the original/crop plus OCR evidence, require nullable schema output, validate independently, and record provenance. A text-only LLM cannot recover unread pixels reliably.
5. Never commit financial allocations directly from an LLM response. Manual entry remains a complete path when offline/cloud-disabled or after bounded retries. Distinguish service failure from extraction ambiguity.

## Malaysian validation gate before choosing an engine

Proposed next-phase experiment: use a consented/de-identified set of roughly 50–100 local receipts, separately label items and totals, and stratify by restaurant/POS, English/Malay/Chinese/Tamil or mixed scripts, long thermal rolls, faded print, folds/glare/skew, wrapped names/modifiers, quantities, discounts, multiple taxes, service charge, inclusive pricing and cash-rounding lines. Include digital PDFs and midrange phones, not only clear desktop samples. This sample size is a planning assumption, not enough to establish every merchant's reliability.

Split calibration and holdout merchants/layouts. Compare all engines on the *same images*. Report exact line-amount/quantity match, item recall, exact final total, tax/service/discount field match, false acceptance of wrong totals, manual correction time, fallback fraction, p50/p95 runtime, model download size and device memory. Measure local-only and hybrid separately. Set release acceptance criteria with the owner before testing; require cent conservation and user review for every finalized receipt. Language support and public OCR benchmarks do not replace this evidence.

## Licensing, reproducibility and current-version caveats

Official public repository HEAD metadata retrieved 2026-10-16 (documentation/source sampling, not application-level audits):

| Upstream | HEAD at access | Library license |
|---|---|---|
| [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR/tree/dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf) | `dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf` (2026-09-16) | Apache-2.0 [LICENSE](https://github.com/PaddlePaddle/PaddleOCR/blob/dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf/LICENSE) |
| [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR/tree/7cfd3d9ef786a2e538ca30df700325e72e85b5f5) | `7cfd3d9ef786a2e538ca30df700325e72e85b5f5` (2026-10-13) | Apache-2.0 [LICENSE](https://github.com/RapidAI/RapidOCR/blob/7cfd3d9ef786a2e538ca30df700325e72e85b5f5/LICENSE) |
| [naptha/tesseract.js](https://github.com/naptha/tesseract.js/tree/a1ca80d9e31c34512d0ded75ff8821ddcf3f2f91) | `a1ca80d9e31c34512d0ded75ff8821ddcf3f2f91` (2026-05-17) | Apache-2.0 [LICENSE.md](https://github.com/naptha/tesseract.js/blob/a1ca80d9e31c34512d0ded75ff8821ddcf3f2f91/LICENSE.md) |
| [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract/tree/b2544450ca01407259ed53c870b7e5e4c67f7789) | `b2544450ca01407259ed53c870b7e5e4c67f7789` (2026-10-10) | Apache-2.0 [LICENSE](https://github.com/tesseract-ocr/tesseract/blob/b2544450ca01407259ed53c870b7e5e4c67f7789/LICENSE) |

These permissive library licenses do not automatically clear every downloaded model, dataset, runtime dependency or native SDK term. Pin/checksum the actual selected weights and assets, verify their distribution rights and preserve notices before shipping. Native ML Kit/Apple SDK use is governed by vendor terms, not a blanket open-source license.

Current Tesseract.js README mentions v7; the v6 section explains changed output defaults (non-text outputs opt-in). Context7 examples still include older CDN versions; use the pinned chosen release API, self-host/cache all required worker/WASM/language assets for privacy/offline, and request geometry deliberately. PaddleOCR main source retrieved by Context7 includes v6 model selection while deployment examples show v5; choose an explicit model/revision, do not describe v5 as necessarily the latest. RapidOCR defaults Chinese/English; converted model availability is a separate check from Paddle language support.

## Cost model and privacy trade-off

Local inference has $0 required per-call license/API charge; compute, battery, bandwidth, asset hosting, storage and maintenance are not free. Server inference needs measured CPU seconds/RAM per receipt before choosing hosting. Zero paid API usage remains feasible with manual correction as fallback; that does not establish adequate automation quality.

Hosted comparison example only: official [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), accessed 2026-10-16, lists Gemini 2.5 Flash-Lite standard at $0.10/million text/image input tokens and $0.40/million output tokens (including thinking). Free-tier data is listed as used to improve products; paid-tier data is listed as not used for that purpose. This is not a zero-retention guarantee or a model recommendation. Confirm terms, region availability, model lifecycle and tokenization before any personal-receipt pilot.

Illustrative assumption: 3,000 input tokens including image plus 1,000 output tokens costs $0.0007 per call at those rates. For 1,000 receipts/month, one call each is $0.70; escalating 20% is $0.14, excluding retries, infrastructure, taxes and exchange rates. Actual image tokens/output/thinking vary; track billed usage and enforce receipt/monthly spend caps. Compare cost per *correct reviewed receipt*, not just nominal request price. Grounding/search is unnecessary for reading a receipt and must not be enabled accidentally.

Schema-constrained JSON reduces parse errors but still requires semantic validation, per the [official structured-output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output). Receipt content is untrusted model input: extraction must have no tool authority to execute instructions printed on the receipt.

## Primary sources

- [Apple text recognition](https://developer.apple.com/documentation/vision/recognizing-text-in-images), [runtime language list](https://developer.apple.com/documentation/vision/vnrecognizetextrequest/supportedrecognitionlanguages()), [ranked candidates](https://developer.apple.com/documentation/vision/vnrecognizedtextobservation/topcandidates(_:)).
- [ML Kit overview](https://developers.google.com/ml-kit/guides), [Android text recognizer/model delivery](https://developers.google.com/ml-kit/vision/text-recognition/android).
- [PaddleOCR deployment and languages](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/inference_deployment/local_inference/cpp/OCR.en.md); [PaddleOCR main](https://github.com/PaddlePaddle/PaddleOCR).
- [RapidOCR main](https://github.com/RapidAI/RapidOCR), [output fields](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/utils/output.py), [model list](https://rapidai.github.io/RapidOCRDocs/main/model_list/).
- [Tesseract manual/license](https://tesseract-ocr.github.io/tessdoc/), [language data](https://github.com/tesseract-ocr/tessdoc/blob/main/Data-Files.md), [quality guidance](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html), [TSV output](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).
- [Tesseract.js scope and changes](https://github.com/naptha/tesseract.js/blob/a1ca80d9e31c34512d0ded75ff8821ddcf3f2f91/README.md), [local asset paths](https://github.com/naptha/tesseract.js/blob/a1ca80d9e31c34512d0ded75ff8821ddcf3f2f91/docs/local-installation.md).

## Evidence conflicts and outstanding questions

- The [Notion automation inspection](repositories/notion-expense-automation.md) has local PDF text rules plus LLM text extraction, not photo OCR. Its confidence system is not evidence of measured image accuracy or a cost-saving OCR fallback gate.
- A supplementary local-Paddle/Ollama candidate was identified by the coordinating research stream; consult its repository report for observed Unicode stripping, dropped score geometry and mock-on-failure problems. “Local OCR” in an architecture description alone does not establish privacy, Unicode preservation or confidence-gated LLM usage.
- No engines/models were installed, no private receipts transmitted, no comparative OCR benchmark or native device build performed. Best engine, actual mobile performance, multilingual model packaging, latency budget, acceptable fallback rate and privacy consent remain unresolved. These require an explicitly approved experimental next phase, not immediate app implementation.
