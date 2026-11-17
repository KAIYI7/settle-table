# Experimental checkout demo (synthetic)

After finalization, an organizer can ask an operator-run experimental checkout
bridge to create one **synthetic, nonpayable** demo checkout for a current
suggested transfer whose receiver is the organizer. SettleTable then only
displays the bridge's outcome. It is display only: no contribution, pending
report or transfer is ever written, accepted command and result bytes are not
changed, and suggested transfers and balances are unchanged by every outcome.
SettleTable's own transfer confirmation flow is separate and unaffected.

The organizer issues the payer code from the bridge's own receiver page and
reviews and confirms the demo there. SettleTable never receives or stores a payer
code, never reviews, verifies or confirms anything in the bridge, and receives no
callback from it. Only the organizer can request or read the demo status.

The feature is disabled by default and is separate from the
[allocation authorization simulation](payment-simulation.md): it has its own
configuration, namespace, client, wire slot and suspension state, and
`settletable/payment_simulation.py` is unchanged.

## Configuration

Set these server-process variables from private configuration outside source
control. Enabled but missing or malformed configuration fails startup.
Configuration is read once at startup and creates no account or credential.

| Variable | Meaning |
| --- | --- |
| `SETTLETABLE_CHECKOUT_DEMO_ENABLED` | `1` to enable; absent or `0` disables |
| `SETTLETABLE_CHECKOUT_DEMO_BASE_URL` | Fixed bridge origin without path, query or user information |
| `SETTLETABLE_CHECKOUT_DEMO_NAMESPACE` | Stable installation UUID for this feature, retained with backups. It must differ from `SETTLETABLE_KAIPAY_NAMESPACE`. |
| `SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL` | Native mode only: the narrow bridge integration credential (`[A-Za-z0-9_-]{32,256}`) |
| `SETTLETABLE_CHECKOUT_DEMO_CREDENTIALS_FILE` | Container mode instead of the variable above: a read-only mounted JSON file `{"credential":"..."}` |
| `SETTLETABLE_CHECKOUT_DEMO_CA_FILE` | Optional, HTTPS only: a trust anchor for this client only |

Exactly one of `_CREDENTIAL` and `_CREDENTIALS_FILE` must be set. HTTP is
accepted only when every resolved address is loopback; the supported demo is a
native SettleTable process calling `http://127.0.0.1:28082`. Any other
destination needs HTTPS with certificate and hostname verification, using
`_CA_FILE` through `ssl.create_default_context(cafile=...)` for this client
only. `SSL_CERT_FILE` is never set or required. DNS is resolved and pinned at
startup; each request tries the pinned addresses in order within its deadline
(so `localhost` resolving to `::1` and `127.0.0.1` reaches a bridge bound only
to `127.0.0.1`, at the cost of up to 2 s per request; prefer the literal
`http://127.0.0.1:28082`). Without `_CA_FILE`, HTTPS uses the default trust store. Requests use direct sockets, ignore proxy environment variables, do not
follow redirects and send no cookies, names, receipt content or participant
credentials. No Compose override ships with this feature; a container
deployment would need a separately reviewed, opt-in, read-only credential mount.

For a native demo, use a fresh synthetic database and set
`SETTLETABLE_DATA_VOLUME=settletable_synthetic_data`, and use a port the Stage 1
container does not bind.

## Local HTTP interface

`GET /api/meals/{meal}/checkout-demo` returns the latest intent, the eligible
suggestions and the last check. It sends at most one bridge GET and never a PUT.

`POST /api/meals/{meal}/checkout-demo` accepts exactly
`{"sender_id": "...", "amount_sen": N}`. The pair must equal a current
suggestion whose receiver is the requesting organizer; the amount is a consent
check against the recomputed suggestion, never a caller-chosen amount. Existing
session, action-header and same-origin checks apply.

Responses are `{"ok":true,"checkout_demo":{...}}` with `intent`, `eligible`,
`lastCheck`, `retryAfter` and `synthetic: true`. 202 means the outcome is
uncertain (`REQUEST_UNKNOWN`) or another check was in progress (`BUSY`).
Errors: `checkout_demo_stale` (409), `checkout_demo_active` (409),
`checkout_demo_already_confirmed` (409), `checkout_demo_conflict` (409),
`forbidden` (403) and `checkout_demo_disabled` (503, after authentication).

The meal snapshot carries only a static organizer-only `checkout_demo_enabled`
flag. Demo status is never read on the 3 s snapshot poll. The browser reads the
dedicated endpoint at elapsed 2/5/10/30/60/90/120 seconds while the intent is
open, then stops; it pauses while the page is hidden. It also reads it once when
a snapshot shows that the finalized meal's suggested transfers changed (a
contribution or confirmed transfer recorded after finalization), so the eligible
list and the stale flag stay current. If a read is still in flight at that point,
one more read follows it; while the page is hidden, that read waits until the page
is visible again. These reads do not restart the polling schedule.

## Intent, reference and eligibility

An additive `checkout_demos` SQLite table freezes, in one `BEGIN IMMEDIATE`
transaction, the meal, the unique accepted Finalize actor and command, the
sender, receiver and amount in sen, the attempt number, the reference, the local
state and the possible-dispatch count. The write lock is released before the
bridge is contacted, and organizer access is checked again before dispatch.

