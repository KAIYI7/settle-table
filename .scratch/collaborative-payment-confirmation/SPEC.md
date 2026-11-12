# Collaborative Payment Confirmation UX Specification

**Status**: In Progress / Draft  
**Target Branch**: `feat/collaborative-payment-confirmation`  
**Classification**: HIGH Risk (touches payment confirmation, authoritative ledger, settlement workflows, authorization boundaries)  
**Governance**: Follows `AGENTS.md` and `docs/agents/governance.md` (Investigate → Design → Implement → Test → Independent Review)

---

## 1. Context & Product Objective

In SettleTable's current implementation, only the organizer can record restaurant bill contributions (`RecordContribution`) and peer reimbursements (`RecordTransfer`). Non-organizer diners can only view the results.

This specification establishes a **collaborative payment confirmation workflow**:
- **Restaurant Payments**: Any participating diner who paid the restaurant cashier at the counter can report "I Paid the Restaurant". The report enters a pending state awaiting organizer confirmation. The organizer confirms or declines. Only confirmation updates the authoritative restaurant funding ledger (`payer_contributions`). The organizer also retains the ability to record payments directly when appropriate.
- **Peer Reimbursements**: Debtors who owe money can select "I've Sent Payment", prefilled from the suggested transfers. The intended recipient (creditor) receives a pending confirmation request and can choose "Confirm Received" or "Not Received" (decline). Only recipient confirmation updates the authoritative transfer ledger (`peer_transfers`). Senders cannot confirm their own payment; unauthorized third parties cannot confirm. Organizers can still record attested payments directly when necessary.
- **Shared Visibility & Clarity**: All diners see clear, understandable statuses across both cards:
  - Outstanding / Not Reported
  - Pending Confirmation
  - Confirmed
  - Declined or Cancelled
  Pending reports are never presented as confirmed bank or e-wallet transactions.
- **Financial & Architectural Invariants**:
  - Exact MYR integer sen arithmetic.
  - Finalized consumption allocations and receipt totals are completely immutable.
  - Pending reports do NOT affect balances until confirmed.
  - Confirmation is atomic, idempotent, and strictly enforces anti-overpayment and anti-oversettlement caps.
  - The authoritative tables (`payer_contributions`, `peer_transfers`) remain append-only/reversal-only with their existing database triggers untouched.
  - Real database (`settletable_data`) is strictly isolated and preserved.

---

## 2. Mathematical Model & Conservation Invariants

Let $\mathcal{P}$ be the set of participants, $\mathcal{R}$ the finalized receipt total in sen, and $\mathcal{C}(p)$ the finalized consumption liability for participant $p$.

### 2.1 Authoritative Balances (Unchanged)
$$\text{TotalContributed} = \sum_{c \in \text{active contributions}} \text{amount\_sen}(c)$$
$$\text{UnfundedAmount} = \max(0, \mathcal{R} - \text{TotalContributed})$$
$$\text{BaseNet}(p) = \text{Contributed}(p) - \mathcal{C}(p)$$
$$\text{OutstandingNet}(p) = \text{BaseNet}(p) + \text{ConfirmedSent}(p) - \text{ConfirmedReceived}(p)$$

### 2.2 Conservation Laws
1. $\sum_{p \in \mathcal{P}} \text{BaseNet}(p) \equiv \text{TotalContributed} - \mathcal{R} \equiv -\text{UnfundedAmount}$
2. $\sum_{p \in \mathcal{P}} \text{ConfirmedSent}(p) \equiv \sum_{p \in \mathcal{P}} \text{ConfirmedReceived}(p)$
3. $\sum_{p \in \mathcal{P}} \text{OutstandingNet}(p) \equiv -\text{UnfundedAmount}$

