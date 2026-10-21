# SettleTable

A receipt-based dining bill splitter with live diner collaboration, local/self-hosted extraction and optional downstream Notion reporting. The project is being built in small reviewed slices; the complete application is not available yet.

Start with [project status](PROJECT_STATUS.md), [agent operating rules](AGENTS.md) and the [research index](research/README.md). The main Codex agent manages evidence-based phase transitions under [governance](docs/agents/governance.md).

Repository: [KAIYI7/settle-table](https://github.com/KAIYI7/settle-table). The local directory may have any name. Current Python imports use `settletable`. The historical versioned allocation domain `tabwise-apportion-v1` remains unchanged to preserve deterministic financial results; the package rename does not migrate persisted SQLite state or accepted replay contracts.

The checkout contains sanitized research, aggregate results and source metadata. Receipt images/text, models, environments, local databases and private Notion locators are excluded. Read [publication and reproducibility notes](research/publishing/README.md) before reproducing experiments or restoring the locally installed Impeccable skill.

The production modules are a Python standard-library financial calculator, a bounded local SQLite draft authority, a same-origin WSGI transport adapter, a zero-dependency browser client, and an optional decoupled Notion exporter, separate from disposable research experiments.

### Running Public-Interface Tests

Run the full automated test suite from this directory:

```powershell
python -m unittest discover -s tests -v
```

The suite includes real durable SQLite command transactions, mock OCR extraction, and bounded Notion export tests. Disposable databases use ignored `.local/tests/`.

To run the automated real browser journey test (requires Chrome and Node.js):

```powershell
node tools/e2e_browser_test.mjs
```

### Running the Local Browser Demo

Launch the local development and demonstration server with deterministic mock OCR and mock Notion clients:

```powershell
python tools/run_demo.py --host 127.0.0.1 --port 8000 --mock-ocr --mock-notion
```

Open `http://127.0.0.1:8000` in your web browser.

**Runner Behavior & Credential Security**:
- The runner binds to the local interface and prints the server origin and database path.
- The runner **never prints organizer credentials or session links to stdout**. Credentials are issued directly to the browser via host-only secure cookies (`settletable_session`), and diner invitations are created and copied directly within the organizer's web UI.
- OCR inference runs locally on the host server (RapidOCR CPU ONNX), not on-device inside phone browsers.
- See the complete [User Acceptance Testing (UAT) Handover Guide](docs/uat-handover.md) for step-by-step walkthroughs, realistic test meals, failure/recovery scenarios, and known limitations.