The reference is a UUIDv5 of the feature namespace and the compact ASCII JSON
array `["checkout-demo-v1",mealId,finalizeActorId,finalizeCommandId,senderId,
receiverId,attempt]`. The amount never enters it. Every read recomputes each
stored reference and checks it against the current Finalize basis; any
disagreement fails closed (`checkout_demo_conflict`).

Eligibility:

- the meal is finalized and the caller is the organizer;
- the target is a current suggestion (recomputed with `compute_settlement` from
  active contributions and confirmed transfers) whose receiver is the organizer;
- at most one open intent per meal. `NOT_CREATED`, `CONFLICT`, `EXPIRED` and
  `MANUALLY_CONFIRMED` count as finished, so a new attempt may follow;
- after `MANUALLY_CONFIRMED`, the same unchanged suggestion (sender, receiver,
  amount) can never be requested again.

If the recomputed suggestion no longer matches an intent, the intent is shown as
**stale — balances changed** and no further PUT is sent for it. Pending reports
and unrelated transfers do not make it stale.

## Wire contract (bridge integration API)

Each action sends at most one request with `Authorization: Bearer <credential>`:

- `PUT /api/integrations/checkouts/{reference}` with body exactly
  `{"amountMinor":N,"currency":"MYR"}`.
- `GET /api/integrations/checkouts/{reference}`.

A success is `200` (or `201` for a PUT that created the checkout) with
`application/json` and exactly these fields: `reference`, `checkoutId`,
`amountMinor`, `status`, `evidence`, `createdAt`, `expiresAt`,
`reviewExpiresAt` (nullable) and `revision`. Errors are `{"error":"CODE"}`.

| Bridge answer | Local outcome |
| --- | --- |
| PUT 200/201, valid body | Checkout bound; status mapped below |
| PUT 409 `SAME_AMOUNT_HELD` | `NOT_CREATED`: "Another demo checkout holds this amount. It can last up to 40 minutes." |
| PUT 409 `REFERENCE_CONFLICT` | `CONFLICT`; automatic actions stop |
| PUT timeout, 503 `STORE_UNAVAILABLE`, any other answer | `REQUEST_UNKNOWN`; the next explicit action is a GET |
| GET 404 `REFERENCE_NOT_FOUND`, no checkout ever bound | Checked absence: `NOT_CREATED`; each explicit organizer action may send one identical re-PUT (same reference) while the suggestion is unchanged |
| GET 404 `REFERENCE_NOT_FOUND`, checkout bound | Snapshot loss: shown `UNAVAILABLE` until the operator decides; never recreated |
| Other 404s, malformed bodies, transport failure on GET | `UNAVAILABLE` for that check; the stored state is kept |
| A different `checkoutId`, amount, reference or `createdAt` | `CONFLICT` |
| 400/401/403 | Client suspended until operator correction and restart |
| 429 | Shared bounded `Retry-After` cooldown (1–120 s) |

For a PUT answered 400/401/403/429 the response shows `UNAVAILABLE` for that
check while the stored state stays `REQUEST_UNKNOWN`, so the next action is a
GET. While the client is suspended or cooling down, a request freezes no new
intent and sends nothing.

A lower `revision` than the stored one is ignored. An equal revision with
different content fails closed. A higher revision with no visible change is a
new observation. A finished bridge status (`MANUALLY_CONFIRMED`, `EXPIRED`,
`REVIEW_EXPIRED`) that later changes becomes `UNEXPECTED_STATUS`.

Display mapping (evidence is checked first; any evidence other than `NONE` or
`SYNTHETIC`, including `NOTIFICATION_UNVERIFIED`, is `UNEXPECTED_STATUS`):

| Bridge status and evidence | SettleTable shows |
| --- | --- |
| `AWAITING_PAYMENT`, `NONE` | Awaiting synthetic evidence |
| `PAYMENT_DETECTED` or `AWAITING_VERIFICATION`, `SYNTHETIC` | Synthetic evidence detected — awaiting organizer review |
| `AMBIGUOUS`, `NONE` or `SYNTHETIC` | Needs organizer review in the demo checkout |
| `MANUALLY_CONFIRMED`, `SYNTHETIC` | Organizer marked the synthetic demo checkout confirmed — no money moved; balance unchanged |
| `EXPIRED` or `REVIEW_EXPIRED`, `NONE` or `SYNTHETIC` | Expired — you may request again |
| any other combination | Unexpected demo checkout status — automatic actions stopped |

`CONFLICT` and `UNEXPECTED_STATUS` are latched: no further bridge request is sent
for that intent.

**Known limitation — operator recovery.** `UNEXPECTED_STATUS` is latched but not
finished, and a snapshot-loss `UNAVAILABLE` stays open until the bridge returns
the same checkout at the same or a higher revision. A restored *older* bridge
snapshot (lower revision) is therefore ignored and the intent stays
`UNAVAILABLE`. In both cases the demo for that meal stays blocked; the meal's own
balances, reports and transfers are unaffected. No in-app or scripted operator
override ships: investigate, then run the demo with a fresh synthetic meal. Any
manual database change would need its own reviewed procedure. After 50 attempts
a meal also refuses further demo requests (`resource_limit`).

The client allows a two-second connect timeout, a five-second
whole-request deadline and an 8 KiB response limit. Admission controls are
process-local and reset on restart.

## Tests

```bash
python -m unittest discover -s tests -p test_checkout_demo.py -v
```

```bash
node tools/verify_checkout_demo.mjs
```

Both run against `tests/checkout_demo_stub.py`, an in-process stub that follows
the bridge contract above. They use disposable random credentials and contact
no real bridge.
