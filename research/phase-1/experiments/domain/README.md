# Disposable dining-domain experiment

This folder contains a Python standard-library scenario runner and reproducible evidence. It is not production application code or a production test suite. No installed package, database, external service or credentials are required.

```powershell
python research/phase-1/experiments/domain/validate_domain.py --output research/phase-1/experiments/domain/results.json --seed 20261016 --trials 3000
```

Run with Python assertions enabled (ordinary `python`, **not `python -O`**). The runner exits on a failed assertion or unexpected error; only a fully successful run writes a new results file. Money is integer sen and weights/quantities use exact `Fraction`; no monetary float or vendor API is used.

- `validate_domain.py`: independent experimental arithmetic/scenario code; not copied from reference applications.
- `results.json`: 67 concrete cases and seeded randomized assertion results; each policy alternative is labeled as such.
- `verification.json`: coordinator-run script/result hashes and execution record.
- [Findings and limits](../../domain-model.md): interpretations, sources, corrected subtotal assumption and unresolved product choices.

Machine-readable money in concrete scenarios is integer sen; the large randomized maximum is a decimal string to avoid loss in JSON consumers that coerce numbers to binary float. This stress bound is not a proposed production limit. The actual historical image remains under the OCR workstream; it is not copied or redistributed here. Its transcribed arithmetic/source hash is recorded in the concrete case.
