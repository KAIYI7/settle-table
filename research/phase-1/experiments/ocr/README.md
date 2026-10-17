# Disposable OCR experiment

No production pipeline/server/UI. No hosted image calls. All normalized money is integer sen; unknowns remain null. Read [findings](../../ocr-validation.md) before interpreting scores.

## Recorded environment

Python3.12.14 isolated `.venv`, Node22.20.0, RapidOCR3.10.0/ORT1.31.0, PaddleOCR3.7.0/Paddle3.3.1, Tesseract.js7.0.0. Python freeze and npm lock pin this experimental environment. Models/images/caches are local ignored assets, not cleared distributable fixtures. Do not use the system Python3.14 for these recorded ML wheel versions.

## Reproduce existing corpus

**Published checkout limitation:** the following commands describe the original local experiment. `prepare.py`, `data/corpus.json`, `data/truth.json`, receipt images and raw per-receipt outputs are intentionally withheld pending original-input rights clearance. They are not supplied by this checkout. Public `data/corpus-manifest.json` retains source IDs/revisions and image hashes; `results/metrics.json` retains aggregate scores. To reproduce the full historical run, independently provision permitted exact inputs and reviewed labels; do not treat a fresh clone as a complete fixture pack. Source hashes in verification records describe prepublication originals, not newly executed OCR.

From the project root, with the experiment venv/dependencies/models already available:

```powershell
.\research\phase-1\experiments\ocr\.venv\Scripts\python.exe research/phase-1/experiments/ocr/prepare.py
.\research\phase-1\experiments\ocr\.venv\Scripts\python.exe research/phase-1/experiments/ocr/add_perspective.py
.\research\phase-1\experiments\ocr\.venv\Scripts\python.exe research/phase-1/experiments/ocr/run_local.py rapidocr --passes 2
.\research\phase-1\experiments\ocr\.venv\Scripts\python.exe research/phase-1/experiments/ocr/run_local.py paddleocr --passes 2
node research/phase-1/experiments/ocr/run_tesseract.cjs --offline
python research/phase-1/experiments/ocr/parse_evaluate.py
```

Run engines sequentially. `prepare.py` freezes agent-transcribed labels plus three synthetic cases; `add_perspective.py` adds the fourth. Do not tune the frozen parser from final scores without recording a new version and keeping the failed baseline. `--offline` selects locally cached traineddata, not an OS firewall test. First provisioning may download models/language assets; it never sends receipt images.

If building this environment afresh, use a Python3.12 venv here, install the recorded `requirements-frozen.txt`, and restore experiment-local npm dependencies from `package-lock.json` with install scripts disabled. The recorded bundled Python executable is in `.venv/pyvenv.cfg`; paths differ on other machines. Read current official package docs before changing versions; none is an endorsed application dependency.

## Corpus and results

`acquire.py` fetches six public dining examples only and refuses if dataset-server HEAD differs from the recorded revision. Existing `data/images/*.source.json` plus image hashes preserve the actual source; historical re-acquisition may require resolving pinned parquet assets rather than querying a changed dataset server. Do not silently change truth/images.

- `data/corpus.json`: image SHA256, dataset revision and source entities.
- `data/truth.json`: agent visual annotations, uncertainty notes, synthetic values.
- `results/{rapidocr,paddleocr,tesseract}.json`: two passes, raw text/boxes/scores and timings.
- `results/parsed.json`: frozen parser proposals and routing issues.
- `results/metrics.json`: exact positive/absence field denominators, split real/synthetic.
- `verification.json`: script/input/result/model hashes.

No private receipt folder was supplied. Original SROIE rights could not be independently confirmed beyond curator CC-BY-4.0/NOTICE; do not turn this research cache into a product fixture pack. Current source/license URLs and limitations are in the findings document. Local image source JSON can contain temporary download URLs; it is ignored and must not be copied into shared reports.

## Known failed hypotheses

High mean OCR confidence and a matching total did not ensure correct item names/quantities. The intentionally small parser expects some quantity-first rows and mishandles name-before-quantity synthetic rows even when raw text is correct. Scores therefore measure this entire baseline, not intrinsic engine recognition quality. No automatic acceptance or local/cloud LLM recovery was validated. Native phones/browsers remain unmeasured.
