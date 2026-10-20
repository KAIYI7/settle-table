"""Export engine for generating Notion pages and blocks from finalized SettleTable meals."""
import re
from typing import Any

from .client import NOTION_ID_REGEX, NotionClientProtocol, NotionValidationError
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

    for pid, pdata in participants.items():
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

        # Find who split this item
        splitters = []
        for c in claims_by_item.get(it_id, []):
            c_pid = c.get("participant_id") if isinstance(c, dict) else getattr(c, "participant_id", None)
            c_name = participants.get(c_pid, {}).get("name", c_pid)
            c_qty = c.get("quantity", 1) if isinstance(c, dict) else getattr(c, "quantity", 1)
            c_qty_str = f"{c_qty[0]}/{c_qty[1]}" if isinstance(qty, list) and len(qty) == 2 else str(c_qty)
            splitters.append(f"{c_name} ({c_qty_str})")
        split_str = ", ".join(splitters) if splitters else "Unclaimed"

        items_rows.append({
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

    return [
        callout_block,
        apportionment_heading,
        apportionment_table,
        items_heading,
        items_table,
        divider_block,
        audit_paragraph,
    ]


def export_finalized_meal(
    client: NotionClientProtocol,
    meal_id: str,
    snapshot: dict[str, Any],
    config: NotionExportConfig,
) -> NotionExportResult:
    """Export a finalized SettleTable meal snapshot to Notion."""
    if not snapshot.get("finalized"):
        return NotionExportResult(
            ok=False,
            status="failed",
            error="meal_not_finalized",
        )

    clean_parent_id = config.parent_id.strip()
    if not NOTION_ID_REGEX.match(clean_parent_id):
        raise NotionValidationError(f"Invalid Notion parent_id UUID: '{clean_parent_id}'")

    parent_key = "database_id" if config.parent_type == "database_id" else "page_id"
    parent = {parent_key: clean_parent_id}

    properties = format_meal_properties(meal_id, snapshot, parent_type=config.parent_type)
    children = format_compact_meal_blocks(meal_id, snapshot)

    page_obj = client.create_page(
        token=config.token,
        parent=parent,
        properties=properties,
        children=children,
    )

    page_id = page_obj.get("id")
    page_url = page_obj.get("url") or (f"https://notion.so/{page_id.replace('-', '')}" if page_id else None)
    blocks_count = len(children)

    return NotionExportResult(
        ok=True,
        status="completed",
        page_id=page_id,
        page_url=page_url,
        blocks_created=blocks_count,
    )
