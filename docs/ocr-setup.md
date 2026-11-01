# SettleTable Local OCR Setup Guide

SettleTable features an optional, air-gapped local OCR pipeline designed for offline inference on Malaysian dining receipts. It uses RapidOCR with ONNX Runtime on the server CPU, making zero outbound network calls and transmitting zero private image bytes to third-party hosted vision services.

If OCR dependencies are not installed on the host system, the core SettleTable application functions 100% normally using manual receipt entry, and the OCR upload route cleanly returns HTTP 503 (`ocr_unavailable`).

---

## 1. Prerequisites

- Python 3.10, 3.11, 3.12, 3.13, or 3.14.
- Compatible with Windows (x86_64), macOS (Apple Silicon / Intel), and Linux (x86_64, aarch64).
- No GPU or CUDA required; inference runs efficiently on CPU.

---

## 2. Dedicated Environment Setup

To keep the base SettleTable development environment lightweight and zero-dependency, install OCR packages in a dedicated virtual environment:

### Step 1: Create a dedicated virtual environment
```bash
# On Linux / macOS / Windows PowerShell
python -m venv .venv-ocr
```

### Step 2: Activate the environment
```bash
# Windows PowerShell
.\.venv-ocr\Scripts\Activate.ps1

# Linux / macOS
source .venv-ocr/bin/activate
```

### Step 3: Install the pinned OCR dependencies
```bash
pip install -r requirements-ocr.txt
```

Upon first OCR execution, RapidOCR automatically caches the lightweight PP-OCRv6 ONNX models ($\approx 15-20\text{ MB}$ total) locally into its package directory.

---

## 3. Running with Real Local OCR

Launch the development server using the Python binary from your dedicated environment without the `--mock-ocr` flag:

```bash
# From the repository root (with .venv-ocr active)
python tools/run_demo.py --port 8000 --mock-notion
```

In the browser:
1. Create a meal as Organizer.
2. In the **Local Receipt OCR Scanner** section, upload a clear receipt image (`.png`, `.jpg`, `.webp` $\le 5\text{MB}$).
3. The server processes the image via RapidOCR and displays the **Staged Candidate Receipt Card**.
4. Review, adjust any misrecognitions (using the inline stepper or adjustments editor), and click **Accept & Apply to Receipt**.
5. The mandatory physical bill review and digest sealing (`ReviewReceipt`) remain required before finalization.

---

## 4. Running Without OCR (Deterministic Mock Mode)

For automated test suites, CI pipelines, or systems without native ML wheels:

```bash
python tools/run_demo.py --port 8000 --mock-ocr --mock-notion
```

This uses `MockOcrEngine`, replaying deterministic token fixtures with zero CPU inference overhead.
