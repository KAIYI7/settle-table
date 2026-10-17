# Disposable real-browser collaboration probe

**Never deploy this fixture.** It uses public synthetic bearer tokens, a fixture revocation endpoint and in-memory state. It is neither application scaffolding nor a secure invitation implementation. It imports the independently written Phase 1 simulation rather than copying reference-project source.

Question: do role/revision/quantity/idempotency rules behave as expected when two independent browser sessions make actual HTTP requests? The transport question requires a server, overriding the prototype skill's usual single-file/no-server preference. User-required persistent benchmark evidence takes precedence over the skill's throwaway-branch capture default.

From the project root, start a **fresh** server for every run:

```powershell
python research/phase-2/experiments/collaboration/server.py
```

Then run with an available Playwright installation and installed Chromium:

```powershell
node research/phase-2/experiments/collaboration/run-browser.cjs
```

Provide Node and Playwright1.62.1 with its matching Chromium in your chosen environment; if Playwright is outside Node's module search path, set `NODE_PATH` to that environment's module directory. The recorded run used a host-bundled runtime discovered through `load_workspace_dependencies`, not a globally installed dependency. Those private bundled paths are not portable prerequisites. The execution sandbox blocked loopback sockets; the server and runner succeeded with sandbox escalation, remaining bound to `127.0.0.1:8766` only. Do not widen the bind address to work around browser connectivity.

Manual reproduction: open `http://127.0.0.1:8766/?actor=A` and `?actor=B`, click Race and replay in both, Organizer checks in A, Reconnect in B, Revoke in A, Revoked replay in B. State/checks remain visible. The runner uses two isolated Chromium contexts, stronger session separation than two ordinary same-profile tabs; both are still on one machine and engine.

`results.json` contains browser assertions, raw response evidence, race-arrival timestamps, final state and source hashes. Stop the server with Ctrl+C. Restart discards all state. Browser/session fixtures are synthetic only, and no application source should import this directory.
