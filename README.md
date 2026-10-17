# SettleTable

A receipt-based dining bill splitter with live diner collaboration, local/self-hosted extraction and optional downstream Notion reporting. The project is being built in small reviewed slices; the complete application is not available yet.

Start with [project status](PROJECT_STATUS.md), [agent operating rules](AGENTS.md) and the [research index](research/README.md). The main Codex agent manages evidence-based phase transitions under [governance](docs/agents/governance.md).

Repository: [KAIYI7/settle-table](https://github.com/KAIYI7/settle-table). The local directory may have any name. The accepted calculator's Python namespace `tabwise` and versioned rounding domain remain unchanged to preserve its reviewed contract.

The checkout contains sanitized research, aggregate results and source metadata. Receipt images/text, models, environments, local databases and private Notion locators are excluded. Read [publication and reproducibility notes](research/publishing/README.md) before reproducing experiments or restoring the locally installed Impeccable skill.

The first production module is a Python standard-library financial calculator, separate from disposable research experiments. Run its public-interface tests from this directory:

```powershell
python -m unittest discover -s tests -v
```

See the [bounded specification](research/phase-2/mvp-specification.md) and [implementation record](research/phase-3/README.md). Passing calculation tests does not establish identity, human verification, live collaboration, OCR accuracy or Notion delivery. Those capabilities have their own acceptance gates.
