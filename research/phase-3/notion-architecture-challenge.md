# Independent Architecture and Security Challenge: Bounded Optional Asynchronous Notion Reporting Pipeline

**Target Document**: `C:\LKY_Project\TabWise\.scratch\notion-reporting\SPEC.md`  
**Target Component**: `settletable.notion` and `settletable.transport` (`POST /api/meals/{meal_id}/export/notion`)  
**Review Date**: 2026-10-21  
**Reviewer**: Independent Architecture & Security Challenger  
**Determination**: **CONDITIONAL PASS (REVISE SPEC BEFORE IMPLEMENTATION)**

---

## 1. Executive Summary & Determination

The draft specification (`.scratch/notion-reporting/SPEC.md`) proposes an optional, asynchronous Notion reporting pipeline designed to archive finalized dining settlements without compromising the privacy, financial authority, or local availability of SettleTable. Its foundational architectural tenets—keeping SettleTable's SQLite ledger and calculation engine as the sole canonical authority, one-way projection, zero external socket dependencies in CI via `MockNotionClient`, and zero dependency on Notion for core dining operations—are sound and adhere to SettleTable's architectural principles.

However, an adversarial architecture, security, and protocol audit against the live Notion REST API (v2022-06-28), WSGI transport constraints, and SQLite persistence model has identified **7 critical defects, protocol mismatches, and operational hazards** that must be remediated in the specification before code is written:

1. **Page-Parent vs. Database-Parent Property Payload Fatal Collision (Showstopper)**:  
   Section 4.1 specifies creating/updating page properties including `"Total (MYR)"`, `"Total (Sen)"`, `"Participants"`, `"Status"`, `"Sealed Receipt Digest"`, and `"Finalized Revision"`. Concurrently, Section 2.1 and Section 5.3 set `parent_type = "page_id"` as the default. In Notion's REST API, **pages with a page parent (`page_id`) support exclusively a single property: `"title"`**. Sending database schema properties on a page with a `page_id` parent causes Notion to immediately reject the request with HTTP 400 `validation_error`. All structured metadata on page-parent exports must reside within the page body (Callout block).
2. **False Notion Idempotency Key Assumption**:  
   Section 1 (Tenet 6) claims that Notion provides deduplication via an idempotency key header (`settletable-notion-v1:{meal_id}:{finalized_revision}`). The Notion REST API **does not support native idempotency keys** on `POST /v1/pages`. Re-exports and rapid double-clicks without local concurrency locking will create duplicate orphan pages in the user's workspace. Deduplication and concurrency control must be enforced locally in SQLite.
3. **Block Quota Underestimation & Gate 4 Contradiction**:  
   Section 1 (Tenet 3) and Gate 4 claim Compact Mode creates "$\le 5$ blocks total", protecting multi-member Free workspace limits (1,000 lifetime blocks). However, in Notion's block tree, **every `table_row` is an individual block object**. A meal with 8 diners and 15 items generates ~32 blocks ($1\text{ callout} + 2\text{ headings} + 2\text{ tables} + 25\text{ table rows} + 1\text{ divider} + 1\text{ audit paragraph}$). Gate 4 must be redefined to measure total block allocations accurately ($\le 40$ blocks per meal) or adopt a single-block multi-line Callout format if ultra-compact preservation is needed.
4. **Notion Table Block Payload Invariant Omissions**:  
   Section 4.2 specifies Table Blocks without detailing Notion's mandatory structural constraints: `table_width` is immutable upon creation and must strictly match the `cells` array length of every child `table_row`; table row cells are not plain strings but 2D arrays of `rich_text` objects (`cells: [[{type: "text", text: {content: "..."}}]]`); and a table block cannot be created empty.
5. **Wire Boundary Injection & SSRF Exposure via `parent_id`**:  
   The spec does not define syntactic validation for `parent_id` or pin the target base URL. Passing arbitrary strings, path traversal characters (`../../`), or URLs could trigger path traversal or SSRF. `parent_id` must be strictly validated against Notion's 32/36-character UUID regex, and the HTTP client must hardcode the base URL to `https://api.notion.com/v1/`.
6. **Token Leakage in Logs & Missing Status Code Mapping**:  
   `settletable.transport.redact_log_string` redacts Bearer tokens and session cookies, but does not redact Notion integration tokens (`secret_...` or `ntn_...`). Furthermore, `settletable.transport.STATUS_MAP` is missing `'meal_not_finalized'`. If raised, it defaults to HTTP 400 instead of HTTP 409 Conflict as mandated by Section 5.4.
