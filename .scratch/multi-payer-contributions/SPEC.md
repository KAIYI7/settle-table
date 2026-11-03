# SettleTable Multi-Payer Contributions & Net Balance Reconciliation Specification (Remediated)

## 1. Overview & Objectives

In group dining, restaurant bills are frequently settled at the counter by multiple people (e.g. Alice pays RM 50 in cash, Bob pays the remaining RM 56.40 via credit card; or an organizer pays the bill but another friend covers part of it).

This specification establishes:
1. **Durable Multi-Payer Contribution Recording**: Allows organizers to record actual payments made to the restaurant toward the finalized bill.
2. **Authoritative Funding Status**: Evaluates whether the restaurant bill is `Not Funded`, `Partially Funded`, or `Fully Funded`.
3. **Participant Net Balance Reconciliation**: Derives each participant's base net balance (`Contributed - Consumption Liability`) while strictly conserving total cents.
4. **Auditable, Additive Reversals**: Financial history is immutable; corrections occur via explicit reversals rather than silent overwriting. Enforced by SQLite database triggers.
5. **Decoupled Architecture**: Finalized consumption calculations (`settletable/calculation.py`) remain 100% byte-untouched and immutable. Restaurant funding is independent of diner consumption liability.
6. **Notion Export Idempotency**: Notion exports are anchored to the immutable `finalized_revision`, completely decoupling Notion caching and lifetime block limits from post-finalization revision increments.

All 10 remediations from the independent architecture and security challenge are incorporated into this specification.

---

## 2. Domain Invariants & Mathematical Formulations

### 2.1 Integer Sen Money Boundary
- All monetary amounts are non-negative integer minor units (MYR sen):
  $$1 \le \text{amount\_sen} \le 1,000,000,000$$
- Floats and binary rounding are strictly prohibited in persistence and arithmetic.

### 2.2 Active Contributions & Bill Funding
Let $\mathcal{C}$ be the set of recorded contributions for meal $M$.
Each contribution $c \in \mathcal{C}$ has status $\in \{\text{'active'}, \text{'reversed'}\}$.
The active contributions are:
$$\mathcal{C}_{\text{active}} = \{c \in \mathcal{C} \mid c.\text{status} = \text{'active'}\}$$

$$\text{Total Contributed} = \sum_{c \in \mathcal{C}_{\text{active}}} c.\text{amount\_sen}$$
$$\text{Unfunded Amount} = \max(0, \text{Receipt Total} - \text{Total Contributed})$$

### 2.3 Funding Status (Disambiguated for Zero-Total Meals - Remediation 6)
$$\text{Funding Status} = \begin{cases}
\text{'fully\_funded'} & \text{if } \text{Total Contributed} \ge \text{Receipt Total} \\
\text{'not\_funded'} & \text{if } \text{Total Contributed} = 0 \text{ and } \text{Receipt Total} > 0 \\
\text{'partially\_funded'} & \text{if } 0 < \text{Total Contributed} < \text{Receipt Total}
\end{cases}$$

### 2.4 Overpayment Prevention Policy
A new contribution $c_{\text{new}}$ is accepted if and only if:
$$\text{Total Contributed} + c_{\text{new}}.\text{amount\_sen} \le \text{Receipt Total}$$
Any contribution exceeding the remaining unfunded bill is conservatively rejected with `AuthorityError('overpayment_prohibited')`.

### 2.5 Participant Base Net Balance & Inactive Inclusion (Remediation 5)
Let $\mathcal{P}$ be the authoritative participant set fixed at finalization in `calculation.consumption`.
For each participant $p \in \mathcal{P}$:
$$\text{Contributed}(p) = \sum_{c \in \mathcal{C}_{\text{active}}, c.\text{participant\_id} = p} c.\text{amount\_sen}$$
$$\text{Consumption}(p) = \text{authoritative finalized consumption from } \text{calculation.consumption}(p)$$
$$\text{Base Net Balance}(p) = \text{Contributed}(p) - \text{Consumption}(p)$$