### 2.3 Pending Isolation Invariant
Let $\mathcal{U}_{\text{pending}}$ be the set of pending contribution reports and $\mathcal{T}_{\text{pending}}$ be the set of pending transfer reports.
$$\forall u \in \mathcal{U}_{\text{pending}}, \quad u \notin \text{active contributions}$$
$$\forall t \in \mathcal{T}_{\text{pending}}, \quad t \notin \mathcal{T}_{\text{confirmed}}$$
$$\Delta \text{BaseNet}(p) = 0 \quad \text{for any pending submission, decline, or cancellation}$$
$$\Delta \text{OutstandingNet}(p) = 0 \quad \text{for any pending submission, decline, or cancellation}$$

Only when a pending report transitions to `status = 'confirmed'` does it generate an authoritative record in `payer_contributions` or `peer_transfers`, adjusting balances exactly once.

---

## 3. Database Architecture & SQLite Schema

Two additive tables store pending reports without touching existing tables:

### 3.1 Table `pending_contributions`
```sql
CREATE TABLE IF NOT EXISTS pending_contributions (
    meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    report_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    amount_sen INTEGER NOT NULL CHECK (amount_sen >= 1 AND amount_sen <= 1000000000),
    payment_method TEXT CHECK (payment_method IN ('cash', 'card', 'ewallet', 'bank_transfer', 'other') OR payment_method IS NULL),
    created_at REAL NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'declined', 'cancelled')),
    resolved_at REAL,
    resolved_by TEXT,
    rejection_reason TEXT,
    contribution_id TEXT,
    PRIMARY KEY(meal_id, report_id),
    UNIQUE(meal_id, command_id),
    FOREIGN KEY(meal_id, participant_id) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, created_by) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, resolved_by) REFERENCES participants(meal_id, id)
);
CREATE INDEX IF NOT EXISTS idx_pending_contributions_status ON pending_contributions(meal_id, status);

CREATE TRIGGER IF NOT EXISTS prevent_pending_contributions_delete
BEFORE DELETE ON pending_contributions
BEGIN
    SELECT RAISE(FAIL, 'pending_contributions rows cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS prevent_pending_contributions_tamper
BEFORE UPDATE ON pending_contributions
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN OLD.status != 'pending' THEN
            RAISE(FAIL, 'cannot modify resolved pending contribution')
        WHEN NEW.status NOT IN ('confirmed', 'declined', 'cancelled') THEN
            RAISE(FAIL, 'invalid status transition')
        WHEN NEW.meal_id != OLD.meal_id OR NEW.report_id != OLD.report_id
          OR NEW.command_id != OLD.command_id OR NEW.participant_id != OLD.participant_id
          OR NEW.amount_sen != OLD.amount_sen OR NEW.created_at != OLD.created_at
          OR NEW.created_by != OLD.created_by OR (NEW.payment_method IS NOT OLD.payment_method) THEN
            RAISE(FAIL, 'immutable pending contribution columns cannot be modified')
    END;
END;
```

### 3.2 Table `pending_transfers`
```sql
CREATE TABLE IF NOT EXISTS pending_transfers (
    meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    report_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    receiver_id TEXT NOT NULL,
    amount_sen INTEGER NOT NULL CHECK (amount_sen >= 1 AND amount_sen <= 1000000000),
    note TEXT,
    created_at REAL NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'declined', 'cancelled')),
    resolved_at REAL,
    resolved_by TEXT,
    rejection_reason TEXT,
    transfer_id TEXT,
    PRIMARY KEY(meal_id, report_id),
    UNIQUE(meal_id, command_id),
    CHECK(sender_id != receiver_id),
    FOREIGN KEY(meal_id, sender_id) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, receiver_id) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, created_by) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, resolved_by) REFERENCES participants(meal_id, id)
);
CREATE INDEX IF NOT EXISTS idx_pending_transfers_status ON pending_transfers(meal_id, status);

CREATE TRIGGER IF NOT EXISTS prevent_pending_transfers_delete
BEFORE DELETE ON pending_transfers
BEGIN
    SELECT RAISE(FAIL, 'pending_transfers rows cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS prevent_pending_transfers_tamper
BEFORE UPDATE ON pending_transfers
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN OLD.status != 'pending' THEN
            RAISE(FAIL, 'cannot modify resolved pending transfer')
        WHEN NEW.status NOT IN ('confirmed', 'declined', 'cancelled') THEN
            RAISE(FAIL, 'invalid status transition')
        WHEN NEW.meal_id != OLD.meal_id OR NEW.report_id != OLD.report_id
          OR NEW.command_id != OLD.command_id OR NEW.sender_id != OLD.sender_id
          OR NEW.receiver_id != OLD.receiver_id OR NEW.amount_sen != OLD.amount_sen
          OR NEW.created_at != OLD.created_at OR NEW.created_by != OLD.created_by
          OR (NEW.note IS NOT OLD.note) THEN
            RAISE(FAIL, 'immutable pending transfer columns cannot be modified')
    END;
END;
```

