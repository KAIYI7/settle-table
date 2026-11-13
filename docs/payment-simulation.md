# Optional allocation authorization simulation

After finalization, an organizer can explicitly simulate authorization of one active
participant's accepted consumption amount. This is an authorization-only simulation:
no money moves and consumption, contributions, reimbursement and settlement remain
unchanged. A managed diner does not need a session to be an organizer's target.
An active diner can read only their own simulation. Only organizers can initiate.
KaiPay's `AUTHORIZED` status updates the simulation observation only. Actual
contributions, restaurant funding, reimbursements, peer settlements, balances,
and payment completion are governed by the existing meal workflows.

The [INTEGRATION-06 acceptance record](agents/phase-transitions.md#2026-11-12--settletable-kaipay-integration-06)
documents the bounded cross-application synthetic demonstration.

The feature is disabled by default. The SettleTable–KaiPay deployment is reserved
for supervised, on-demand portfolio demonstrations on isolated synthetic data.
Keep the integration disabled in SettleTable's primary real-data deployment and
leave the dedicated KaiPay connector stopped between demonstrations.

| Variable | Meaning |
| --- | --- |
| `SETTLETABLE_KAIPAY_ENABLED` | `1` to enable; absent or `0` disables |
| `SETTLETABLE_KAIPAY_BASE_URL` | Fixed KaiPay origin, without path/query/user information |
| `SETTLETABLE_KAIPAY_INTEGRATION_ID` | Stable UUID of the KaiPay integration binding |
| `SETTLETABLE_KAIPAY_NAMESPACE` | Stable installation UUID, retained with backups |
| `SETTLETABLE_KAIPAY_CREDENTIALS_FILE` | Private JSON credential file readable by the app process |

Enabled but missing or malformed configuration fails startup. Configuration is read
once at startup. It creates no account or credential. Retain the namespace, binding,
SQLite sidecar rows and corresponding KaiPay payment history together; never change
them to bypass a conflict or recreate a payment after lost history. Disable the
feature and investigate a restore inconsistency. Disable simulation before rolling
back to a version that lacks durable dispatch and checked-absence handling.

## Docker and operator activation

Keep the feature disabled in the primary real-data deployment. Use an approved
synthetic SettleTable dataset and the matching retained KaiPay synthetic binding.
Use the existing independent KaiPay runbook for loopback TLS, private runtime and
its supervised connector window. Check that the retained Access credentials are
valid and scoped to the KaiPay API, and preserve the binding and installation IDs.

1. Outside the repository and Docker build context, create a JSON file with string
   keys `credential` (the KaiPay bearer value without `Bearer `), `access_client_id`
   and `access_client_secret`. Supply both Access values for the protected KaiPay
   machine endpoint.
   Restrict the host file to the operator and Docker file-sharing identity. The
   app runs as UID 10001 and must be able to read the mounted file.
2. Set the nonsecret options from `deploy/env.template` in the synthetic deployment's
   private Compose configuration. Set `SETTLETABLE_KAIPAY_CREDENTIALS_HOST_FILE` to
   the file's absolute host path. Use `-f docker-compose.yml -f docker-compose.kaipay.yml`
   together with the selected synthetic Compose configuration. This override mounts
   the file read-only in SettleTable only. Docker metadata includes its path.
   Keep credential values out of Compose environment variables, shell arguments,
   browser code and logs. Leave Cloudflare Access on KaiPay's machine hostname only.
3. Recreate only the intended SettleTable app service to load settings or changed
   credentials. Check its local health and confirm the organizer's simulation
   control. Enable the KaiPay connector only during a separately authorized window.
   To disable simulation, set `SETTLETABLE_KAIPAY_ENABLED=0` and recreate the app.
   Keep both applications' retained data and their independent tunnel controls.

For a native loopback demo, the existing `SETTLETABLE_KAIPAY_CREDENTIAL` environment
variable remains supported. A native HTTPS process can also provide the pair via
`SETTLETABLE_KAIPAY_ACCESS_CLIENT_ID` and `SETTLETABLE_KAIPAY_ACCESS_CLIENT_SECRET`.
Use either a file or environment credentials. HTTP loopback sends only the bearer.

HTTP is accepted only on loopback. Every off-host destination requires HTTPS with
normal certificate and hostname verification. DNS resolves on demand with a bounded
wait. Address fallback ends before any HTTP bytes are sent. Requests use direct
sockets, ignore proxy environment variables, do not follow redirects and do not
forward cookies, participant credentials, names, receipt content or Notion credentials.
GET is bodyless and has no Content-Type header.

## Local HTTP interface

`POST /api/meals/{meal}/participants/{participant}/payment-simulation` accepts an empty
body or `{}`. Existing session, action-header and same-origin checks apply. No caller
amount, merchant, customer, callback or reference is accepted. The corresponding GET
allows the current organizer or participant self and never creates an intent or
dispatches PUT. Missing local intent returns `exists: false` and `NOT_SENT` (or
`NO_PAYMENT_NEEDED` for zero consumption) without remote I/O.

Successful responses use `{"ok":true,"payment_simulation":{...}}` with a local
`state`, `exists`, opaque `clientReference`, immutable finalization `basis`, optional
`paymentId`, `paymentVersion`, `paymentStatus`, `paymentUpdatedAt`, local `observedAt`
and `retryAfter`. Pending or uncertain results may return 202; this does not establish
remote acceptance. Responses are not cached. The browser receives no machine secret.

The basis is the unique accepted Finalize actor/command and original committed result,
including its revision, financial revision, SHA-256 digest, exact participant ID and
accepted integer sen amount. A UUIDv5 reference derives from the installation namespace
and compact ASCII JSON array `["allocation-authorization-v1",mealId,finalizeActorId,
finalizeCommandId,participantId]`. Amount, current revision, credentials and retry count
never enter the reference. Missing, ambiguous, malformed or conflicting retained
basis fails closed. Accepted command/result bytes are preserved.

An additive `payment_simulations` SQLite table freezes the nonfinancial intent in a
short authorized transaction. The server releases the write lock before contacting
KaiPay and rechecks current access before dispatch and before returning the result.
Each action sends at most one request: PUT or GET to KaiPay's
`/v1/integrations/payments/{clientReference}`. A request contains only `amountCents`
and literal `MYR`. Zero consumption never creates a remote payment.

## Outcomes and recovery

`AUTHORIZED`, `DECLINED` and definitive `FAILED` are distinct terminal simulation
outcomes. `CREATED` and `PROCESSING` map to `PENDING`; an unresolved timeout can remain
pending indefinitely. A transport failure is `REQUEST_UNKNOWN` or `UNAVAILABLE`,
never definitive payment failure. A reference conflict is `CONFLICT`. Unsupported
remote states, including later capture/refund states, become `UNEXPECTED_STATUS` and
stop automatic actions. No capture, refund, journal or settlement request exists here.

Before PUT, SettleTable durably records possible dispatch and consumes any prior
checked absence. After interruption or restart, the same intent stays uncertain
until reconciled. Refresh status, or let the next organizer retry perform GET first.
Only a well-framed KaiPay JSON `404 NOT_FOUND` for that exact reference permits a
subsequent explicit identical PUT. An unavailable or invalid check leaves the
intent uncertain. Older unresolved sidecar rows require a fresh check. Retained
payment identity and monotonically increasing versions prevent
stale responses from overwriting newer observations; equal-version conflicts fail
closed. Manual refresh can detect unsupported changes after a terminal observation.

One simulation can use the network at a time per WSGI process. The configured
single worker keeps its other threads available for meal work. Requests use a
two-second DNS/connect budget, a five-second whole-request deadline and an 8 KiB
response limit. Truncated responses,
invalid types, mismatched identities/amounts, duplicate fields and invalid content
fail closed. HTTP 429 imposes a shared bounded Retry-After cooldown. HTTP 400/401/403
suspends further wire attempts until operator correction and process reload/restart.
These client admission controls are process-local and reset on restart.

Visible polling uses read-only GET at elapsed 2/5/10/30/60/90/120 seconds, then stops.
It pauses while the page is hidden. Manual refresh or revisiting can resume reads.
No background worker promises progress while users are absent. Before any real
deployment, rehearse stopped-writer backup/restore; old binaries tolerate the extra
table, which must not be destructively removed to reverse feature enablement.

Run focused synthetic tests with `python -m unittest discover -s tests -p
test_payment_simulation.py -v`, the full suite with `python -m unittest discover -s
tests -v`, and browser regressions with `node tools/e2e_browser_test.mjs`.