- If $\text{Base Net Balance}(p) > 0$: $p$ is a **Creditor** (entitled to recover money).
- If $\text{Base Net Balance}(p) < 0$: $p$ is a **Debtor** (owes money).
- If $\text{Base Net Balance}(p) = 0$: $p$ is **Settled** (contributions exactly match consumption).

### 2.6 Cent Conservation Law
$$\sum_{p \in \mathcal{P}} \text{Base Net Balance}(p) = \text{Total Contributed} - \text{Receipt Total} = -\text{Unfunded Amount}$$

- When $\text{Funding Status} = \text{'fully\_funded'}$:
  $$\sum_{p \in \mathcal{P}} \text{Base Net Balance}(p) = 0$$
- When $\text{Funding Status} = \text{'partially\_funded'}$:
  The negative net balance sum exactly equals the remaining debt to the restaurant. It represents an outstanding external restaurant obligation, not a peer debt.
- Cent conservation holds unconditionally across all participants, including any participant whose membership was subsequently revoked.

---

## 3. Database Schema & Persistence (Remediations 4, 10)

### 3.1 Table `payer_contributions` and Triggers
An additive SQLite table and immutability triggers created in `Authority.__init__`:
```sql
CREATE TABLE IF NOT EXISTS payer_contributions (
    meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    contribution_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    amount_sen INTEGER NOT NULL CHECK (amount_sen >= 1 AND amount_sen <= 1000000000),
    payment_method TEXT CHECK (payment_method IN ('cash', 'card', 'ewallet', 'bank_transfer', 'other') OR payment_method IS NULL),
    created_at REAL NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'reversed')),
    reversed_at REAL,
    reversed_by TEXT,
    reversal_command_id TEXT,
    reversal_reason TEXT,
    PRIMARY KEY(meal_id, contribution_id),
    UNIQUE(meal_id, command_id),
    FOREIGN KEY(meal_id, participant_id) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, created_by) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, reversed_by) REFERENCES participants(meal_id, id)
);

CREATE INDEX IF NOT EXISTS idx_payer_contributions_status ON payer_contributions(meal_id, status);

CREATE TRIGGER IF NOT EXISTS prevent_payer_contributions_delete
BEFORE DELETE ON payer_contributions
BEGIN
    SELECT RAISE(FAIL, 'payer_contributions rows cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS prevent_payer_contributions_tamper
BEFORE UPDATE ON payer_contributions
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN OLD.status != 'active' THEN
            RAISE(FAIL, 'cannot modify inactive contribution')
        WHEN NEW.status != 'reversed' THEN
            RAISE(FAIL, 'invalid status transition')
        WHEN NEW.meal_id != OLD.meal_id OR NEW.contribution_id != OLD.contribution_id
          OR NEW.command_id != OLD.command_id OR NEW.participant_id != OLD.participant_id
          OR NEW.amount_sen != OLD.amount_sen OR NEW.created_at != OLD.created_at
          OR NEW.created_by != OLD.created_by THEN
            RAISE(FAIL, 'immutable contribution columns cannot be modified')
    END;
END;
```

---

## 4. Commands & Protocol Contract (Remediations 1, 3, 7, 9)

### 4.1 Lifecycle Partitioning in `Authority.apply`
Command kinds are partitioned into three lifecycle sets:
1. `DRAFT_MUTATION_COMMANDS = {'ReplaceReceipt', 'SetOwnQuantity', 'AssignParticipantQuantity', 'SetItemAllocations', 'ReviewReceipt', 'Finalize'}`
   Strictly requires `state['calculation'] is None` (`AuthorityError('finalized')`).
2. `POST_FINALIZATION_COMMANDS = {'RecordContribution', 'ReverseContribution'}`
   Strictly requires `state['calculation'] is not None` (`AuthorityError('not_finalized')`).
3. `SECURITY_COMMANDS = {'RevokeSession', 'RevokeMembership', 'RevokeInvitation'}`
   Permitted in either lifecycle state.