---

## 4. Commands & Domain Logic

### 4.1 Command Classes
1. `ReportContribution`: Diner reports counter payment.
   - `command_id: str`, `expected_revision: int`, `participant_id: str`, `amount_sen: int`, `payment_method: str | None = None`
2. `ConfirmContribution`: Organizer confirms report.
   - `command_id: str`, `expected_revision: int`, `report_id: str`
3. `DeclineContribution`: Organizer declines report.
   - `command_id: str`, `expected_revision: int`, `report_id: str`, `reason: str | None = None`
4. `CancelContribution`: Reporting diner cancels their own report.
   - `command_id: str`, `expected_revision: int`, `report_id: str`
5. `ReportTransfer`: Debtor diner reports sent reimbursement.
   - `command_id: str`, `expected_revision: int`, `sender_id: str`, `receiver_id: str`, `amount_sen: int`, `note: str | None = None`
6. `ConfirmTransfer`: Creditor diner confirms received reimbursement.
   - `command_id: str`, `expected_revision: int`, `report_id: str`
7. `DeclineTransfer`: Creditor diner marks reimbursement not received.
   - `command_id: str`, `expected_revision: int`, `report_id: str`, `reason: str | None = None`
8. `CancelTransfer`: Sender diner cancels their own report.
   - `command_id: str`, `expected_revision: int`, `report_id: str`

### 4.2 Authorization Matrix
| Command | Allowed Caller | Condition |
| :--- | :--- | :--- |
| `ReportContribution` | Participant (`actor == participant_id`) or Organizer | Active participant, meal finalized |
| `ConfirmContribution` | Organizer only | Report status is `pending` |
| `DeclineContribution` | Organizer only | Report status is `pending` |
| `CancelContribution` | Reporter (`actor == created_by`) | Report status is `pending` |
| `ReportTransfer` | Sender (`actor == sender_id`) | Active debtor, receiver is active creditor |
| `ConfirmTransfer` | Receiver (`actor == receiver_id`) | Report status is `pending`, not sender |
| `DeclineTransfer` | Receiver (`actor == receiver_id`) or Organizer | Report status is `pending` |
| `CancelTransfer` | Sender (`actor == sender_id`) | Report status is `pending` |
| `RecordContribution` | Organizer only | Direct recording (retained) |
| `ReverseContribution` | Organizer only | Direct reversal (retained) |
| `RecordTransfer` | Organizer only | Direct recording (retained) |
| `ReverseTransfer` | Organizer only | Direct reversal (retained) |

---

## 5. Audit Attribution & Display

In `snap.contributions`:
- If `contribution_id` is linked to a confirmed pending contribution:
  - Display: "Reported by [Diner Name], Confirmed by [Organizer Name]"
- If recorded directly via `RecordContribution`:
  - Display: "Recorded by Organizer"

In `snap.transfers`:
- If `transfer_id` is linked to a confirmed pending transfer:
  - Display: "Reported by [Sender Name], Confirmed by [Receiver Name]"
- If recorded directly via `RecordTransfer`:
  - Display: "Recorded by Organizer"

In both cards:
- Pending reports are grouped prominently under "Pending Confirmations" with interactive confirm/decline/cancel buttons according to caller role.
- Clear disclaimers remind participants that SettleTable tracks self-attested settlements and does not move money.
