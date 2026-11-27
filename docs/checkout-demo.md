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
| `SETTLETABLE_CHECKOUT_DEMO_OBSERVED_EVIDENCE` | Optional. Exactly `true` selects [observed-evidence mode](#observed-evidence-mode); absent keeps the synthetic demo. Any other value, or setting it while the demo is disabled, fails startup. |
| `SETTLETABLE_CHECKOUT_DEMO_OBSERVED_MULTI` | Optional, off by default. Exactly `true` selects [multi-diner observed mode](#multi-diner-observed-mode); it requires `_OBSERVED_EVIDENCE=true`. Any other value, or setting it without the observed flag, fails startup. Absent, observed mode is unchanged. |

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
open, then stops (in [observed-evidence mode](#observed-evidence-mode) it
continues until the bridge's deadlines; see **Status reads** there); it pauses
while the page is hidden and restarts when the page is visible again. "Refresh
demo status" also restarts it. It also reads it once when
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

## Observed-evidence mode

`SETTLETABLE_CHECKOUT_DEMO_OBSERVED_EVIDENCE=true` is for a bridge started in its
separate observed-evidence integration mode. In that mode the bridge's phone
companion observes the organizer's own wallet notification for one test transfer
between the organizer's own wallets, made by the organizer outside SettleTable.
The bridge does not verify or settle payments, and a notification never proves
settlement, payer identity or intent. Everything above still applies, with these
differences. When the variable is absent, nothing below applies and the behaviour
is the synthetic demo's.

It stays **display only**: no contribution, pending report or transfer is written,
accepted command and result bytes are unchanged, and suggested transfers and
balances are unchanged by every outcome. Any real reimbursement record stays a
separate, manual organizer action.

**Mode check.** Success bodies must carry one extra key,
`"evidenceMode":"OBSERVED_NOTIFICATION"`; no other extra key is accepted. A
success body without it, or with any other value, is never bound and latches the
intent as `UNEXPECTED_STATUS` with reason `EVIDENCE_MODE_MISMATCH`: "Bridge mode
does not match this SettleTable configuration — do not transfer". The reverse also
fails closed: without the variable, the extra key fails validation, so a PUT to an
observed bridge stays `REQUEST_UNKNOWN` and later reads are `UNAVAILABLE` (that
PUT does create the bridge checkout).

**Refusals.** PUT 409 `OBSERVED_CHECKOUT_SPENT` (the bridge's single checkout is
already used) and 409 `OBSERVED_AMOUNT_MISMATCH` (not the bridge's pinned amount)
create nothing. They latch the intent as `CONFLICT` with that code as the reason:
"Not created — do not transfer". They never become `REQUEST_UNKNOWN` or
`NOT_CREATED`. Without the variable they are ordinary unknown answers
(`REQUEST_UNKNOWN`).

**One attempt per meal.** After the first PUT for a meal, no new attempt is ever
offered or accepted, whatever the outcome; an explicit request is refused
(`resource_limit`, or `checkout_demo_active` while the checkout is open, or
`checkout_demo_already_confirmed` after a confirmation). The only further PUT is the identical re-PUT of the **same**
reference after a checked absence: the intent is `NOT_CREATED` with reason
`REFERENCE_NOT_FOUND` and no `checkoutId` was ever bound. A `SAME_AMOUNT_HELD`
refusal offers no re-PUT. Once a checkout is bound, the only action is a GET.

**Display mapping** (evidence is checked first; `SYNTHETIC` or any other evidence is
`UNEXPECTED_STATUS`):

| Bridge status and evidence | SettleTable shows |
| --- | --- |
| `AWAITING_PAYMENT`, `NONE` | Waiting for the organizer's own wallet notification. Nothing is recorded in SettleTable. Transfer at most once; if already sent, do not send again. |
| `PAYMENT_DETECTED` or `AWAITING_VERIFICATION`, `NOTIFICATION_UNVERIFIED` | Notification observed — unverified. The organizer checks their own wallet history in the bridge. |
| `MANUALLY_CONFIRMED`, `NOTIFICATION_UNVERIFIED` | Notification observed, unverified, manually confirmed by the organizer — SettleTable balance unchanged |
| `AMBIGUOUS`, `NONE` or `NOTIFICATION_UNVERIFIED` | Needs organizer review — not confirmed. Do not transfer again. |
| `EXPIRED` or `REVIEW_EXPIRED`, `NONE` or `NOTIFICATION_UNVERIFIED` | Ended without confirmation. If money was sent, check your wallet history; do not transfer again. |
| any other combination | `UNEXPECTED_STATUS`, latched |

The other local states also say not to transfer: request outcome unknown,
not created, conflict, unexpected status and unavailable.

**Card.** The card is titled "Experimental checkout demo (observed notification)"
and always carries the line "Test transfer between the organizer's own wallets;
the named diner did not pay." The meal should name its counterparty plainly as a
test, for example "Owner's other wallet (test)", never a person. The card keeps
SettleTable's boundary notice that it does not execute or independently verify
bank, card, or e-wallet transactions, and its copy never says that anyone paid or
that anything was settled. The organizer's snapshot carries
`checkout_demo_observed: true` (only in this mode) so the card shows the observed
copy before its first read; the status response carries `observed: true`,
`synthetic: false` and `evidenceMode`.

**Status reads.** The bridge's payment window can stay open well beyond 120 s, so
in this mode the card keeps reading after the fixed 2/5/10/30/60/90/120 s reads:

- every 15 s while the payment window is open (the intent's `expiresAt`);
- then every 30 s until the review deadline (the intent's `reviewExpiresAt`) passes;
- then it stops. It stops at once when the status is finished or latched
  (`terminal` or `latched`).

Each next read is decided from the latest status response, so one read always
follows each deadline and shows the bridge's outcome. Both deadlines come only
from that response: without a valid `expiresAt` (for example a request whose
outcome is unknown) the card stops at 120 s as in the synthetic demo, and without
a `reviewExpiresAt` it stops at the first read after the window ends. The deadlines
are compared with the device clock: with a device clock ahead of the bridge's,
the last read can arrive before the bridge applies its final status, so that status
needs "Refresh demo status"; with a clock behind, reads continue for up to that
difference. The client adds no cap of its own, so reads last as long as the
deadlines the bridge reports. A failed read keeps the last stored deadlines.
While the page is hidden nothing is read and the schedule is cleared; when it is
visible again the whole schedule restarts from 2 s. Each read is the same `GET` to
the same endpoint as before, with at most one bridge GET, and a read never starts
while another is in flight. Without the variable none of this applies.

**Fresh database.** Use a database with no `checkout_demos` rows for this mode.
The local state does not record which mode wrote a row, so a row written by the
synthetic demo could be shown with the observed copy until its next bridge read
fails closed (a mode mismatch or a missing reference). Restarting the same
observed run on its own database is fine.

**One-sen meals.** A suggestion of RM0.01 works: for example one RM0.02 item shared
equally by the organizer and the test counterparty and paid by the organizer
suggests exactly one RM0.01 transfer to the organizer.

## Multi-diner observed mode

`SETTLETABLE_CHECKOUT_DEMO_OBSERVED_MULTI=true` (with the observed flag) is for a
bridge started in its multi-checkout observed mode. Real diners at the meal may pay the
organizer's own TNG wallet, each against their own observed checkout. SettleTable never
takes, holds or moves money and never contacts TNG. Everything in
[observed-evidence mode](#observed-evidence-mode) still applies, with the differences
below. Without the variable none of this applies, and observed mode behaves exactly as
described above.

It stays **display only**: no contribution, pending report or transfer is written,
suggested transfers and balances are unchanged by every outcome, and nothing new is
stored from a notification. Every observed state is shown as unverified. Only after the
organizer confirms on the bridge's own receiver page does a card say "Manually
confirmed by the organizer — notification unverified". An ambiguous match stays
ambiguous: the organizer settles it from TNG history with SettleTable's existing manual
reimbursement records. There is no assignment path and no receiving-QR upload.

**One intent per diner.** Every current suggestion whose receiver is the organizer
(each diner who owes the organizer) may get one observed intent, with the same
single-use rule as observed mode, applied per diner instead of per meal: after a
diner's first PUT the only further PUT for that diner is the identical re-PUT after a
checked absence. Other diners' intents never block a diner. The meal's 50-attempt limit
does not apply; one intent per diner already bounds the rows. Intent references are
formed as above.

**Offset allocation.** Notifications show an amount and a time only, so every amount
held in a meal must be distinct. A diner pays their share less an offset `k` of 0 to 9
sen, chosen inside the `BEGIN IMMEDIATE` transaction that freezes the intent:

1. Excluded amounts are (a) the amount of every intent of the meal that may still hold
   its amount on the bridge and (b) the unadjusted share of every *other* diner who owes
   the organizer and has no confirmed checkout. For (a), from the stored state: an
   unknown request outcome, a lost record, a latched conflict or unexpected status, a
   checked absence (kept for its re-PUT) and every open bridge status hold; a manually
   confirmed checkout holds until its `expiresAt` plus a 120 s margin for clock skew;
   `EXPIRED` and `REVIEW_EXPIRED`, and refusals that created nothing, never hold. This
   is never narrower than the bridge's own rule. An open checkout keeps holding after its
   deadlines until a status read shows that it ended.
2. `k` is the smallest value from 0 to 9 such that `share − k` is not excluded and is at
   least 1 sen. Several diners with the same share therefore never get the plain share.
3. If no `k` fits, the diner is offered no checkout and the card says so plainly; the
   offer returns once a held amount frees up (after a status read or "Refresh demo
   status").
4. Only subtraction: nobody pays more than their share, and the organizer absorbs at most
   9 sen per diner. Balances do not change.

Two allocations never produce the same amount: the database write lock serializes them,
so the second sees the first's frozen amount. The offset is stored in an additive
`checkout_demo_offsets` table (meal, attempt, offset 0–9), written in the same
transaction. Every read checks that each multi-mode intent has exactly one offset and
each diner at most one intent, and that no offset exists outside multi mode; any
disagreement fails closed (`checkout_demo_conflict`). The PUT amount and the amount the
bridge reports are `share − k`.

**Request body.** `POST` accepts exactly `{"sender_id": "...", "amount_sen": SHARE,
"pay_sen": AMOUNT}`: the share is the consent check against the recomputed suggestion,
and `pay_sen` is the exact amount the card showed. If the allocation now gives another
amount, nothing is frozen or sent (`checkout_demo_amount_changed`, 409); with no free
amount, `checkout_demo_no_free_amount` (409). Offers are computed per diner, so two
diners with the same share can be offered the same amount until one of them is
requested; the other's card then shows its new amount. SettleTable never retries with
another amount by itself. In this mode the route authenticates the caller as the organizer
before it judges the body, so within this mode the body's shape tells a diner or an
unauthenticated caller nothing. Across modes it still does: an invalid body gets 403 or
401 here but 400 in the other modes (see Known limitations).

**Bridge answers.** A PUT refused `409 OBSERVED_CHECKOUT_SPENT` (the bridge's checkout
count is used up) latches that diner's intent as `CONFLICT` with that reason and holds
nothing. `409 SAME_AMOUNT_HELD` is `NOT_CREATED` for that diner with no re-PUT. Both are
shown as plain "Not created" states. A success body must carry `evidenceMode` as in
observed mode.

**Status reads.** The bridge has no list route, so a status read sends one GET for each
intent that is neither finished nor latched, one after another under the same wire slot,
and stores each answer in its own transaction. Finished and latched intents are not read
again. To keep the process-wide wire slot short, a read starts no further GET after the
first transport failure (the bridge is not answering) or after 10 s; the intents not read
are shown unavailable for that check, with their stored state kept. A request refused
because the client is suspended or cooling down shows every open intent as unavailable.
The card's read schedule follows every open intent: every 15 s while any payment window
is open, then every 30 s while any review deadline is ahead, then it stops.

**Response.** In this mode the status carries `multi: true`, `intents` (every intent of
the meal, each with `offsetSen` and `paySen` besides `amountSen`, the share), `eligible`
offers with `offsetSen` and `paySen`, and `noFreeAmount` (diners with no free amount).
`intent` stays the latest intent. The organizer's snapshot carries `checkout_demo_multi:
true`. No projection carries a participant name.

**Cards.** One short shared card holds the boundary notice and "Refresh demo status";
then each diner gets a card showing the share, the offset and the amount, the factual
status and two notices, word for word. The amount reads "pay exactly" only while a created
checkout waits for its notification, is not stale and its payment window is open by the
device clock; an offer reads "if requested now (fixed when the checkout is created)", and
any other checkout shows its "checkout amount". The notices:

- "The organizer's phone reads its own TNG payment notifications to update this status.
  TNG shows the organizer your name and amount. From the notification, SettleTable and
  the bridge keep only the amount, the time and technical IDs, never your name. The
  organizer checks TNG before marking you paid."
- "A notification shows an amount and time only; it does not show that this diner paid."

Under the same condition as "pay exactly", the organizer's card shows a hint to read out: "My phone reads my TNG payment alerts to update the bill. It keeps the
amount and time, not your name. I still check TNG myself before marking you paid. Please
pay exactly RM x.yz." These replace observed mode's "own wallets" line in this mode only.

**Known limitations.** A late update to an earlier notification can make a later checkout
of the same amount ambiguous; the allocator follows the smallest-`k` rule and does not
also avoid recently confirmed amounts. A confirmed checkout's amount is freed by
SettleTable's clock; once every intent is finished the card stops reading, so a diner
waiting for that amount needs "Refresh demo status". If SettleTable's clock runs more than
the 120 s margin ahead of the bridge's, that amount can be offered while the bridge still
holds it: the bridge refuses it (`SAME_AMOUNT_HELD`) and that diner's single attempt is
used. The same happens if the bridge store holds an amount from outside this meal; the
exclusion sets are per meal. Use a fresh database and a fresh bridge store per session,
as for observed mode. Returning to an earlier SettleTable version with multi-mode rows
present is not supported; it needs a fresh database. In the synthetic and single observed
modes the route still judges the POST body before authenticating, as before this mode.

## Tests

```bash
python -m unittest discover -s tests -p "test_checkout_demo*.py" -v
```

```bash
node tools/verify_checkout_demo.mjs
```

```bash
node tools/verify_checkout_demo_observed.mjs
```

```bash
node tools/verify_checkout_demo_observed_multi.mjs
```

```bash
node tools/test_checkout_demo_poll_schedule.mjs
```

All but the last run against `tests/checkout_demo_stub.py`, an in-process stub
that follows the bridge contract above (with `observed_amount` set, the
observed-evidence contract; with `observed_count` set, the multi-checkout contract).
They use disposable random credentials, listen on random loopback ports and contact
no real bridge, phone or wallet. `tests/test_checkout_demo_multi.py` covers the offset
rule (both exclusion sets, duplicate shares, the no-fit state, the 1-sen floor, the
9-sen ceiling and re-allocation after a hold ends), every bridge refusal and status, and
two allocations for the same meal racing on separate connections. The observed browser regression fakes page time
(`setTimeout` and `Date`) to check the reads after 120 s, the hidden-page pause
and the stop on a finished status. The last command unit-tests the read schedule
by running the card's own code from `app.js` with a fake clock and no server.
