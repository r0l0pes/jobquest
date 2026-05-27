#!/usr/bin/env python3
"""Replace a specific experience section in a Notion resume page.

Usage:
    python notion_update_resume.py <page_id> --dry-run
    python notion_update_resume.py <page_id> --apply
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTION_TOKEN
from notion_client import Client

notion = Client(auth=NOTION_TOKEN, notion_version="2022-06-28")

# --- Configuration: what to replace and with what ---
OLD_HEADING_TEXT = "World Food Programme"

NEW_HEADING = "Postscript, Senior Product Manager — Growth & AI"
NEW_DATE_LINE = "Jul 2024 – Apr 2026 | Remote"
NEW_BULLETS = [
    "Led product development for an AI-powered message optimization engine, solving the tension between sending more SMS messages and keeping every one on-brand. Used predictive analytics and generative AI to test hundreds of variants per automation, driving a 28% increase in earnings-per-message for Shopify merchants through continuous model learning.",
    "Redesigned subscriber acquisition for Shopify merchants around SMS compliance, implementing one-tap mobile opt-in. Increased opt-in conversion by 32% and reduced acquisition cost by 18% through repositioned incentive timing and simplified consent language.",
    "Built analytics instrumentation to measure SMS program health across 18,000+ merchant accounts, establishing earnings-per-message and click-through rate as primary KPIs. Identified engagement decay patterns unique to SMS versus email channels, translating insights into re-engagement automation roadmap priorities presented to leadership.",
]


def fetch_top_level_blocks(page_id):
    """Fetch all top-level blocks (children of the page)."""
    blocks = []
    cursor = None
    while True:
        params = {"block_id": page_id, "page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = notion.blocks.children.list(**params)
        blocks.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return blocks


def find_block_index(blocks, predicate):
    for i, b in enumerate(blocks):
        if predicate(b):
            return i
    return -1


def main():
    if len(sys.argv) < 2:
        print("Usage: notion_update_resume.py <page_id> [--dry-run | --apply]", file=sys.stderr)
        sys.exit(1)

    page_id = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    apply = "--apply" in sys.argv

    if not apply and not dry_run:
        dry_run = True

    print(f"Fetching blocks for page {page_id}...")
    blocks = fetch_top_level_blocks(page_id)

    # Find the heading we want to replace
    old_heading_idx = find_block_index(
        blocks,
        lambda b: b.get("type") == "heading_3" and any(
            OLD_HEADING_TEXT in t.get("plain_text", "")
            for t in b.get("heading_3", {}).get("rich_text", [])
        )
    )

    if old_heading_idx == -1:
        print(f"ERROR: Could not find heading matching '{OLD_HEADING_TEXT}'", file=sys.stderr)
        sys.exit(1)

    old_heading_block = blocks[old_heading_idx]
    old_heading_id = old_heading_block["id"]

    # Find bullet blocks immediately after the heading
    bullet_ids_to_delete = []
    for i in range(old_heading_idx + 1, len(blocks)):
        b = blocks[i]
        btype = b.get("type")
        if btype in ("heading_3", "heading_2", "heading_1", "divider"):
            break
        if btype in ("bulleted_list_item", "numbered_list_item", "paragraph"):
            bullet_ids_to_delete.append(b["id"])

    print(f"Found WFP heading at index {old_heading_idx}: {old_heading_id}")
    print(f"Found {len(bullet_ids_to_delete)} blocks to delete after it")

    # Find the "Experience" heading_2 to append after
    exp_idx = find_block_index(
        blocks,
        lambda b: b.get("type") == "heading_2" and any(
            "Experience" in t.get("plain_text", "")
            for t in b.get("heading_2", {}).get("rich_text", [])
        )
    )
    if exp_idx == -1:
        print("ERROR: Could not find 'Experience' heading_2", file=sys.stderr)
        sys.exit(1)
    exp_id = blocks[exp_idx]["id"]
    print(f"Found 'Experience' heading_2 at index {exp_idx}: {exp_id}")

    new_children = [
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": NEW_HEADING}}]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": NEW_DATE_LINE}}]
            },
        },
    ]
    for bullet in NEW_BULLETS:
        new_children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": bullet}}]
            },
        })

    if dry_run:
        print("\n--- DRY RUN ---")
        print(f"Would DELETE: {old_heading_id}")
        for bid in bullet_ids_to_delete:
            print(f"Would DELETE: {bid}")
        print(f"\nWould APPEND {len(new_children)} blocks after {exp_id}")
        for child in new_children:
            print(f"  - {child['type']}: {child[child['type']]['rich_text'][0]['text']['content'][:60]}...")
        print("\nPass --apply to execute.")
        return

    # Apply changes
    if apply:
        print("\n--- APPLYING ---")
        print(f"Deleting {old_heading_id}...")
        notion.blocks.delete(block_id=old_heading_id)
        for bid in bullet_ids_to_delete:
            print(f"Deleting {bid}...")
            notion.blocks.delete(block_id=bid)

        print(f"Appending {len(new_children)} new blocks after {exp_id}...")
        notion.blocks.children.append(
            block_id=page_id,
            after=exp_id,
            children=new_children,
        )
        print("Done.")


if __name__ == "__main__":
    main()
