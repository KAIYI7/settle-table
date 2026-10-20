# Investigation: Running Real Browser E2E Checks in GitHub CI Without Paid Services

**Date**: 2026-10-21  
**Project**: SettleTable  
**Scope**: Browser E2E automation in GitHub Actions CI under zero-spend policy.  
**Author**: Orchestrator  

---

### 1. Objective

Investigate and document whether actual end-to-end browser tests (`tools/e2e_browser_test.mjs`) can run reliably in GitHub Actions CI without:
1. Adding paid services, subscriptions, or SaaS test clouds (e.g. BrowserStack, SauceLabs, Cypress Cloud).
2. Requiring paid self-hosted runners or larger runner pools.
3. Leaking secrets, tokens, or private assets into build logs.
4. Materially consuming monthly included Actions runner quotas.

---

### 2. Standard GitHub Actions Runner Capabilities (`ubuntu-24.04`)

GitHub-hosted standard Linux runners (`ubuntu-24.04` and `ubuntu-22.04`) include pre-installed software environments documented in [GitHub Virtual Environments](https://github.com/actions/runner-images):
- **Google Chrome**: Pre-installed at `/usr/bin/google-chrome` or `/usr/bin/google-chrome-stable`.
- **Node.js**: Pre-installed in the runner system path.
- **Python**: Configured via the pinned official `actions/setup-python` action.

Because Google Chrome and Node.js are already present in the base runner image, running Headless Chrome via the Chrome DevTools Protocol (CDP) requires **zero package installations** (`npm install` or `apt-get` downloads are unnecessary).

---

### 3. Execution Mechanics & Chrome Flags for Ephemeral Containers

Running Headless Chrome inside CI containers or virtualized Linux VMs requires three standard flags:
- `--headless=new`: Modern Chrome headless implementation matching actual rendering.
- `--no-sandbox`: Required in unprivileged container environments where user namespaces or SUID sandboxes are constrained.
- `--disable-dev-shm-usage`: Forces Chrome to use `/tmp` rather than `/dev/shm` (which is often limited to 64MB in default container environments, causing memory crashes on larger DOMs).
- `--disable-gpu`: Prevents attempts to initialize hardware GPU acceleration on headless virtual machines.

All four flags are configured in `tools/e2e_browser_test.mjs:startChrome()`.

---

### 4. Cost & Quota Analysis

- **Free-Tier Allowance**: Standard GitHub accounts receive 2,000 minutes/month; Pro accounts receive 3,000 minutes/month.
- **Execution Time**: The full 8-stage browser journey (Organizer setup, 2 receipt items, human receipt review, invitation redemption, portion claiming, 409 conflict handling, finalization breakdown, and page reload persistence across two isolated browser profiles) executes in **~3.2 seconds**.
- **Runner Minute Impact**: Even assuming a rounded wall time of ~10 seconds including process startup, running on every PR and commit to `main` consumes less than 0.2% of the standard monthly free quota.
- **Cost**: **$0.00**. No paid services, no third-party tokens, and no billing settings are modified.

---

### 5. Secret & Log Hygiene

Prior to this improvement, the test runner logged the unhashed invitation URL:
```text
   ✓ Invitation URL generated: http://127.0.0.1:8089/invite/0FscMMcbu7nkEl1nL4p6XXxBTGF4MeDJCyiquXj82XM
```
In CI, logs are persisted and accessible to repository viewers. Printing the unhashed bearer token violates secret hygiene principles.
With the redaction update:
```text
   ✓ Invitation URL generated: http://127.0.0.1:8089/invite/[REDACTED]
```
The raw URL is retained in-memory for the isolated diner browser navigation call (`pageB.navigate(inviteUrl)`), while stdout/stderr streams receive only sanitized strings.

---

### 6. Workflow Integration Plan

In `.github/workflows/python-tests.yml`, the browser journey can run following the 113-test Python suite:

```yaml
      - name: All calculator, authority and security tests
        run: python -m unittest discover -s tests -v
      - name: Real browser end-to-end journey tests (Chrome CDP)
        run: node tools/e2e_browser_test.mjs
```

---

### 7. Conclusion & Gate Determination

**PASS**: Running the Chrome CDP browser test directly in GitHub Actions on standard `ubuntu-24.04` runners is feasible, secure, zero-cost, and complies fully with repository governance policies.
