# SettleTable Bounded Optional Asynchronous Notion Reporting Specification

## 1. Overview & Objective

This specification defines the **optional, asynchronous Notion reporting pipeline** for SettleTable.
Notion serves as a downstream, read-only report and receipt archive layer. Live meal collaboration, item claiming, receipt review, and finalized apportionment **must never depend on Notion availability, latency, or credentials**.

### Architectural Tenets
1. **Downstream & Completely Decoupled**: Live dining sessions operate 100% offline or air-gapped without Notion. Finalization succeeds regardless of whether Notion is configured, reachable, or experiencing outages.
2. **One-Way Canonical Projection**: SettleTable's SQLite authority and `settletable.calculation` engine are the sole source of truth. External edits in Notion can never alter balances, claims, or financial liabilities. No authoritative calculations or formulas are delegated to Notion.
3. **Block-Quota Efficiency (Compact Default)**: In Notion's block tree, every `table_row` counts as an individual block. Multi-member Free workspaces have a strict 1,000 lifetime block limit. In **Compact Mode**, an export generates $\le 40$ blocks per meal (1 callout + 2 headings + 2 tables + rows + divider + audit paragraph), yielding a $>70\%$ block savings over relational multi-page database designs (which require 60–100 page blocks per meal).
4. **Secret & Credential Hygiene**: Notion API tokens (`secret_...` or `ntn_...`) are strictly protected:
   - Never logged to stdout, stderr, or debug logs (enforced via expanded regex redaction in `settletable.transport.redact_log_string`).
   - Never persisted to SQLite database disk.
   - Never exposed to non-organizer diners or returned in client API responses.
   - In HTTP error messages and exceptions, `Authorization: Bearer [REDACTED]` is enforced.
5. **Deterministic Portability (Zero Paid Services / Zero External Sockets in CI)**:
   - Pure Python standard library implementation (`urllib.request`) — zero external SDK dependencies.
   - In-memory `MockNotionClient` enforces exact Notion REST API structural constraints and allows 100% of the test suite and GitHub Actions CI to pass deterministically in an air-gapped environment without external network calls or paid API subscriptions.
6. **SQLite-Backed Deduplication & Concurrency State**:
   - Because Notion's REST API does not provide native idempotency keys on `POST /v1/pages`, deduplication and double-click prevention are enforced locally in SQLite via an atomic `notion_exports` state machine (`in_progress` -> `completed`).

---

## 2. Data Models (`settletable/notion/models.py`)

### 2.1 Configuration
```python
@dataclass(frozen=True)
class NotionExportConfig:
    token: str
    parent_id: str  # Page UUID or Database UUID
    parent_type: str = 'page_id'  # 'page_id' (default) or 'database_id'
    mode: str = 'compact'  # 'compact' (default, <= 40 blocks) or 'detailed'
    api_version: str = '2022-06-28'
```

### 2.2 Result & Status
```python
@dataclass(frozen=True)
class NotionExportResult:
    ok: bool
    status: str  # 'completed', 'already_exported', 'failed'
    page_id: str | None = None
    page_url: str | None = None
    error: str | None = None
    blocks_created: int = 0
```

### 2.3 Export Record (SQLite Persistence)
Table: `notion_exports`
```sql
CREATE TABLE IF NOT EXISTS notion_exports (
    meal_id TEXT NOT NULL REFERENCES meals(id),
    finalized_revision INTEGER NOT NULL,
    page_id TEXT NOT NULL,
    page_url TEXT NOT NULL,
    exported_at REAL NOT NULL,
    export_digest TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    PRIMARY KEY (meal_id, finalized_revision)
);
```

---

## 3. Notion Client Protocol & Implementations (`settletable/notion/client.py`)

### 3.1 Protocol
```python
class NotionClientProtocol(Protocol):
    def create_page(self, parent: dict[str, Any], properties: dict[str, Any], children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        ...
    def append_block_children(self, block_id: str, children: list[dict[str, Any]]) -> dict[str, Any]:
        ...
    def query_block_children(self, block_id: str) -> list[dict[str, Any]]:
        ...
    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        ...
```

### 3.2 HTTP Client (`NotionHttpClient`)
- Built strictly with Python `urllib.request`.
- Hardcoded base URL: `https://api.notion.com/v1/` (no client override to prevent SSRF).
- Headers:
  - `Authorization: Bearer <token>`
  - `Notion-Version: 2022-06-28`
  - `Content-Type: application/json`
- Rate-Limit and Retry Handling:
  - Catches HTTP 429 and 503 responses.
  - Bounded sleep: parses `Retry-After` header, capped at $\le 2.0$ seconds (max 2 retries, 5s cumulative timeout) to prevent single-threaded WSGI worker starvation.
  - If `Retry-After > 2.0` or retries exhausted, aborts immediately and raises `NotionRateLimitError`.
  - Sanitizes exception messages to strip `token` and raw authorization headers.

### 3.3 Mock Client (`MockNotionClient`)
- In-memory store validating exact Notion payload invariants:
  - Asserts `parent_id` matches UUID regex.
  - Asserts `parent_type == 'page_id'` receives strictly `title` in `properties`.
  - Asserts `table` blocks contain valid `table_row` children where `len(cells) == table_width`.
  - Asserts table cells are 2D arrays of `rich_text` objects.
