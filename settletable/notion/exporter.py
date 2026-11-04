"""Export engine for generating Notion pages and blocks from finalized SettleTable meals."""
import re
from typing import Any

from .client import (
    NOTION_ID_REGEX,
    NotionClientProtocol,
    NotionValidationError,
    NotionAuthError,
    NotionNotFoundError,
    NotionRateLimitError,
    NotionError,
)
from .models import NotionExportConfig, NotionExportResult


def text_cell(content: str) -> list[dict[str, Any]]:
    """Format string into a single-item rich text array for a Notion table cell."""
    return [{"type": "text", "text": {"content": str(content)[:2000]}}]


def format_sen(sen: int | None) -> str:
    """Format integer sen into RM standard representation without float drift."""
    if sen is None:
        return "RM 0.00"
    sign = "-" if sen < 0 else ""
    abs_sen = abs(sen)
    whole = abs_sen // 100
    frac = abs_sen % 100
    return f"{sign}RM {whole}.{frac:02d}"


MAX_COMPACT_BLOCKS = 40


def count_notion_blocks(blocks: list[dict[str, Any]]) -> int:
    """Accurately count total Notion blocks including top-level blocks and nested table rows."""
    count = 0
    for blk in blocks:
        count += 1
        if blk.get("type") == "table":
            tbl = blk.get("table", {})
            rows = tbl.get("children", [])
            count += len(rows)
    return count


def format_meal_properties(
    meal_id: str,
    snapshot: dict[str, Any],
    parent_type: str = "page_id",
) -> dict[str, Any]:
    """Generate Notion page properties strictly conforming to parent_type constraints.
    
    Pages parented by another page ('page_id') strictly permit only 'title'.
    """
    receipt = snapshot.get("receipt") or {}
    merchant = receipt.get("merchant") or meal_id
    title_text = f"🍽️ SettleTable: {merchant} ({meal_id})"

    props: dict[str, Any] = {
        "title": {
            "title": [
                {
                    "type": "text",
                    "text": {"content": title_text},
                }
            ]
        }
    }

    if parent_type == "database_id":
        total_sen = receipt.get("total_sen") or 0
        props["Total (Sen)"] = {"number": total_sen}
        props["Total (MYR)"] = {"rich_text": text_cell(format_sen(total_sen))}
        props["Status"] = {"status": {"name": "Finalized"}}

    return props