7. **WSGI Worker Starvation from Unbounded `Retry-After`**:  
   Section 3.2 specifies honoring `Retry-After` on HTTP 429/503. If Notion returns a 30s or 60s `Retry-After`, sleeping in a synchronous WSGI worker thread blocks the single-threaded server, creating a denial-of-service hazard for other diners. Retries must be strictly capped at $\le 2.0$ seconds max sleep, aborting with HTTP 429/503 if longer delays are demanded.

**Gate Determination: CONDITIONAL PASS**. The specification is architecturally sound in concept, but must be revised with the concrete remediations detailed below prior to implementation.

---

## 2. Wire Boundary & Security Challenge

### 2.1 Notion API Token Scrubbing & Redaction
- **The Exposure**:  
  Notion internal integration tokens begin with `secret_` or `ntn_` and are 50–128 characters long. In the draft spec, tokens are accepted either via `POST` JSON body (`{"token": "secret_..."}`) or server environment variable (`NOTION_API_KEY`).
  If a downstream call fails, `urllib.error.HTTPError`, Python traceback strings, WSGI request loggers, or client error responses could serialize the raw token.
- **Vulnerabilities in Existing Codebase**:  
  In `settletable.transport`:
  ```python
  def redact_log_string(s: str) -> str:
      s = TOKEN_REDACT_REGEX.sub(r'\1[REDACTED]', s)
      s = re.sub(r'(Bearer\s+)[A-Za-z0-9_-]+', r'\1[REDACTED]', s, flags=re.IGNORECASE)
      s = re.sub(r'(settletable_session=)[A-Za-z0-9_-]+', r'\1[REDACTED]', s)
      return s
  ```
  If the JSON body containing `"token": "secret_..."` or an exception message like `"HTTP Error 401: Unauthorized for url https://api.notion.com/v1/pages with token secret_abc"` is passed through `redact_log_string`, the Notion token is **not** matched and leaks into stdout/stderr!
- **Mandatory Remediations**:
  1. **Log Redaction Regex**: Expand `redact_log_string` in `transport.py`:
     ```python
     s = re.sub(r'(secret_|ntn_)[A-Za-z0-9_-]{20,}', r'\1[REDACTED]', s)
     s = re.sub(r'"token"\s*:\s*"[^"]+"', r'"token":"[REDACTED]"', s)
     ```
  2. **Exception Sanitization**: `NotionHttpClient` must wrap all `urllib.error.URLError` and `urllib.error.HTTPError` catches in a sanitizer that strips `Authorization` headers and scrubs token strings before re-raising or formatting error messages.
  3. **Zero Token Persistence**: Reaffirm that `notion_exports` table and meal state in SQLite never store `token`. Tokens provided in requests must exist strictly within the ephemeral WSGI stack frame.

### 2.2 Wire Injection, SSRF, and `parent_id` Validation
- **The Risk**:  
  If `parent_id` is passed directly into a URL path (e.g. `https://api.notion.com/v1/blocks/{parent_id}/children`) without validation, an attacker could supply path traversal sequences (`../../users`), query parameter injections (`?page_size=100`), or arbitrary protocol targets.
- **Mandatory Remediations**:
  1. **Strict UUID Validation**: The wire parser must validate `parent_id` against a strict canonical UUID regex before initiating any outbound HTTP call:
     ```python
     NOTION_ID_REGEX = re.compile(r'^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$')
     ```
     Any non-matching input must immediately raise `TransportError('invalid_input', 400)`.
  2. **Pinned Target Endpoint**: Outbound requests must hardcode the base domain to `https://api.notion.com/v1/`. The transport adapter must never accept a custom `notion_base_url` or host override from the client, eliminating SSRF.
  3. **Standard-Library HTTP Transport**: Outbound communication must strictly use `urllib.request` without subprocess execution, preventing OS shell injection.

### 2.3 Organizer Authorization & Spoofing Defense
- **The Verification Flow**:  
  In SettleTable's security architecture:
  1. Active credential extracted from `Authorization: Bearer <token>` or `settletable_session` cookie.
  2. Authenticate via `authority.authenticate(active_cred, meal_id)` returning `(participant_id, is_organizer)`.
  3. Enforce `if not is_organizer: raise TransportError('forbidden', 403)`.
  4. Non-organizer diners or unauthenticated callers cannot trigger Notion exports or probe workspace credentials.
- **Spoofing Defense**:  
  Callers cannot supply `organizer` or `actor` in the JSON request body. Any presence of these keys triggers `TransportError('invalid_input', 400)` per existing `_build_command` defense-in-depth rules.