- Supports synthetic error injection for testing:
  - `set_error(status=429, headers={'Retry-After': '1'})`
  - `set_error(status=401, body={'message': 'Invalid token'})`
  - `set_error(status=404, body={'message': 'Parent not found'})`
  - `set_timeout()`

---

## 4. Exporter Engine (`settletable/notion/exporter.py`)

### 4.1 Page Properties (Meal Level)
- **`parent_type == "page_id"` (Default)**:
  - `properties` payload contains **strictly the `title` property**:
    ```json
    {
      "title": {
        "title": [{"type": "text", "text": {"content": "🍽️ SettleTable: {meal_id} ({date})"}}]
      }
    }
    ```
  - All financial facts (Total, Subtotal, SST, Service Charge, Rounding, Participants, Revision, Receipt Digest) are rendered in the top Callout block inside the page body.
- **`parent_type == "database_id"`**:
  - Sets `title`, and if configured, mapped database properties (`Total (MYR)`, `Status`, etc.).

### 4.2 Page Children Blocks (Compact Mode)
1. **Callout Block**: Summary with emoji 🧾:
   - Merchant, Date/Time, Finalized at, Revision.
   - Grand Total: `RM {total_sen / 100:.2f}` (`{total_sen} sen`).
   - Subtotal: `RM {subtotal_sen / 100:.2f}` (`{subtotal_sen} sen`).
   - Adjustments: SST, Service Charge, Discounts, BNM Rounding.
   - Participants: `Alice (Organizer), Bob (Diner)`.
   - Cryptographic Audit Digest: SHA-256 receipt & calculation digest.
2. **Heading 2**: `Diner Apportionment`
3. **Table Block (`table_width = 5`)**:
   - Column Headers: `Participant`, `Items Claimed`, `Base (MYR)`, `Adjustments (MYR)`, `Total Owed (MYR)`.
   - 1 `table_row` per participant mapped from `calculation.consumption`.
4. **Heading 2**: `Receipt Items Breakdown`
5. **Table Block (`table_width = 5`)**:
   - Column Headers: `Item`, `Quantity`, `Unit Price (MYR)`, `Line Total (MYR)`, `Split Among`.
   - 1 `table_row` per receipt item.
6. **Divider Block** followed by small audit note with SettleTable version.

---

## 5. Wire Transport API (`settletable/transport.py`)

### 5.1 Route
`POST /api/meals/{meal_id}/export/notion`

### 5.2 Request Headers
- `Authorization: Bearer <organizer_token>` or cookie session
- `X-SettleTable-Action: 1`
- `Content-Type: application/json`

### 5.3 Request Body
```json
{
  "token": "secret_...",            // Optional if set via environment variable
  "parent_id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d", // Required Notion Page UUID
  "parent_type": "page_id",         // "page_id" (default) or "database_id"
  "mode": "compact"                 // "compact" (default)
}
```

### 5.4 Wire Validation & Invariants
1. **UUID Regex Validation**: `parent_id` must match `^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$`. Malformed IDs raise `TransportError('invalid_input', 400)`.
2. **Token Format Validation**: When provided, `token` must start with `secret_` or `ntn_` and have length between 20 and 128 chars.
3. **Organizer Authorization**: Must be organizer (`is_organizer == True`). Non-organizers receive HTTP 403 `forbidden`. Unauthenticated callers receive HTTP 401 `invalid_session`.
4. **Finalized State Required**: If meal is not finalized, raises `TransportError('meal_not_finalized', 409)`.
5. **Zero Authority Mutation**: SQLite meal rows, claims, and revisions are untouched.
6. **Concurrency State Machine**:
   - Checks `notion_exports` table for `(meal_id, finalized_revision)`.
   - If `status == 'completed'`: Returns existing `page_url` immediately with `status: "already_exported"`.
   - If `status == 'in_progress'` within last 30s: Raises HTTP 409 `export_in_progress`.
   - Inserts `in_progress`, performs Notion export, then updates to `completed`.

---

## 6. Frontend Integration (`settletable/static/app.js`)

1. In `renderFinalizedCalculation()`:
   - Organizer view renders an **"📤 Export to Notion"** card.
   - Clicking opens a modal prompting for Notion Parent ID (and Token if not pre-configured).
2. On submit:
   - Shows spinner.
   - On success: renders green banner with direct link: `[Open Report in Notion ↗]`.
   - On error: displays actionable error banner without resetting the meal state.

---

## 7. Audit & Acceptance Gates

1. **Gate 1: Decoupling & Fault Isolation**: Meal collaboration, item claiming, and finalization succeed 100% when Notion is down, unconfigured, or failing.
2. **Gate 2: Secret Hygiene**: Notion tokens are never persisted, never logged, and redacted in all tracebacks (`secret_...[REDACTED]`).
3. **Gate 3: One-Way Invariance**: Exported amounts exactly match `calculation.consumption` integer sen values; no calculations performed by Notion.
4. **Gate 4: Quota & Block Efficiency**: Compact mode produces $\le 40$ blocks per meal, protecting Free workspace limits.
5. **Gate 5: Deterministic CI Portability**: `MockNotionClient` runs all unit, integration, and E2E tests in < 1 second with 0 network calls.
6. **Gate 6: Real Browser E2E Integration**: Automated Headless Chrome test exercises the Notion export UI flow via `--mock-notion`.
