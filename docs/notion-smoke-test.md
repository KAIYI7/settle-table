# SettleTable Notion Live Smoke-Test Procedure

This document specifies the exact, minimal procedure for conducting an optional live smoke test of the SettleTable Notion reporting pipeline against a dedicated, disposable Notion test page.

> [!CAUTION]
> **Safety Boundary**: Live Notion export connects to `https://api.notion.com/v1` over outbound HTTPS. Do not perform this procedure with production databases, sensitive receipts, or real accounting records. Use strictly synthetic test meals and an isolated test page.

---

## 1. Prerequisites (Product Owner Setup)

1. **Create an Internal Notion Integration**:
   - Navigate to [notion.so/profile/integrations](https://www.notion.so/profile/integrations).
   - Click **New integration**.
   - Set Name to `SettleTable Demo`, select your target workspace, and click **Save**.
   - Under **Secrets**, copy the **Internal Integration Secret** (`secret_...` or `ntn_...`).
   - Capabilities required: **Insert content**, **Read content**, **Update content**. (No user information capabilities needed).

2. **Create a Dedicated Disposable Test Page**:
   - In your Notion workspace, create a new top-level blank page titled `SettleTable Test Workspace`.
   - Click the `...` menu in the top-right corner $\to$ **Connect to** (or **Add connections**) $\to$ select `SettleTable Demo`.
   - Copy the Page Link (e.g. `https://notion.so/workspace/SettleTable-Test-Workspace-3fb0ffe172a6815eb59def81c6e8eb4d`).
   - Extract the 32-character or hyphenated UUID at the end of the URL (`3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d`).

---

## 2. Test Execution Protocol

1. **Launch the Demo Server (Without `--mock-notion`)**:
   ```bash
   # Provide credentials via environment variables OR via the UI modal
   $env:SETTLETABLE_NOTION_TOKEN = "secret_your_integration_token_here"
   $env:SETTLETABLE_NOTION_PARENT_ID = "3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d"
   python tools/run_demo.py --port 8000 --mock-ocr
   ```

2. **Synthetic Dining Walkthrough**:
   - Navigate to `http://127.0.0.1:8000/`.
   - Create a meal (e.g. Room ID: `smoke-test-meal`, Organizer: `Alice`).
   - Add synthetic diners (e.g. `Bob`, `Charlie`).
   - Enter synthetic receipt items:
     - 2 Nasi Lemak @ RM 12.00 (RM 24.00)
     - 2 Teh Tarik @ RM 3.00 (RM 6.00)
     - Subtotal RM 30.00, SST RM 1.80, Total RM 31.80.
   - Allocate portions and review/seal the receipt.
   - Finalize the meal.

3. **Export to Notion**:
   - In the **Notion Reporting** card, verify the Target Page UUID is populated.
   - Click **Export Report to Notion**.
   - The UI displays an active progress spinner while the background worker exports.
   - Upon completion, the UI displays a green success banner with a direct clickable link to the newly created subpage in Notion.

4. **Verify Export Output in Notion**:
   - The subpage `🍽️ SettleTable: smoke-test-meal` appears as a child of your test page.
   - Callout block lists participants, date, subtotal, SST, and total.
   - Apportionment table matches finalized diner liabilities exactly.
   - Receipt items table lists line items and splitters.
   - Total blocks created $\le 40$ blocks.

5. **Cleanup**:
   - Delete the test subpage in Notion (or move it to Trash).
   - In [notion.so/profile/integrations](https://www.notion.so/profile/integrations), delete or disable the `SettleTable Demo` integration token when testing is finished.
