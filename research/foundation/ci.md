# Minimal Python CI and cost gate

Accessed **2026-10-17**. Scope: repository foundation only; no workflow or account setting was changed by this investigation. The orchestrator owns activation after reviewing the cost gate.

**Activation update:** the owner explicitly confirmed on2026-10-17 that included Actions minutes remain and no valid payment method is attached. This is owner-supplied account evidence, not an authenticated billing API measurement. Combined with the documented blocking behavior below, the orchestrator passes the no-extra-spend gate for this standard-runner workflow. No billing setting, payment method, paid budget or larger runner is enabled. Remaining usage can change; quota exhaustion must fail visibly rather than purchase usage or skip tests.

## Verified facts

- The repository's documented command is `python -m unittest discover -s tests -v`. The accepted boundary has60 tests, including actual10,000 durable transactions, independent connections, reopen/recovery, rollback, replay/revocation and credential-leak checks. Its recorded local run used Python3.14.6 / SQLite3.50.4 and took195.536 seconds; that does not predict hosted Linux timing. Sources: [README](../../README.md), [acceptance](../phase-3/authority-acceptance.md), `tests/test_authority_security.py:183`.
- Current official releases inspected: [`actions/checkout` v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1), commit [`3d3c42e5aac5ba805825da76410c181273ba90b1`](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1); [`actions/setup-python` v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0), commit [`5fda3b95a4ea91299a34e894583c3862153e4b97`](https://github.com/actions/setup-python/commit/5fda3b95a4ea91299a34e894583c3862153e4b97). These are release-page links to commits in the official repositories, not inferred historical pins.
- Their pinned [`checkout/action.yml`](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml) and [`setup-python/action.yml`](https://github.com/actions/setup-python/blob/5fda3b95a4ea91299a34e894583c3862153e4b97/action.yml) use Node24. Checkout defaults to the event ref/SHA and persists credentials unless explicitly disabled. Setup Python defaults to no dependency cache; its [pinned README](https://github.com/actions/setup-python/blob/5fda3b95a4ea91299a34e894583c3862153e4b97/README.md) requires runner2.327.1+ and recommends selecting Python explicitly.
- GitHub's [secure-use reference](https://docs.github.com/en/actions/reference/security/secure-use) recommends least permissions, verified official full-SHA references and review of action source. It identifies `pull_request_target`/`workflow_run` plus untrusted checkout as dangerous. The proposed workflow uses neither privileged trigger. Manifest/release/source inspection here is bounded; it is not a complete audit of bundled JavaScript or every transitive dependency.
- GitHub's [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) includes2,000 standard-runner minutes/month for GitHub Free personal accounts,3,000 for Pro. Quota is shared at owner-account level, resets each cycle, and private-repository excess can be billed. Without a valid payment method, exhaustion blocks usage. Larger runners always cost money. Current standard Linux2-core excess price is US$0.006/minute; no excess expenditure is authorized here. The workflow creates no Actions caches/artifacts, avoiding those additional storage dependencies; native logs are not uploaded artifacts.
- A configured budget is not necessarily a hard stop. [Setup guidance](https://docs.github.com/en/billing/how-tos/set-up-budgets) requires enabling **Stop usage when budget limit is reached** where available; alerts alone allow continued spending. [Budget concepts](https://docs.github.com/en/billing/concepts/budgets-and-alerts) define scopes and warn that new budgets count usage only from creation onward, so prior-cycle-to-date expenditure can remain outside the new budget's accounting.

Context7 was used first: resolved GitHub Actions to `/websites/github_en_actions`, then queried permissions, full-SHA action references, triggers, Python configuration and concurrency. Direct official sources above supply release and billing facts that the returned examples did not establish.

## Recommended minimal workflow (proposal, not activation)

```yaml
name: Python tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: python-tests-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  tests:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: '3.14'
          allow-prereleases: false
      - name: Runtime versions
        run: python -c "import sys, sqlite3; print(sys.version); print(sqlite3.sqlite_version)"
      - name: All calculator, authority and security tests
        run: python -m unittest discover -s tests -v
```

**Conclusions:** one standard ephemeral Linux VM and stable CPython3.14 minimize complexity and quota consumption while testing SQLite portability beyond the Windows local environment. Twenty minutes is a generous initial bound, not permission to truncate the suite; timeout is failure. Do not add test selection, path filters, `continue-on-error`, conditional skips or a patched quota limit. Normal discovery includes every current security/adversarial test. No dependency installation is needed for this stdlib suite. No user-supplied secret, cloud permission, upload, cache, deployment or listener is needed. The private checkout still uses GitHub's ephemeral read-only automatic token internally; “secret-free” means no supplied repository/account credentials, not absence of all platform authentication. Do not echo environment variables or credentials.

Concurrent stale runs may be cancelled; this is not acceptance evidence for the cancelled revision. Require a completed passing run of the final revision. PR checks use the default merge ref to exercise integration. A successful workflow is not itself branch protection; no protection/account configuration is changed implicitly.

## Unresolved account facts and activation gate

**Unresolved:** current owner plan, actual remaining included minutes, existing other-repository consumption, valid payment-method status, applicable Actions product/SKU/repository budget settings, and whether a zero-dollar hard stop is already effective. Public documentation establishes none of these for KAIYI7. No authenticated billing endpoint/settings view was available to this bounded investigation; no claim of available quota or a safe default is justified.

**Gate: CONDITIONAL PASS for the workflow design; activation blocked pending account evidence.** Before adding a runnable workflow to a pushed branch/PR, establish either (a) no valid payment method, so documented quota blocking applies; or (b) an effective applicable zero-extra-spend hard stop and enough included usage for the run. A small timeout and shared concurrency reduce consumption but do not enforce a billing ceiling. Do not presume a new zero-dollar budget is supported or already applied merely because the generic budget documentation describes hard stops. Do not change budgets, add payment methods, register a self-hosted runner or authorize excess charges to resolve this gate.

If the orchestrator cannot obtain read-only account evidence, persist the prepared configuration outside `.github/workflows/` and request only the specific billing/account confirmation required by the user's spend constraint. Continue unrelated authorized merge/tag, namespace evaluation and bounded identity planning. If quota is exhausted, defer hosted execution or use the existing local full-suite evidence; never weaken tests to claim CI success. The first real hosted result must separately validate runtime compatibility and actual duration.