- **Missing Status Code Mapping (`meal_not_finalized`)**:  
  Section 5.4 mandates HTTP 409 Conflict (`meal_not_finalized`) if the meal is not in a finalized state. In `settletable.transport.STATUS_MAP`, `'meal_not_finalized'` is missing, causing unhandled errors to default to HTTP 400.  
  **Fix**: Explicitly register `'meal_not_finalized': 409` in `STATUS_MAP`.

---

## 3. Notion Block Model & Payload Formatting Challenge

### 3.1 Page Parent vs. Database Parent Collision (CRITICAL)
- **The Notion API Rule**:  
  - When `parent` is `{"page_id": "..."}`, Notion creates a sub-page. Pages parented by pages **do not have a database schema**. They accept strictly one property:
    ```json
    "properties": {
      "title": {
        "title": [{"type": "text", "text": {"content": "🍽️ SettleTable: ..."}}]
      }
    }
    ```
    Attempting to set `Total (Sen)` (number), `Status` (status), or `Participants` (multi-select) on a page-parented page triggers an immediate HTTP 400 `validation_error`: *"Cannot set properties other than title on a page with page parent"*.
  - When `parent` is `{"database_id": "..."}`, Notion creates a database row. However, property names and types must match the database's pre-configured schema exactly.
- **Architectural Resolution**:
  The spec must define distinct payload builders for `parent_type`:
  1. **`parent_type == "page_id"` (Default Compact Mode)**:
     - `properties` payload contains **strictly `title`**.
     - All financial and audit metadata (Merchant, Date, Total Sen, SST, Service Charge, Participants, Revision, Receipt Digest) is rendered directly inside the page body's top Callout block.
  2. **`parent_type == "database_id"`**:
     - Requires that the target database schema define matching property columns, OR the exporter provides fallback graceful degradation (exporting `title` only and logging a warning if custom properties fail).

### 3.2 Table Block & Table Row Exact Payload Structure
- **Notion REST API Constraints (v2022-06-28)**:
  1. **`table_width`**: Must be an integer matching the exact column count. For Diner Apportionment, `table_width = 5`. For Receipt Items Breakdown, `table_width = 5`.
  2. **`table_row` Children**: When creating a `table` block in `POST /v1/pages`, children must be nested under the `table` property:
     ```json
     {
       "object": "block",
       "type": "table",
       "table": {
         "table_width": 5,
         "has_column_header": true,
         "has_row_header": false,
         "children": [
           {
             "type": "table_row",
             "table_row": {
               "cells": [
                 [{"type": "text", "text": {"content": "Participant"}}],
                 [{"type": "text", "text": {"content": "Items Claimed"}}],
                 [{"type": "text", "text": {"content": "Base (MYR)"}}],
                 [{"type": "text", "text": {"content": "Adjustments (MYR)"}}],
                 [{"type": "text", "text": {"content": "Total Owed (MYR)"}}]
               ]
             }
           },
           {
             "type": "table_row",
             "table_row": {
               "cells": [
                 [{"type": "text", "text": {"content": "Alice (Organizer)"}}],
                 [{"type": "text", "text": {"content": "Chicken Rice (1)"}}],
                 [{"type": "text", "text": {"content": "RM 12.00"}}],
                 [{"type": "text", "text": {"content": "RM 1.92"}}],
                 [{"type": "text", "text": {"content": "RM 13.92"}}]
               ]
             }
           }
         ]
       }
     }
     ```
  3. **No Empty Tables**: Notion rejects table blocks with zero `children`. The header row ensures $N \ge 1$, even if a meal has 0 items.
  4. **Cell Wrapping Helper**: Every cell string must be passed through a strict formatter:
     ```python
     def text_cell(content: str) -> list[dict[str, Any]]:
         return [{"type": "text", "text": {"content": str(content)[:2000]}}]
     ```

### 3.3 Free Workspace Quota Reality & Gate 4 Refinement
- **The Quota Mechanic**: Multi-member Free workspaces enforce a strict **1,000 lifetime block limit**.
- **Block Count Breakdown**:
  - Callout: 1 block
  - Headings: 2 blocks
  - Tables: 2 blocks
  - Table Rows: $1 + P$ (participants) and $1 + I$ (receipt items)
  - Divider & Audit Paragraph: 2 blocks
  - Total for 6 diners and 12 items: $1 + 2 + 2 + 7 + 13 + 2 = 27\text{ blocks}$.
