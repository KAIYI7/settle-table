# Phase 1 OCR validation

Publication note2026-10-17: this is a historical experiment report. Original images, receipt-level labels/raw outputs and the local preparation script remain withheld from Git for rights/privacy. Local evidence references below are not downloadable fixtures in this checkout. Public [corpus identity/hash manifest](experiments/ocr/data/corpus-manifest.json), aggregate metrics and [reproducibility limits](../publishing/README.md) remain available. Recorded original hashes/timings were not regenerated after sanitization.

Accessed **2026-10-16**. **Feasible CPU experiment complete; representative production accuracy and on-device validation remain open.** No production pipeline, hosted vision call or private receipt upload. User explicitly requires local-only OCR for Phase 1 and device/self-hosted-only OCR for the product; no private receipt folder was provided.

## Question and method

Compare RapidOCR, PaddleOCR and Tesseract.js with the same ten local images. Six are selected historical Malaysian dining scans (2017–2018); four are known synthetic layouts: clear, faded/blurred, tilted with shadow, and perspective-warped. Two sequential passes per engine; score **second-pass** output and report its six-real-image median/max, not p95 from an inadequate sample. Model import/constructor is timed separately with cached models; Rapid may initialize lazily on first prediction. OS caches/background load are not controlled, so latency is exploratory workstation wall time, not a phone/service SLA. No camera, browser UI, live phone or native SDK was exercised.

A frozen small deterministic parser reconstructs rows from boxes and extracts dates, totals, items and charges. It does not consume truth labels. Evaluation uses strict normalized exact text and fixed item-order alignment; missing rows count as misses, extra rows make the whole candidate incorrect. This can heavily penalize shifted lists. Monetary values are parsed directly into integer sen; OCR scores/timing/pixel transforms are nonmonetary decimals. Unknown extracted fields remain null. Known absence is scored separately from positive fields, never as invented zero.

**Development-set limitation:** parser heuristics and annotations were prepared after inspecting this small corpus; there is no held-out set. Labels extending SROIE are agent visual transcriptions, not independently human-verified gold. They can contain uncertainty/errors; obscured quantities/unit prices and ambiguous time are excluded from positive denominators. The coordinator continued persisted scripts after an agent usage interruption. These results test a baseline, not general engine accuracy or a validated production parser.

## Reproducible inputs and versions

