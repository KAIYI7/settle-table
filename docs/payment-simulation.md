# Optional allocation authorization simulation

After finalization, an organizer can explicitly simulate authorization of one active
participant's accepted consumption amount. This is an authorization-only simulation:
no money moves and consumption, contributions, reimbursement and settlement remain
unchanged. A managed diner does not need a session to be an organizer's target.
An active diner can read only their own simulation. Only organizers can initiate.

The feature is disabled by default. To configure a supervised local demonstration,
set these server-process variables using private configuration outside source control:

| Variable | Meaning |
| --- | --- |
| `SETTLETABLE_KAIPAY_ENABLED` | `1` to enable; absent or `0` disables |
| `SETTLETABLE_KAIPAY_BASE_URL` | Fixed KaiPay origin, without path/query/user information |
| `SETTLETABLE_KAIPAY_CREDENTIAL` | Narrow integration bearer credential provisioned by the operator |
| `SETTLETABLE_KAIPAY_INTEGRATION_ID` | Stable UUID of the KaiPay integration binding |
| `SETTLETABLE_KAIPAY_NAMESPACE` | Stable installation UUID, retained with backups |

Enabled but missing or malformed configuration fails startup. Configuration is read
once at startup. It creates no account or credential. Retain the namespace, binding,
SQLite sidecar rows and corresponding KaiPay payment history together; never change
them to bypass a conflict or recreate a payment after lost history. Disable the
feature and investigate a restore inconsistency. Source publication does not enable
the feature, start a server or authorize public hosting.

HTTP is accepted only on loopback. Every off-host destination requires HTTPS with
normal certificate and hostname verification. DNS is resolved and pinned at client
startup; restart applies an operator destination change. Requests use direct sockets,
ignore proxy environment variables, do not follow redirects and do not forward
cookies, participant credentials, names, receipt content or Notion credentials.

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

There are no automatic PUT retries. Refresh status after uncertainty; an explicit
organizer retry preserves the same reference and amount. If no status check has
confirmed a missing reference, that retry first performs GET and returns. A later
explicit retry may repeat the identical PUT. GET 404 is never evidence of definitive
rejection. Retained payment identity and monotonically increasing versions prevent
stale responses from overwriting newer observations; equal-version conflicts fail
closed. Manual refresh can detect unsupported changes after a terminal observation.

The client permits four simultaneous requests, a two-second connect timeout, a
five-second whole-request deadline and an 8 KiB response limit. Truncated responses,
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