- **Resolution**:
  - Update Section 1 Tenet 3 and Gate 4: Replace the inaccurate "$\le 5$ blocks" claim with **"$\le 40$ blocks per meal in Compact Mode"**. This still provides a $70\%$ block savings over full multi-page database relations (which require 60–100 page blocks per meal).
  - Add documentation recommending single-member personal workspaces (unlimited blocks) for large historical archives.

---

## 4. Fault Isolation & Idempotency Challenge

### 4.1 SQLite Ledger Fault Isolation
- **The Invariant**: Live dining, draft adjustments, claims, and finalization must never block on Notion.
- **Decoupled Outbox Execution**:
  - Notion export is initiated strictly on-demand after meal finalization has already committed to SQLite (`finalized = True`).
  - Outbound HTTP calls execute outside the SQLite write transaction.
  - Any network drop, timeout, 429 rate limit, 401 unauthorized, or 404 parent error returns a clean error payload to the organizer UI without altering or rolling back the meal state, calculation results, or finalized status.

### 4.2 Idempotency, Concurrency Control, and Re-exports
- **The Defect in SPEC.md**: Notion's API does not support idempotency headers for page creation. A double-click or ambiguous timeout can result in duplicate pages.
- **SQLite Concurrency & Deduplication State**:
  Update Section 2.3 schema for `notion_exports`:
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
- **Concurrency Locking Protocol**:
  1. When export request arrives, query `notion_exports` for `(meal_id, finalized_revision)`:
     - If `status == 'completed'`: Return existing `page_url` immediately (`status: "already_exported"`).
     - If `status == 'in_progress'` and `exported_at > now - 30s`: Return HTTP 409 Conflict (`export_in_progress`).
  2. If absent or expired, atomically insert `(meal_id, finalized_revision, status='in_progress', exported_at=now)`.
  3. Execute Notion API call:
     - On success: Update row to `status = 'completed'`, persisting `page_id` and `page_url`.
     - On definitive failure: Delete the `in_progress` row, enabling clean retries.
  4. **Ambiguous Timeout Reconciliation**: If `urllib.request` times out, before re-creating a page on subsequent requests, query `GET /v1/blocks/{parent_id}/children` searching for a page titled `🍽️ SettleTable: {meal_id}`. If found, link to that page rather than creating a duplicate.

### 4.3 Rate Limit & Retry Policy in Single-Threaded WSGI
- **The Risk**: SettleTable runs as a local WSGI server with single-threaded or bounded workers. If Notion returns `Retry-After: 60`, calling `time.sleep(60)` starves the entire server.
- **Mandatory Retry Limits**:
  - Maximum retry attempts: 2 (3 attempts total).
  - Maximum sleep per retry: $\le 2.0$ seconds.
  - If `Retry-After > 3.0` seconds or cumulative time exceeds 10 seconds: Abort immediately, return HTTP 429 `resource_limit` or HTTP 503 `busy`, and set `Retry-After: 5` header to the browser client.

---

## 5. Test Strategy & CI Zero-Cost Portability Challenge

### 5.1 Fidelity and Socket Isolation in `MockNotionClient`
- **Zero-Cost / Air-Gapped CI Requirement**:  
  No test in `tests/` or GitHub Actions CI may attempt outbound socket connections to `api.notion.com`.
- **Requirements for `MockNotionClient`**:
  1. **Strict Payload Contract Checking**: To prevent tests from passing with illegal payloads that fail in production, `MockNotionClient` must assert:
     - `parent_id` matches UUID regex.
     - `parent_type == "page_id"` has NO properties other than `title`.
     - `table` blocks contain valid `table_row` children where `len(cells) == table_width`.
     - Cell contents are arrays of rich text objects.
  2. **Adversarial Error Injection**: Must support synthetic triggers:
     - `mock_client.set_error(status=429, headers={'Retry-After': '1'})`
     - `mock_client.set_error(status=401, body={'message': 'Invalid token'})`
     - `mock_client.set_error(status=404, body={'message': 'Parent not found'})`
     - `mock_client.set_timeout()`
  3. **Global Socket Guard**: Unit tests must assert that standard Python sockets are never opened during test execution.

### 5.2 Real Browser Headless Chrome (CDP) Verification
- **E2E Browser Test Integration (`tools/e2e_browser_test.mjs`)**:  
  The browser E2E harness executes against `tools/run_demo.py`.