- Public image IDs/hashes: [corpus identity manifest](experiments/ocr/data/corpus-manifest.json). Original source entities and annotations remain local in `experiments/ocr/data/corpus.json` and `experiments/ocr/data/truth.json`; they are withheld rather than included fixtures.
- Dataset curator repository [jsdnrs/ICDAR2019-SROIE](https://github.com/jsdnrs/ICDAR2019-SROIE/tree/77c4c11490e3c4179ee22f86611569c71c04b5f9), revision `77c4c11490e3c4179ee22f86611569c71c04b5f9`; downloaded dataset revision `bffe40c26759f3376ec2b3ae9031dbba54cd587c` on [Hugging Face](https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE/tree/bffe40c26759f3376ec2b3ae9031dbba54cd587c). Curator LICENSE/NOTICE claims CC-BY-4.0 and credits SROIE authors; original competition terms could not be independently retrieved. **Rights provenance remains qualified; image/model caches are ignored research assets, not cleared product fixtures.** Acquisition now refuses changed dataset HEAD instead of silently switching inputs. Original author paper: [Huang et al.](https://arxiv.org/abs/2103.10213).
- System Python3.14.6; isolated bundled Python3.12.14 for ML wheels; Node22.20.0; Intel Core i5-12450H. CPU runners configured4 threads; [full Python freeze](experiments/ocr/requirements-frozen.txt) and experiment-local npm lock retained. No global packages or framework skills changed.
- RapidOCR3.10.0 / ONNX Runtime1.31.0, packaged PP-OCRv6 small detection/recognition plus mobile classifier. PaddleOCR3.7.0 / PaddlePaddle3.3.1, PP-OCRv5 mobile detection and English recognition, orientation/dewarp disabled. Tesseract.js7.0.0, English+Malay (`eng`,`msa`), page segmentation6, Node WASM worker (not a measured browser implementation). These are concrete configurations, not best-tuned equivalents or every model supported by each engine.
- Paddle first failed in oneDNN (`ConvertPirAttribute2RuntimeAttribute`); a bounded retry with `enable_mkldnn=False` succeeded. Failure/success logs retained locally. Tesseract warned of narrow unrecognized lines. Those failures are not discarded.
- Context7 resolve→query completed for RapidOCR, PaddleOCR, Tesseract.js and Pillow before relevant API use. Current source documentation can disagree with old examples; measured installed versions above govern this run.

## Field-level end-to-end results: real historical scans

Counts are correct / positively labeled observations, **OCR plus this parser**, not OCR recognition alone. A zero denominator is unmeasured. Some errors are parser layout errors despite correct raw recognized words.

| Field | RapidOCR | PaddleOCR | Tesseract.js |
|---|---:|---:|---:|
| Merchant | 3/6 | 3/6 | 1/6 |
| Date | 5/6 | 5/6 | 5/6 |
| Time (known only) | 3/4 | 3/4 | 3/4 |
| Item name | 13/28 | 4/28 | 3/28 |
| Quantity (known only) | 15/27 | 12/27 | 6/27 |
| Printed unit price | 13/16 | 12/16 | 11/16 |
| Line total | 16/28 | 16/28 | 13/28 |
| Printed subtotal | 5/6 | 5/6 | 3/6 |
| Tax (GST in real corpus) | 6/6 | 6/6 | 5/6 |
| Service charge | 3/3 | 3/3 | 3/3 |
| Discount/voucher | N/A (0 positive labels) | N/A (0 positive labels) | N/A (0 positive labels) |
| Printed rounding adjustment | 4/4 | 4/4 | 3/4 |
| Final total | 6/6 | 6/6 | 3/6 |

No real modern SST or voucher/discount-positive receipt was available. “Tax” success above is historical GST, not validated current SST understanding. Complete positive/absence counts and synthetic field results: [metrics.json](experiments/ocr/results/metrics.json). Never average real and synthetic scores into a claimed Malaysian accuracy.

## Timing, memory and local feasibility

| Configuration | Cached import/constructor | Real second-pass median / max | Observed max process RSS after inference |
|---|---:|---:|---:|
| rapidocr | 1.187s | 2.602s / 4.436s | 154 MiB |
| paddleocr | 3.904s | 14.254s / 31.541s | 392 MiB |
| tesseract | 0.273s | 2.390s / 3.706s | Not measured |

RSS is sampled after each call, not a true peak or total installed size. Tesseract worker/process memory was not measured. No measured GPU, phone battery, concurrency, first-ever model download or browser cold-start cost. Rapid was materially faster than this Paddle configuration on this workstation; that does not rank all Paddle models/hardware.

Tesseract reran with local language paths/WASM assets; Rapid/Paddle logs used cached local weights. This supports local inference after provisioning. It is not an OS-level network-disconnection/packet-capture proof. No image-upload or hosted image endpoint exists in these runners. Device-native ML Kit/Apple Vision remain documentation candidates only; no compatible phone/device runtime was available for a fair measurement.

## Confidence/hybrid hypothesis: counter-evidence

Frozen gate: mean OCR score at least0.90, recognized merchant/date/items and exact candidate arithmetic. Passing still routes to **human verification**; failing routes to **manual correction**. The numeric score is not a calibrated probability and this mean mixes engine-specific scores.

| Engine | Real manual-correction route | Real clean-but-incorrect candidates | Synthetic manual route | Synthetic clean-but-incorrect |
|---|---:|---:|---:|---:|
| rapidocr | 3/6 | 3/6 | 2/4 | 2/4 |
| paddleocr | 3/6 | 3/6 | 2/4 | 2/4 |
| tesseract | 6/6 | 0/6 | 2/4 | 2/4 |

**Experimental conclusion:** confidence plus matching final total is insufficient to accept extracted items. All three clean synthetic outputs preserve correct unit/line money but merge the quantity into the item label (`NASI IKAN 2`, quantity unknown). That is a parser-layout failure, not evidence that the OCR engine failed to read the digit. Some historical lists also shift/lose names while totals remain correct. Tesseract's0 real unsafe clean candidates occurs because all6 were sent to correction, **not because it extracted every field correctly**. No case bypasses human review.

The gate is preserved as a failed baseline; it was not tuned after scoring to hide counter-evidence. A better proposal needs per-field completeness, unit/line meaning, quantity conservation, geometry and calibrated risk evidence. Under user policy, no cloud AI escalation is available. Manual correction is viable; a self-hosted text/vision model is a future experiment, not a measured recovery layer. No cached Ollama/LM Studio model/runtime was found; downloading a large VLM was not necessary for this bounded CPU comparison. Direct hosted vision and cloud-hybrid recovery are **excluded by user**, rather than claimed inferior on unrun accuracy tests.

## Difficult-case coverage and gaps

| Case | Evidence | Limit |
|---|---|---|
| Thermal/faded print | Historical thermal receipt scans; synthetic reduced contrast/blur | No measured natural fade severity distribution |
| Tilt, perspective, shadow/poor light | Explicitly generated rotation+shadow and perspective fixtures | Synthetic transforms are not real phone acquisition quality |
| Malay/English/abbreviations | Historical Thai/Malay dish labels, SVC CHG/STTL, English/Malay synthetic names | No broad multilingual corpus, Chinese/Tamil script validation |
| Quantities/unit/line amounts | 27 labeled real quantities,16 printed unit prices,28 line amounts | One obscured quantity and unprinted units excluded |
| Modifiers/combos | Size/variant descriptions; vegetarian set has unpriced child labels | No broad separately priced modifier corpus |
| SST/service/discount/rounding | Service and rounding real; GST real; SST/discount synthetic | Modern SST and actual voucher-positive receipts unmeasured |
| Subtotal/grand-total ambiguity | Included-GST Wan Sheng and pre-round Coffee/Thai totals | Parser/general review policy remains provisional |

Wan Sheng has item sum600, printed net subtotal566 and included GST34: adding GST again is wrong. Kechara's printed components sum6448 but final is6450 without a printed rounding row; do not fabricate a2-sen adjustment. These are specific review triggers, not tolerance exceptions.

## Privacy, cost and implementation conclusion

**Verified:** all executed inference is local CPU; no hosted image call or paid model usage. Server-local OCR would still send a diner's image to the operator-controlled server, unlike device-only processing. Notion receipt archiving is a separate optional reporting/retention choice, not permission to call a hosted vision model.

**Cost inference:** required per-receipt vendor inference spend is USD0; hardware, asset delivery, storage, power and operations remain. At the measured real median,1000 sequential receipts occupy approximately43.4 wall-minutes for Rapid,237.6 for this Paddle configuration,39.8 for Tesseract; these are wall-time illustrations, not CPU billing or throughput under load. A continuously available collaborative server needs capacity/backups even when idle. No hosting quote or mobile/offline failure rate was measured.

**Recommendation:** keep RapidOCR as a practical self-hosted baseline and Tesseract.js as a candidate browser baseline; do not ship the experimental parser/gate. Paddle remains a model/configuration candidate but this CPU path is slower and had packaging/runtime friction. Retain required human verification and manual entry. Do not select a production OCR engine or native/web stack from six scans or assume model independence just because Rapid and Paddle have different wrappers.

## Reproduction and artifacts

[Experiment guide](experiments/ocr/README.md), [parser/evaluator](experiments/ocr/parse_evaluate.py), [aggregate metrics](experiments/ocr/results/metrics.json). Raw engine files `results/{rapidocr,paddleocr,tesseract}.json` and `results/parsed.json` remain local and are withheld. Original script/result/model/input hashes: [verification.json](experiments/ocr/verification.json); some original inputs/scripts are intentionally absent from this checkout. No private receipts or application code.

**Go/no-go:** feasible local OCR and field scoring demonstrated; **no-go for unattended receipt/item acceptance or confidence-only fallback selection**. Representative modern phone receipts, independent reviewed labels, held-out evaluation, actual mobile/device latency and local-model recovery remain required before promising automation quality.
