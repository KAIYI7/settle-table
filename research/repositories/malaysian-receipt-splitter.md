# lester-liam/receipt-splitter — additional Malaysian candidate

Accessed 2026-10-16. Exact revision [`766b2c9201007f589cb128f60936a0d2946d9fe0`](https://github.com/lester-liam/receipt-splitter/commit/766b2c9201007f589cb128f60936a0d2946d9fe0), latest commit 2026-02-01. Temporary shallow checkout; earlier history/commit count not audited. Added because GitHub search surfaced an explicit Malaysian SST/service-charge project combining PaddleOCR and local LLMs, directly relevant to our hypotheses.

**Decision/inference:** useful MIT concept reference and counterexample to claims that local OCR alone solves extraction. Do not fork its current arithmetic, failure handling, privacy logging or multilingual pipeline.

## Verified source findings

Main evidence: [main.py](https://github.com/lester-liam/receipt-splitter/blob/766b2c9201007f589cb128f60936a0d2946d9fe0/main.py), [site/index.html](https://github.com/lester-liam/receipt-splitter/blob/766b2c9201007f589cb128f60936a0d2946d9fe0/site/index.html), [prompt.txt](https://github.com/lester-liam/receipt-splitter/blob/766b2c9201007f589cb128f60936a0d2946d9fe0/prompt.txt), [LICENSE](https://github.com/lester-liam/receipt-splitter/blob/766b2c9201007f589cb128f60936a0d2946d9fe0/LICENSE), `pyproject.toml`, `requirements.txt`, `.env.example`, `site/css/style.css` at this revision.

| Dimension | Verified finding |
|---|---|
| License / maintenance | Complete MIT grant, copyright Lester Liam 2026. Version 0.2.0 in Python metadata/API. Latest fetched HEAD Feb 1; no inference of sustained support from a shallow snapshot. |
| Stack / architecture | Python FastAPI, PaddleOCR 3.3/PaddlePaddle 3.2, HTTPX, Google GenAI; static HTML uses React 18 development UMD plus runtime Babel from unpkg. Single Python module; React state in one HTML file. Separate OCR/extraction API, no domain database. |
| Receipt flow | Browser file upload (10 MiB client cap) to hard-coded localhost:8000/extract; multipart bytes decoded by OpenCV locally or base64 uploaded to configured Paddle AI Studio. API validates image MIME/nonempty but reads full body and has no matching explicit size cap. Rate limiter 5 requests/min; wildcard CORS. |
| OCR / extraction | Startup loads Paddle detection/recognition models. Local mode PaddleOCR then Ollama text parsing on **every** receipt. Cloud mode Paddle service then Gemini text parsing on every receipt. Python default local=true, but supplied .env.example sets false: following sample setup sends image/text externally. No confidence-triggered escalation. |
| Structured schema | Items UUID/name/float price/integer quantity; float SST/service percentages and notes. Prompt defines **unit price**. No printed subtotal/final total/currency/discount fields, raw evidence or normalized adjustment rows. Pydantic shape validation exists but permissive coercion skips malformed items and defaults invalid values. |
| Confidence / errors | OCR helper retains only rec_texts and swallows result-shape exceptions; scores/polygons dropped. API returns 400/422/502 for several failures, but logs raw OCR debug, prompt/JSON content and exception details. No confidence calibration or reconciliation check. |
| Malaysian suitability | en-MY/MYR formatting, editable SST/service rates and familiar dish examples. **main.py strips all non-ASCII characters before parsing**, losing Chinese/Tamil receipt content. Percent-only tax schema misses explicit fixed amounts/tax-inclusive bases. Defaults such as 6% in UI/examples are code examples, not verified current tax rules. |
| Human correction | Add/edit/delete item name/price/quantity, edit rates, add/delete people and toggle shared assignments. However, API error silently substitutes a plausible mock Nasi Lemak/Teh Tarik/Roti Canai bill, then displays receipt processed. Notes mention mock; ordinary result success still dangerous. |
| Participant / item model | Local person ID/name, item assignedPeople array. Unassigned items shown separately; no durable group, invitation, auth or multi-device state. Each item divided equally among selected people. |
| Charges / discounts | SST and service computed as percentages of assigned subtotal, allocated proportionally by consumption. No discounts, tax applicability, ordering, inclusive amounts or printed total reconciliation. Unassigned items excluded from subtotal. |
| Money / rounding | Python floats / JS Number, independent round2 shares. A 1.00 item shared by three yields 0.33 each and a computed itemsTotal of 0.99. No residual distribution. Prompt supplies unit price but calculation divides item.price without multiplying quantity, so a quantity-two line is undercounted if provider follows prompt. |
| Settlements | Per-person consumption totals only; no payer credits, net debts, settlement optimization/history/status. |
| Persistence / Notion | In-memory React state only; refresh loses bill. No DB or Notion integration. No intentional durable receipt retention; logs can retain receipt content. |
| Tests | examples/test.py is a manual endpoint caller; sample Paddle API response and four receipt images exist. No automated arithmetic/contract regression suite or CI found in tracked tree. No tests/app run. |
| Responsive UX | viewport meta, flex wrapping, auto-fill grids and <=768px CSS rules. Source evidence only: no live mobile or accessibility verification. |
| Dependencies / cost | Local mode needs downloaded OCR models plus Ollama/model compute/RAM; no metered API requirement after setup. Cloud mode uses Paddle API and Gemini; no current prices verified. CDN dependencies preclude first-load offline UI. Model weights/terms require separate review (Gemma terms are separate from application MIT). Python imports dotenv/OpenCV/numpy but direct dependency list omits at least python-dotenv; transitive availability not assumed. |

## Borrow / reject

**Inference:** borrow the conceptual editable rate breakdown, proportional-charge visibility, correction/assignment workflow and separated OCR backend. Independently implement with integer minor units, explicit line-total/unit-price semantics and printed receipt reconciliation. Reuse of selected MIT source remains possible with notices and dependency audit, but offers little advantage here.

Reject silent demo substitution, non-ASCII stripping, evidence-dropping OCR normalization, permanent raw receipt logs, hard-coded endpoint and independent rounding. This repository does not validate a deterministic-parser-plus-confidence-fallback hypothesis: it requires model parsing on every receipt.

## Unresolved / limits

No OCR accuracy/latency or Malaysian coverage measurement; sample receipt images are not a benchmark and fixture consent/rights were not audited. No cloud/model calls or dependencies installed. Local OCR API result-shape compatibility and startup model memory on intended hardware remain unverified. Current actual SST applicability must be derived from receipts/user review, not this example's percentages.