def format_compact_meal_blocks(
    meal_id: str,
    snapshot: dict[str, Any],
    image_block: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Format high-density, compact Notion blocks (<= 40 blocks total) for a finalized meal."""
    receipt = snapshot.get("receipt") or {}
    calc = snapshot.get("calculation") or {}
    participants = {p["id"]: p for p in snapshot.get("participants", [])}
    items = receipt.get("items", [])
    adjustments = receipt.get("adjustments", [])
    revision = snapshot.get("revision", 0)

    # Normalized claims by item_id
    raw_claims = snapshot.get("claims", [])
    claims_by_item: dict[str, list[dict[str, Any]]] = {}
    if isinstance(raw_claims, dict):
        claims_by_item = raw_claims
    elif isinstance(raw_claims, (list, tuple)):
        for c in raw_claims:
            if isinstance(c, dict):
                c_item = c.get("item_id")
                claims_by_item.setdefault(c_item, []).append(c)
            elif hasattr(c, "item_id"):
                claims_by_item.setdefault(c.item_id, []).append({
                    "item_id": c.item_id,
                    "participant_id": c.participant_id,
                    "quantity": c.quantity,
                })

    # Normalized consumption map
    raw_con = calc.get("consumption", [])
    consumption_by_part: dict[str, int] = {}
    if isinstance(raw_con, dict):
        for k, v in raw_con.items():
            consumption_by_part[k] = v.get("total_sen", v.get("sen", 0)) if isinstance(v, dict) else int(v)
    elif isinstance(raw_con, (list, tuple)):
        for entry in raw_con:
            if isinstance(entry, dict):
                pid = entry.get("participant_id")
                if pid:
                    consumption_by_part[pid] = entry.get("sen", 0)
            elif hasattr(entry, "participant_id"):
                consumption_by_part[entry.participant_id] = entry.sen

    # Calculate item base shares and adjustment shares per participant
    base_shares: dict[str, int] = {}
    for src in calc.get("items", []):
        shares = src.get("shares", []) if isinstance(src, dict) else getattr(src, "shares", [])
        for sh in shares:
            sh_pid = sh.get("participant_id") if isinstance(sh, dict) else getattr(sh, "participant_id", None)
            sh_sen = sh.get("sen", 0) if isinstance(sh, dict) else getattr(sh, "sen", 0)
            if sh_pid:
                base_shares[sh_pid] = base_shares.get(sh_pid, 0) + sh_sen

    adj_shares: dict[str, int] = {}
    for src in calc.get("adjustments", []):
        shares = src.get("shares", []) if isinstance(src, dict) else getattr(src, "shares", [])
        for sh in shares:
            sh_pid = sh.get("participant_id") if isinstance(sh, dict) else getattr(sh, "participant_id", None)
            sh_sen = sh.get("sen", 0) if isinstance(sh, dict) else getattr(sh, "sen", 0)
            if sh_pid:
                adj_shares[sh_pid] = adj_shares.get(sh_pid, 0) + sh_sen

    total_sen = receipt.get("total_sen", 0)
    subtotal_sen = receipt.get("subtotal_sen", 0)
    included_tax_sen = receipt.get("included_tax_sen", 0)

    # 1. Summary Callout Block
    adj_lines = []
    for adj in adjustments:
        adj_lines.append(f"• {adj.get('label', adj.get('kind', 'Adjustment'))}: {format_sen(adj.get('amount_sen', 0))}")
    if included_tax_sen:
        adj_lines.append(f"• Included Tax (SST): {format_sen(included_tax_sen)} (tax-inclusive)")
    adj_text = "\n".join(adj_lines) if adj_lines else "None"

    part_names = [p.get("name", pid) for pid, p in participants.items()]
    part_str = ", ".join(part_names) if part_names else "None"

    receipt_digest = snapshot.get("receipt_digest") or "unsealed"
    calc_digest = snapshot.get("calculation_digest") or "uncalculated"

    callout_content = (
        f"Meal ID: {meal_id} | Finalized Revision: {revision}\n"
        f"Grand Total: {format_sen(total_sen)} ({total_sen} sen)\n"
        f"Item Subtotal: {format_sen(subtotal_sen)} ({subtotal_sen} sen)\n"
        f"Adjustments:\n{adj_text}\n"
        f"Participants: {part_str}\n"
        f"Audit Digests: Receipt [{receipt_digest[:16]}...] • Calc [{calc_digest[:16]}...]"
    )

    callout_block = {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": callout_content}}],
            "icon": {"type": "emoji", "emoji": "🧾"},
        },
    }

    # 2. Diner Apportionment Heading & Table
    apportionment_heading = {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "👥 Diner Apportionment"}}],
        },
    }

    apportionment_rows = [
        # Table Header Row
        {
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell("Participant"),
                    text_cell("Items Claimed"),
                    text_cell("Base (MYR)"),
                    text_cell("Adjustments (MYR)"),
                    text_cell("Total Owed (MYR)"),
                ]
            },
        }
    ]

    # Bounded Diner Apportionment Rows (cap to 20 to protect block budget)
    part_keys = list(participants.keys())
    if len(part_keys) > 20:
        display_part_keys = part_keys[:19]
        rollup_part_keys = part_keys[19:]
    else:
        display_part_keys = part_keys
        rollup_part_keys = []

    for pid in display_part_keys:
        pdata = participants[pid]
        pname = pdata.get("name", pid)
        if pdata.get("is_organizer") or pdata.get("organizer"):
            pname += " (Organizer)"

        # Find items claimed by this participant
        p_claimed = []
        for it in items:
            it_id = it.get("id")
            for c in claims_by_item.get(it_id, []):
                c_pid = c.get("participant_id") if isinstance(c, dict) else getattr(c, "participant_id", None)
                if c_pid == pid:
                    qty = c.get("quantity", 1) if isinstance(c, dict) else getattr(c, "quantity", 1)
                    qty_str = f"{qty[0]}/{qty[1]}" if isinstance(qty, list) and len(qty) == 2 else str(qty)
                    p_claimed.append(f"{it.get('label', it_id)} ({qty_str})")
        claimed_str = ", ".join(p_claimed) if p_claimed else "None"

        owed_sen = consumption_by_part.get(pid, 0)
        base_sen = base_shares.get(pid, owed_sen)
        adj_sen = adj_shares.get(pid, 0)
        if isinstance(raw_con, dict) and isinstance(raw_con.get(pid), dict):
            base_sen = raw_con[pid].get("base_sen", base_sen)
            adj_sen = raw_con[pid].get("adjustments_sen", adj_sen)
            owed_sen = raw_con[pid].get("total_sen", owed_sen)

        apportionment_rows.append({
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell(pname),
                    text_cell(claimed_str),
                    text_cell(format_sen(base_sen)),
                    text_cell(format_sen(adj_sen)),
                    text_cell(format_sen(owed_sen)),
                ]
            },
        })

    if rollup_part_keys:
        other_sen = sum(consumption_by_part.get(r_pid, 0) for r_pid in rollup_part_keys)
        apportionment_rows.append({
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell(f"Other diners ({len(rollup_part_keys)} participants)"),
                    text_cell(f"{len(rollup_part_keys)} diners"),
                    text_cell("-"),
                    text_cell("-"),
                    text_cell(format_sen(other_sen)),
                ]
            },
        })

    apportionment_table = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 5,
            "has_column_header": True,
            "has_row_header": False,
            "children": apportionment_rows,
        },
    }

    # 3. Receipt Items Breakdown Heading & Table
    items_heading = {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "📋 Receipt Items Breakdown"}}],
        },
    }

    items_rows = [
        # Table Header Row
        {
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell("Item"),
                    text_cell("Qty"),
                    text_cell("Unit Price (MYR)"),
                    text_cell("Line Total (MYR)"),
                    text_cell("Split Among"),
                ]
            },
        }
    ]

    # Fixed blocks so far:
    # 5 top-level non-table (Callout, Apport Heading, Items Heading, Divider, Audit Paragraph)
    # + 1 reserved for optional image_block (guaranteeing total compact blocks <= 40 even if appended later)
    # + 1 (Apportionment Table) + len(apportionment_rows)
    # + 1 (Items Table) + 1 (Items Header Row)
    used_blocks = 6 + 1 + len(apportionment_rows) + 1 + 1
    remaining_item_budget = max(1, MAX_COMPACT_BLOCKS - used_blocks)

    if len(items) > remaining_item_budget:
        display_items_count = max(1, remaining_item_budget - 1)
        display_items = items[:display_items_count]
        rollup_items = items[display_items_count:]
    else:
        display_items = items
        rollup_items = []

    for it in display_items:
        it_id = it.get("id")
        label = it.get("label", it_id)
        qty = it.get("quantity", 1)
        qty_str = f"{qty[0]}/{qty[1]}" if isinstance(qty, list) and len(qty) == 2 else str(qty)
        line_sen = it.get("line_sen", 0)
        unit_sen = it.get("unit_price_sen")

        # Find who split this item
        splitters = []
        for c in claims_by_item.get(it_id, []):
            c_pid = c.get("participant_id") if isinstance(c, dict) else getattr(c, "participant_id", None)
            c_name = participants.get(c_pid, {}).get("name", c_pid)
            c_qty = c.get("quantity", 1) if isinstance(c, dict) else getattr(c, "quantity", 1)
            c_qty_str = f"{c_qty[0]}/{c_qty[1]}" if isinstance(qty, list) and len(qty) == 2 else str(c_qty)
            splitters.append(f"{c_name} ({c_qty_str})")
        split_str = ", ".join(splitters) if splitters else ("Complimentary" if line_sen == 0 else "Unclaimed")

        items_rows.append({
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell(label),
                    text_cell(qty_str),
                    text_cell(format_sen(unit_sen) if unit_sen is not None else "-"),
                    text_cell(format_sen(line_sen)),
                    text_cell(split_str),
                ]
            },
        })

    if rollup_items:
        rollup_sen = sum(it.get("line_sen", 0) for it in rollup_items)
        items_rows.append({
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell(f"Other receipt items ({len(rollup_items)} items)"),
                    text_cell(str(len(rollup_items))),
                    text_cell("-"),
                    text_cell(format_sen(rollup_sen)),
                    text_cell("Group"),
                ]
            },
        })

    items_table = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 5,
            "has_column_header": True,
            "has_row_header": False,
            "children": items_rows,
        },
    }

    # 4. Divider & Audit Note
    divider_block = {"object": "block", "type": "divider", "divider": {}}
    audit_paragraph = {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": "SettleTable Export • Contract settletable-command-v1 • Cent-conserving apportionment"
                    },
                    "annotations": {"italic": True, "color": "gray"},
                }
            ]
        },
    }

    blocks = [
        callout_block,
        apportionment_heading,
        apportionment_table,
        items_heading,
        items_table,
    ]
    if image_block is not None:
        blocks.append(image_block)
    blocks.extend([
        divider_block,
        audit_paragraph,
    ])
    assert count_notion_blocks(blocks) <= MAX_COMPACT_BLOCKS, f"Compact blocks {count_notion_blocks(blocks)} exceeds {MAX_COMPACT_BLOCKS}"
    return blocks


def format_full_meal_blocks(
    meal_id: str,
    snapshot: dict[str, Any],
    image_block: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Format full, unconstrained Notion blocks listing every participant and receipt item without rollup."""
    receipt = snapshot.get("receipt") or {}
    calc = snapshot.get("calculation") or {}
    participants = {p["id"]: p for p in snapshot.get("participants", [])}
    items = receipt.get("items", [])
    adjustments = receipt.get("adjustments", [])
    revision = snapshot.get("revision", 0)

    raw_claims = snapshot.get("claims", [])
    claims_by_item: dict[str, list[dict[str, Any]]] = {}
    if isinstance(raw_claims, dict):
        claims_by_item = raw_claims
    elif isinstance(raw_claims, (list, tuple)):
        for c in raw_claims:
            if isinstance(c, dict):
                claims_by_item.setdefault(c.get("item_id"), []).append(c)
            elif hasattr(c, "item_id"):
                claims_by_item.setdefault(c.item_id, []).append({
                    "item_id": c.item_id,
                    "participant_id": c.participant_id,
                    "quantity": c.quantity,
                })

    raw_con = calc.get("consumption", [])
    consumption_by_part: dict[str, int] = {}
    if isinstance(raw_con, dict):
        for k, v in raw_con.items():
            consumption_by_part[k] = v.get("total_sen", v.get("sen", 0)) if isinstance(v, dict) else int(v)
    elif isinstance(raw_con, (list, tuple)):
        for entry in raw_con:
            if isinstance(entry, dict):
                pid = entry.get("participant_id")
                if pid:
                    consumption_by_part[pid] = entry.get("sen", 0)
            elif hasattr(entry, "participant_id"):
                consumption_by_part[entry.participant_id] = entry.sen

    base_shares: dict[str, int] = {}
    for src in calc.get("items", []):
        shares = src.get("shares", []) if isinstance(src, dict) else getattr(src, "shares", [])
        for sh in shares:
            sh_pid = sh.get("participant_id") if isinstance(sh, dict) else getattr(sh, "participant_id", None)
            sh_sen = sh.get("sen", 0) if isinstance(sh, dict) else getattr(sh, "sen", 0)
            if sh_pid:
                base_shares[sh_pid] = base_shares.get(sh_pid, 0) + sh_sen

    adj_shares: dict[str, int] = {}
    for src in calc.get("adjustments", []):
        shares = src.get("shares", []) if isinstance(src, dict) else getattr(src, "shares", [])
        for sh in shares:
            sh_pid = sh.get("participant_id") if isinstance(sh, dict) else getattr(sh, "participant_id", None)
            sh_sen = sh.get("sen", 0) if isinstance(sh, dict) else getattr(sh, "sen", 0)
            if sh_pid:
                adj_shares[sh_pid] = adj_shares.get(sh_pid, 0) + sh_sen

    total_sen = receipt.get("total_sen", 0)
    subtotal_sen = receipt.get("subtotal_sen", 0)
    included_tax_sen = receipt.get("included_tax_sen", 0)

    adj_lines = []
    for adj in adjustments:
        adj_lines.append(f"• {adj.get('label', adj.get('kind', 'Adjustment'))}: {format_sen(adj.get('amount_sen', 0))}")
    if included_tax_sen:
        adj_lines.append(f"• Included Tax (SST): {format_sen(included_tax_sen)} (tax-inclusive)")
    adj_text = "\n".join(adj_lines) if adj_lines else "None"

    part_names = [p.get("name", pid) for pid, p in participants.items()]
    part_str = ", ".join(part_names) if part_names else "None"

    receipt_digest = snapshot.get("receipt_digest") or "unsealed"
    calc_digest = snapshot.get("calculation_digest") or "uncalculated"

    callout_content = (
        f"Meal ID: {meal_id} | Finalized Revision: {revision}\n"
        f"Grand Total: {format_sen(total_sen)} (Subtotal: {format_sen(subtotal_sen)})\n"
        f"Adjustments:\n{adj_text}\n"
        f"Participants ({len(participants)}): {part_str}\n"
        f"Receipt Digest: {receipt_digest[:16]}... | Calculation Digest: {calc_digest[:16]}..."
    )

    callout_block = {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "🧾"},
            "rich_text": [{"type": "text", "text": {"content": callout_content}}],
        },
    }

    apportionment_heading = {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "👥 Diner Apportionment"}}],
        },
    }

    apportionment_rows = [
        {
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell("Diner"),
                    text_cell("Items Claimed"),
                    text_cell("Base (MYR)"),
                    text_cell("Adjustments (MYR)"),
                    text_cell("Total Owed (MYR)"),
                ]
            },
        }
    ]

    for pid, pdata in participants.items():
        pname = pdata.get("name", pid)
        if pdata.get("is_organizer") or pdata.get("organizer"):
            pname += " (Organizer)"

        p_claimed = []
        for it in items:
            it_id = it.get("id")
            for c in claims_by_item.get(it_id, []):
                c_pid = c.get("participant_id") if isinstance(c, dict) else getattr(c, "participant_id", None)
                if c_pid == pid:
                    qty = c.get("quantity", 1) if isinstance(c, dict) else getattr(c, "quantity", 1)
                    qty_str = f"{qty[0]}/{qty[1]}" if isinstance(qty, list) and len(qty) == 2 else str(qty)
                    p_claimed.append(f"{it.get('label', it_id)} ({qty_str})")
        claimed_str = ", ".join(p_claimed) if p_claimed else "None"

        owed_sen = consumption_by_part.get(pid, 0)
        base_sen = base_shares.get(pid, owed_sen)
        adj_sen = adj_shares.get(pid, 0)
        if isinstance(raw_con, dict) and isinstance(raw_con.get(pid), dict):
            base_sen = raw_con[pid].get("base_sen", base_sen)
            adj_sen = raw_con[pid].get("adjustments_sen", adj_sen)
            owed_sen = raw_con[pid].get("total_sen", owed_sen)

        apportionment_rows.append({
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell(pname),
                    text_cell(claimed_str),
                    text_cell(format_sen(base_sen)),
                    text_cell(format_sen(adj_sen)),
                    text_cell(format_sen(owed_sen)),
                ]
            },
        })

    apportionment_table = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 5,
            "has_column_header": True,
            "has_row_header": False,
            "children": apportionment_rows,
        },
    }

    items_heading = {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "📋 Receipt Items Breakdown"}}],
        },
    }

    items_rows = [
        {
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell("Item"),
                    text_cell("Qty"),
                    text_cell("Unit Price (MYR)"),
                    text_cell("Line Total (MYR)"),
                    text_cell("Split Among"),
                ]
            },
        }
    ]

    for it in items:
        it_id = it.get("id")
        label = it.get("label", it_id)
        qty = it.get("quantity", 1)
        qty_str = f"{qty[0]}/{qty[1]}" if isinstance(qty, list) and len(qty) == 2 else str(qty)
        line_sen = it.get("line_sen", 0)
        unit_sen = it.get("unit_price_sen")

        splitters = []
        for c in claims_by_item.get(it_id, []):
            c_pid = c.get("participant_id") if isinstance(c, dict) else getattr(c, "participant_id", None)
            c_name = participants.get(c_pid, {}).get("name", c_pid)
            c_qty = c.get("quantity", 1) if isinstance(c, dict) else getattr(c, "quantity", 1)
            c_qty_str = f"{c_qty[0]}/{c_qty[1]}" if isinstance(qty, list) and len(qty) == 2 else str(c_qty)
            splitters.append(f"{c_name} ({c_qty_str})")
        split_str = ", ".join(splitters) if splitters else ("Complimentary" if line_sen == 0 else "Unclaimed")

        items_rows.append({
            "object": "block",
            "type": "table_row",
            "table_row": {
                "cells": [
                    text_cell(label),
                    text_cell(qty_str),
                    text_cell(format_sen(unit_sen) if unit_sen is not None else "-"),
                    text_cell(format_sen(line_sen)),
                    text_cell(split_str),
                ]
            },
        })

    items_table = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 5,
            "has_column_header": True,
            "has_row_header": False,
            "children": items_rows,
        },
    }

    divider_block = {"object": "block", "type": "divider", "divider": {}}
    audit_paragraph = {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": "SettleTable Export • Contract settletable-command-v1 • Cent-conserving apportionment"
                    },
                    "annotations": {"italic": True, "color": "gray"},
                }
            ]
        },
    }

    blocks = [
        callout_block,
        apportionment_heading,
        apportionment_table,
        items_heading,
        items_table,
    ]
    if image_block is not None:
        blocks.append(image_block)
    blocks.extend([
        divider_block,
        audit_paragraph,
    ])
    return blocks