### 4.2 `RecordContribution`
- **Fields**:
  - `command_id`: str (validated with `_id`)
  - `expected_revision`: int (MANDATORY optimistic concurrency check)
  - `participant_id`: str (validated with `_id`)
  - `amount_sen`: int ($1 \le \text{amount\_sen} \le 1,000,000,000$)
  - `payment_method`: str | None (one of `'cash'`, `'card'`, `'ewallet'`, `'bank_transfer'`, `'other'`, or `None`)
- **Validation**:
  - Meal must be finalized (`state['calculation'] is not None`).
  - Caller must be organizer (`organizer == True`).
  - `participant_id` must be in `calculation.consumption` participant IDs.
  - $\text{Total Contributed} + \text{amount\_sen} \le \text{Receipt Total}$.
- **Deterministic ID**:
  $$c_{\text{id}} = \text{"contrib-" } + \text{SHA256}(\text{meal\_id} + ":" + \text{command\_id})[:16]$$
- **Effect**:
  - Inserts row into `payer_contributions`.
  - Advances `state['revision'] += 1`.
  - Records command into `commands` table with identical replay idempotency.

### 4.3 `ReverseContribution`
- **Fields**:
  - `command_id`: str
  - `expected_revision`: int (MANDATORY optimistic concurrency check)
  - `contribution_id`: str
  - `reason`: str | None (sanitized with `_text(reason, 200)` if present)
- **Validation**:
  - Meal must be finalized.
  - Caller must be organizer.
  - Target contribution must exist in meal with `status == 'active'`.
- **Effect**:
  - Updates target row: `status = 'reversed'`, `reversed_at = now`, `reversed_by = actor`, `reversal_command_id = command_id`, `reversal_reason = reason`.
  - Advances `state['revision'] += 1`.
  - Records command in `commands` table.

---

## 5. Snapshot Representation & Notion Decoupling (Remediations 2, 8)

### 5.1 Decoupled `finalized_revision`
- In `Authority._finalize`:
  `state['finalized_revision'] = state['revision'] + 1`
- `DraftSnapshot` exposes:
  `finalized_revision: int | None = None`
- In `transport.py`, Notion export lookups and mutations query `snap.finalized_revision or snap.revision`, ensuring that subsequent contribution commands do not produce duplicate Notion pages or break export tracking.

### 5.2 Deterministic Ordering in `DraftSnapshot.funding` and `contributions`
- `contributions`: tuple of `PayerContributionRecord`, strictly ordered by `created_at ASC, contribution_id ASC`.
- `funding.net_balances`: tuple of `ParticipantNetBalance`, strictly ordered by `participant_id ASC`.

---

## 6. Frontend UI / UX Experience

- Rendered within the finalized meal view in `settletable/static/app.js`:
  1. **Funding Progress Bar**:
     - Visual bar indicating percentage funded.
     - Badges: `Not Funded (RM 0.00 / RM X.XX)` (amber), `Partially Funded (RM Y.YY / RM X.XX - RM Z.ZZ Remaining)` (blue), or `✓ Fully Funded (RM X.XX)` (green).
  2. **Per-Participant Financial Breakdown Table**:
     - Columns: Participant, Consumed (authoritative), Contributed, Net Balance, Status.
     - Net balance highlighted: Green `+RM X.XX` (Creditor), Red `-RM X.XX` (Debtor), Neutral `RM 0.00` (Settled).
     - Informational disclaimer explaining that when partially funded, negative net balances represent outstanding restaurant liability.
  3. **Record Contribution Card (Organizer Only)**:
     - Participant selector dropdown.
     - Amount in RM (with auto-fill "Remaining RM Z.ZZ" convenience button).
     - Payment Method selector (`Cash`, `Credit / Debit Card`, `E-Wallet (Touch 'n Go / GrabPay)`, `Online Transfer (DuitNow)`, `Other`).
     - Submit button dispatching `RecordContribution`.
  4. **Auditable Contribution History Ledger**:
     - Chronological list of contributions with timestamps, contributor, payment method, amount.
     - Clear strikethrough and `[Reversed]` badge for reversed contributions.
     - Safe `Reverse` button with reason prompt for active entries.
