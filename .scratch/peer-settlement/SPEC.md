# Milestone 2: Suggested Peer Transfers & Settlement Tracking Specification

## 1. Context & Objective
Following the completion and autonomous merge of Milestone 1 (Multi-Payer Contributions & Net Balance Reconciliation, PR #36), Milestone 2 implements suggested peer transfers, partial reimbursements, and durable settlement tracking.

SettleTable tracks repayments attested by the organizer without holding, moving, or executing money.

Authority & Seam Boundary:
- `settletable/calculation.py` remains 100% byte-untouched. Authoritative finalized meal consumption liabilities are immutable.
- All monetary representations use positive integer MYR minor units (sen). Zero floating-point arithmetic.
- Persistence uses additive SQLite WAL tables with trigger-enforced immutability. Zero row deletions.
- Dedicated domain module: `settletable/settlement.py` for settlement calculations, preserving separation of concerns from `settletable/funding.py`.

---

## 2. Mathematical Model & Invariants

### 2.1 Balance Equations
For each participant $p \in \mathcal{P}$:
1. **Base Net Balance**:
   $$\text{BaseNet}(p) = \text{Contributions}(p) - \text{Consumption}(p)$$
2. **Reimbursements**:
   $$\text{ConfirmedSent}(p) = \sum_{t \in \mathcal{T}_{\text{confirmed}}, \text{sender}(t)=p} \text{amount\_sen}(t)$$
   $$\text{ConfirmedReceived}(p) = \sum_{t \in \mathcal{T}_{\text{confirmed}}, \text{receiver}(t)=p} \text{amount\_sen}(t)$$
3. **Outstanding Net Balance**:
   $$\text{OutstandingNet}(p) = \text{BaseNet}(p) + \text{ConfirmedSent}(p) - \text{ConfirmedReceived}(p)$$

### 2.2 Conservation Law
For confirmed transfers $\mathcal{T}_{\text{confirmed}}$, every transfer transfers exactly $X$ sen from sender to receiver:
$$\sum_{p \in \mathcal{P}} \text{ConfirmedSent}(p) = \sum_{p \in \mathcal{P}} \text{ConfirmedReceived}(p)$$
Therefore:
$$\sum_{p \in \mathcal{P}} \text{OutstandingNet}(p) \equiv \sum_{p \in \mathcal{P}} \text{BaseNet}(p) \equiv \text{TotalContributed} - \text{ReceiptTotal} \equiv -\text{UnfundedAmount}$$

When the meal is **fully funded** ($\text{UnfundedAmount} = 0$):
$$\sum_{p \in \mathcal{P}} \text{OutstandingNet}(p) = 0$$
When all debts are settled:
$$\forall p \in \mathcal{P}: \text{OutstandingNet}(p) = 0$$

### 2.3 Deterministic Greedy Settlement Suggestion Algorithm
When $\text{UnfundedAmount} > 0$:
- The restaurant bill is partially unfunded. Total debtor debt exceeds total creditor credit by $\text{UnfundedAmount}$.
- Full settlement is blocked by outstanding external restaurant obligation.
- Suggestions only match up to available creditor credits. Unmatched debtor obligations remain flagged as "Awaiting restaurant funding".

Algorithm:
1. Identify Debtors: $\mathcal{D} = [ (p, |\text{OutstandingNet}(p)|) \mid \text{OutstandingNet}(p) < 0 ]$. Sort $\mathcal{D}$ descending by debt amount, tie-break by $p$ ascending.
2. Identify Creditors: $\mathcal{C} = [ (p, \text{OutstandingNet}(p)) \mid \text{OutstandingNet}(p) > 0 ]$. Sort $\mathcal{C}$ descending by credit amount, tie-break by $p$ ascending.
3. While $\mathcal{D}$ and $\mathcal{C}$ are non-empty:
   - Let $(d, \text{debt}) = \mathcal{D}[0]$ and $(c, \text{credit}) = \mathcal{C}[0]$.
   - Let $\text{xfer} = \min(\text{debt}, \text{credit})$.
   - Yield `SuggestedTransfer(sender_id=d, receiver_id=c, amount_sen=xfer)`.
   - Update $\text{debt} \leftarrow \text{debt} - \text{xfer}$; $\text{credit} \leftarrow \text{credit} - \text{xfer}$.
   - If $\text{credit} == 0$, pop $\mathcal{C}[0]$.
   - If $\text{debt} == 0$, pop $\mathcal{D}[0]$.
   - If $\text{debt} > 0$, update $\mathcal{D}[0] = (d, \text{debt})$ in-place without re-sorting to preserve greedy pairing and prevent transaction fragmentation.
4. Exact cent conservation is unconditionally preserved.

---

## 3. Database Schema & Triggers

### 3.1 Table `peer_transfers`
```sql
CREATE TABLE IF NOT EXISTS peer_transfers (
    meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    transfer_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    receiver_id TEXT NOT NULL,
    amount_sen INTEGER NOT NULL CHECK (amount_sen >= 1 AND amount_sen <= 1000000000),
    note TEXT,
    created_at REAL NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'reversed')),
    reversed_at REAL,
    reversed_by TEXT,
    reversal_command_id TEXT,
    reversal_reason TEXT,
    PRIMARY KEY(meal_id, transfer_id),
    UNIQUE(meal_id, command_id),
    CHECK(sender_id != receiver_id),
    FOREIGN KEY(meal_id, sender_id) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, receiver_id) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, created_by) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, reversed_by) REFERENCES participants(meal_id, id)
);
CREATE INDEX IF NOT EXISTS idx_peer_transfers_status ON peer_transfers(meal_id, status);
```

### 3.2 Immutability Triggers
```sql
CREATE TRIGGER IF NOT EXISTS prevent_peer_transfers_delete
BEFORE DELETE ON peer_transfers
BEGIN
    SELECT RAISE(FAIL, 'peer_transfers rows cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS prevent_peer_transfers_tamper
BEFORE UPDATE ON peer_transfers
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN OLD.status != 'confirmed' THEN
            RAISE(FAIL, 'cannot modify inactive transfer')
        WHEN NEW.status != 'reversed' THEN
            RAISE(FAIL, 'invalid status transition')
        WHEN NEW.meal_id != OLD.meal_id OR NEW.transfer_id != OLD.transfer_id
          OR NEW.command_id != OLD.command_id OR NEW.sender_id != OLD.sender_id
          OR NEW.receiver_id != OLD.receiver_id OR NEW.amount_sen != OLD.amount_sen
          OR NEW.created_at != OLD.created_at OR NEW.created_by != OLD.created_by
          OR (NEW.note IS NOT OLD.note) THEN
            RAISE(FAIL, 'immutable transfer columns cannot be modified')
    END;
END;
```

---

## 4. Commands & Domain Invariants

### 4.1 Post-Finalization Command Classification in `Authority.apply`
In `settletable/authority.py`:
`post_finalization = data['kind'] in ('RecordContribution', 'ReverseContribution', 'RecordTransfer', 'ReverseTransfer')`
Mutations require `state['calculation'] is not None` and update `finalized_revision` backfill if missing.

### 4.2 Command: `RecordTransfer`
- Attributes: `command_id: str`, `expected_revision: int`, `sender_id: str`, `receiver_id: str`, `amount_sen: int`, `note: str | None`
- Invariants:
  - Caller must be organizer (`organizer == True`).
  - Meal must be finalized (`state['calculation'] is not None`).
  - `sender_id != receiver_id` (`self_transfer_prohibited`).
  - Both `sender_id` and `receiver_id` must be known participants in `state['people']`.
  - $1 \le \text{amount\_sen} \le 1,000,000,000$.
  - Sender must have outstanding debt: $\text{OutstandingNet}(\text{sender}) < 0$ (`not_a_debtor`).
  - Receiver must have outstanding credit: $\text{OutstandingNet}(\text{receiver}) > 0$ (`not_a_creditor`).
  - Over-settlement check: $\text{amount\_sen} \le \min(-\text{OutstandingNet}(\text{sender}), \text{OutstandingNet}(\text{receiver}))$ (`over_settlement_prohibited`).
  - Deterministic ID: `transfer_id = derive_transfer_id(meal_id, command_id)`.
  - Stored with `status = 'confirmed'`.

### 4.3 Command: `ReverseTransfer`
- Attributes: `command_id: str`, `expected_revision: int`, `transfer_id: str`, `reason: str | None`
- Invariants:
  - Caller must be organizer.
  - Meal must be finalized.
  - Transfer must exist with `status == 'confirmed'`.
  - Sets `status = 'reversed'`, `reversed_at = now`, `reversed_by = actor`, `reversal_command_id = command_id`, `reversal_reason = reason`.

### 4.4 Invariant Guard for `ReverseContribution` with Active Transfers
When executing `ReverseContribution`:
- Let $P$ be the contributing participant.
- Let $\text{new\_active\_contrib} = \text{total\_active\_contrib}(P) - \text{amount\_to\_reverse}$.
- Let $\text{confirmed\_received} = \sum_{t \in \mathcal{T}_{\text{confirmed}}, \text{receiver}(t)=P} \text{amount\_sen}(t)$.
- If $\text{new\_active\_contrib} < \text{confirmed\_received}$:
  Reject with `AuthorityError('active_peer_transfers_exist')`.
  Rationale: A participant cannot reverse their restaurant contribution below the reimbursement amounts they have already received from peers. The organizer must reverse the dependent peer reimbursements first.

---

## 5. Python Domain Data Classes & Contracts

In `settletable/settlement.py`:
```python
@dataclass(frozen=True)
class SuggestedTransfer:
    sender_id: str
    receiver_id: str
    amount_sen: int

@dataclass(frozen=True)
class PeerTransferRecord:
    transfer_id: str
    command_id: str
    sender_id: str
    receiver_id: str
    amount_sen: int
    note: str | None
    created_at: float
    created_by: str
    status: str
    reversed_at: float | None = None
    reversed_by: str | None = None
    reversal_command_id: str | None = None
    reversal_reason: str | None = None

@dataclass(frozen=True)
class ParticipantOutstandingBalance:
    participant_id: str
    name: str
    is_active: bool
    base_net_balance_sen: int
    confirmed_sent_sen: int
    confirmed_received_sen: int
    outstanding_net_balance_sen: int

@dataclass(frozen=True)
class SettlementSnapshot:
    is_settled: bool
    outstanding_net_balances: tuple[ParticipantOutstandingBalance, ...]
    suggested_transfers: tuple[SuggestedTransfer, ...]
    transfers: tuple[PeerTransferRecord, ...]
    unfunded_blocker_sen: int
```

- In `AcceptedResult`:
  `transfer_id: str | None = None`
- In `DraftSnapshot`:
  `transfers: tuple[PeerTransferRecord, ...] = ()`
  `settlement: SettlementSnapshot | None = None`

---

## 6. UI & Interaction Design
- In finalized view, render "Peer Settlements & Reimbursements" card:
  - Overall status: "All Debts Settled ✓" vs "Settlements Pending".
  - If meal is partially unfunded: display clear alert: "Restaurant bill is not fully funded. RM X.XX outstanding must be contributed to the restaurant before all debts can be reconciled."
  - Suggested Transfers: List of clean cards ("Bob pays Alice RM 10.00") with "Record Reimbursement" button pre-populating form.
  - Informational notice for unmatched debtors: "Debtors whose obligations exceed available peer credits must settle via direct contributions to the restaurant bill."
  - Record Reimbursement Form (Organizer):
    - Sender dropdown (pre-populated with debtors).
    - Receiver dropdown (pre-populated with creditors).
    - Amount input with `inputmode="decimal"` and "Fill Suggested" button.
    - Optional note input.
    - Disclaimer: "SettleTable records organizer-attested reimbursements without executing or verifying bank/e-wallet transactions."
  - Reimbursement Ledger:
    - Chronological list of confirmed and reversed transfers with sender, receiver, amount, note, timestamp, and "Reverse" action button.
    - Strikethrough style for reversed transfers with reversal reason.
  - Outstanding Balances Table:
    - Participant, Base Net, Confirmed Sent, Confirmed Received, Outstanding Net, Status badge.