def export_finalized_meal(
    client: NotionClientProtocol,
    meal_id: str,
    snapshot: dict[str, Any],
    config: NotionExportConfig,
) -> NotionExportResult:
    """Export a finalized SettleTable meal snapshot to Notion.
    
    Delivery Semantics: At-least-once with pre-creation title reconciliation.
    Does not claim exactly-once delivery across non-transactional REST APIs.
    """
    if not snapshot.get("finalized"):
        return NotionExportResult(
            ok=False,
            status="failed",
            error="meal_not_finalized",
        )

    clean_parent_id = config.parent_id.strip()
    if not NOTION_ID_REGEX.match(clean_parent_id):
        raise NotionValidationError(f"Invalid Notion parent_id UUID: '{clean_parent_id}'")

    if config.include_receipt_photo and not config.receipt_photo_data:
        return NotionExportResult(
            ok=False,
            status="failed",
            error="missing_receipt_photo_data",
        )

    receipt = snapshot.get("receipt") or {}
    merchant = receipt.get("merchant") or meal_id
    title_text = f"🍽️ SettleTable: {merchant} ({meal_id})"

    existing_id = config.existing_page_id
    existing_url = f"https://notion.so/{existing_id.replace('-', '')}" if existing_id else None

    # Pre-creation title reconciliation: check if page already exists under page parent
    # to prevent duplicate pages if a previous network response was lost
    if not existing_id and config.parent_type == "page_id":
        try:
            existing_blocks = client.query_block_children(config.token, clean_parent_id)
            for blk in existing_blocks:
                if blk.get("type") == "child_page":
                    child_info = blk.get("child_page") or {}
                    if child_info.get("title") == title_text:
                        existing_id = blk.get("id")
                        existing_url = f"https://notion.so/{existing_id.replace('-', '')}" if existing_id else None
                        break
        except (NotionAuthError, NotionValidationError, NotionNotFoundError, NotionRateLimitError):
            raise
        except Exception:
            pass

    if existing_id:
        if not config.include_receipt_photo:
            return NotionExportResult(
                ok=True,
                status="already_exported",
                page_id=existing_id,
                page_url=existing_url,
                blocks_created=0,
            )

        # Organizer requested photo inclusion for an existing page.
        # Check if the existing page already contains an image block.
        try:
            page_blocks = client.query_block_children(config.token, existing_id)
            has_image = any(blk.get("type") == "image" for blk in page_blocks)
            if has_image:
                return NotionExportResult(
                    ok=True,
                    status="already_exported",
                    page_id=existing_id,
                    page_url=existing_url,
                    blocks_created=0,
                )

            # Upload receipt photo and append image block in-place
            file_bytes, filename, content_type = config.receipt_photo_data
            file_upload_id = client.upload_file(
                token=config.token,
                filename=filename,
                content_type=content_type,
                file_bytes=file_bytes,
            )
            image_block = {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "file_upload",
                    "file_upload": {
                        "id": file_upload_id,
                    },
                },
            }
            client.append_block_children(config.token, existing_id, [image_block])
            return NotionExportResult(
                ok=True,
                status="completed",
                page_id=existing_id,
                page_url=existing_url,
                blocks_created=1,
            )
        except (NotionAuthError, NotionValidationError, NotionNotFoundError, NotionRateLimitError):
            raise
        except Exception as err:
            return NotionExportResult(
                ok=False,
                status="failed",
                error=f"append_photo_failed: {str(err)}"[:128],
            )

    image_block = None
    if config.include_receipt_photo and config.receipt_photo_data:
        file_bytes, filename, content_type = config.receipt_photo_data
        file_upload_id = client.upload_file(
            token=config.token,
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
        )
        image_block = {
            "object": "block",
            "type": "image",
            "image": {
                "type": "file_upload",
                "file_upload": {
                    "id": file_upload_id,
                },
            },
        }

    parent_key = "database_id" if config.parent_type == "database_id" else "page_id"
    parent = {parent_key: clean_parent_id}

    properties = format_meal_properties(meal_id, snapshot, parent_type=config.parent_type)
    if config.mode == "full":
        children = format_full_meal_blocks(meal_id, snapshot, image_block=image_block)
    else:
        children = format_compact_meal_blocks(meal_id, snapshot, image_block=image_block)

    page_obj = client.create_page(
        token=config.token,
        parent=parent,
        properties=properties,
        children=children,
    )

    page_id = page_obj.get("id")
    page_url = page_obj.get("url") or (f"https://notion.so/{page_id.replace('-', '')}" if page_id else None)
    blocks_count = count_notion_blocks(children)

    return NotionExportResult(
        ok=True,
        status="completed",
        page_id=page_id,
        page_url=page_url,
        blocks_created=blocks_count,
    )