- **Remediation for Zero-Cost CDP Runs**:
  1. Add a `--mock-notion` CLI flag or `SETTLETABLE_MOCK_NOTION=1` environment variable to `tools/run_demo.py`.
  2. When enabled, `run_demo.py` initializes `SettleTableApp` with `MockNotionClient()`.
  3. In `tools/e2e_browser_test.mjs`:
     - Organizer finalizes the meal.
     - Organizer sees "📤 Export to Notion" card.
     - Organizer enters Notion Parent ID (UUID) and clicks "Export".
     - Harness verifies loading state, followed by green success banner: `[Open Report in Notion ↗]`.
     - Harness verifies that non-organizer (diner browser) has NO export button or access.

---

## 6. Actionable Test Scenarios

The test suite must include these concrete regression cases in `tests/test_notion.py` and `tests/test_notion_adversarial.py`:

| Test ID | Scenario | Expected Behavior |
|---|---|---|
| `TEST-NOTION-01` | Non-organizer diner calls `POST /api/meals/{id}/export/notion` | HTTP 403 Forbidden (`forbidden`) |
| `TEST-NOTION-02` | Unauthenticated caller calls Notion export endpoint | HTTP 401 Unauthorized (`invalid_session`) |
| `TEST-NOTION-03` | Organizer attempts export on an unfinalized draft meal | HTTP 409 Conflict (`meal_not_finalized`) |
| `TEST-NOTION-04` | Malicious `parent_id` with traversal (`../../v1/users`) or URL | HTTP 400 Bad Request (`invalid_input`) |
| `TEST-NOTION-05` | Malformed token (missing `secret_`/`ntn_` prefix, invalid chars) | HTTP 400 Bad Request (`invalid_input`) |
| `TEST-NOTION-06` | Notion 401 Unauthorized simulated in `MockNotionClient` | Returns HTTP 400/502 error; verifies raw token is NOT in response body or logs |
| `TEST-NOTION-07` | Page parent export payload contract verification | Asserts `properties` contains only `title`; all metadata in Callout |
| `TEST-NOTION-08` | Table block column width mismatch injection | Asserts `MockNotionClient` rejects row with 4 cells when `table_width=5` |
| `TEST-NOTION-09` | Concurrent rapid double-click export simulation | Second request receives existing record or HTTP 409 (`export_in_progress`); exactly 1 Notion page created |
| `TEST-NOTION-10` | Ambiguous timeout recovery | First request times out; retry adopts existing page ID rather than creating orphan |
| `TEST-NOTION-11` | Outage fault isolation | Injected 500 error on Notion export leaves finalized meal state and calculation intact in SQLite |
| `TEST-NOTION-12` | Headless Chrome CDP UI flow | E2E test enters Parent ID, verifies loading spinner, verifies green link banner |

---

## 7. Spec Revision Checklist Prior to Implementation

Before implementation commences, `.scratch/notion-reporting/SPEC.md` must be updated with the following revisions:

- [ ] **Section 1 (Tenet 3 & Gate 4)**: Revise block quota expectation from "$\le 5$ blocks" to "$\le 40$ blocks per meal in Compact Mode", explaining Notion's `table_row` block counting model.
- [ ] **Section 1 (Tenet 6)**: Remove reference to Notion native idempotency keys; define SQLite-backed `notion_exports` concurrency tracking (`in_progress` / `completed`) and parent-children reconciliation.
- [ ] **Section 2.1**: Remove `include_receipt_image` or explicitly clarify that SettleTable does not store receipt images in SQLite.
- [ ] **Section 2.3**: Add `status: TEXT` (`'in_progress'`, `'completed'`) and use `exported_at REAL` in `notion_exports`.
- [ ] **Section 4.1**: Separate page properties for `page_id` parent (strictly `title`) versus `database_id` parent; move all structured meal metadata to the Callout block for page parents.
- [ ] **Section 4.2**: Specify exact Table Block payload format (`table_width = 5`, `has_column_header = True`, `cells` as 2D rich text arrays, mandatory header row).
- [ ] **Section 5.3 & 5.4**: Add regex validation for `parent_id` (UUID) and `token` (`secret_` / `ntn_`). Add `'meal_not_finalized': 409` to `STATUS_MAP`.
- [ ] **Section 3.2**: Cap retry backoff to $\le 2.0$ seconds to prevent WSGI worker starvation.
- [ ] **Section 6 & 7**: Add `--mock-notion` support to `run_demo.py` and integrate offline Notion export verification into `tools/e2e_browser_test.mjs`.

**Final Determination: CONDITIONAL PASS (REVISE SPEC BEFORE IMPLEMENTATION)**.
