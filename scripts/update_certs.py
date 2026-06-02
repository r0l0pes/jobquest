#!/usr/bin/env python3
"""Update certifications in Notion master resume pages.

Adds: 2026 -- Introduction to Subagents, Anthropic
Removes: 2019 – Blockchain Essentials, IBM
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTION_TOKEN

# Resume page IDs (from web_ui.py)
RESUME_IDS = {
    "Growth PM": "2f40fd98-227b-8083-a78f-c61c38e55a12",
    "Generalist": "30b0fd98-227b-8195-9649-fe5287cb8cb9",
    # AI-PM uses Growth PM's page
}

ADD_ITEM = "2026 -- Introduction to Subagents, Anthropic"
REMOVE_ITEM = "2019 – Blockchain Essentials, IBM"

from notion_client import Client

notion = Client(auth=NOTION_TOKEN, notion_version="2022-06-28")


def get_block_text(block):
    """Extract plain text from a block."""
    block_type = block.get("type", "")
    if not block_type:
        return ""
    content = block.get(block_type, {})
    rich_text = content.get("rich_text", [])
    return "".join(t["plain_text"] for t in rich_text)


def update_certifications(page_id, label):
    """Update certifications in a Notion page."""
    print(f"\nProcessing {label} (page {page_id})...", file=sys.stderr)

    # Get all blocks
    blocks = []
    cursor = None
    while True:
        params = {"block_id": page_id, "page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        response = notion.blocks.children.list(**params)
        blocks.extend(response["results"])
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    print(f"  Found {len(blocks)} blocks", file=sys.stderr)

    # Find certifications section
    in_certifications = False
    heading_id = None
    cert_blocks = []

    for i, block in enumerate(blocks):
        text = get_block_text(block)
        btype = block.get("type", "")

        if btype == "heading_2" and "certif" in text.lower():
            heading_id = block["id"]
            in_certifications = True
            continue

        if in_certifications:
            if btype == "bulleted_list_item":
                cert_blocks.append(block)
            elif btype == "heading_2" or btype == "heading_1" or btype == "divider":
                break

    if not heading_id:
        print(f"  [yellow]Certifications heading not found![/yellow]", file=sys.stderr)
        print(f"  [dim]Blocks after scanner:[/dim]", file=sys.stderr)
        for b in blocks:
            t = get_block_text(b)
            if t:
                print(f"    [{b.get('type')}] {t[:80]}", file=sys.stderr)
        return False

    print(f"  Found {len(cert_blocks)} certification items", file=sys.stderr)
    for b in cert_blocks:
        print(f"    - {get_block_text(b)}", file=sys.stderr)

    # Rebuild certifications in correct order
    # Strategy: delete all cert bullets, then recreate them in order
    new_order = [
        ADD_ITEM,
        "2026 -- Claude Code in Action, Anthropic",
        "2026 -- AI Fluency Framework & Foundations, Anthropic",
        "2021 -- Certified Scrum Product Owner®, Scrum Alliance",
        "2020 – Enterprise Design Thinking: Team Essentials for AI, IBM",
        "2020 – Design Sprint Masterclass, AJ&Smart",
    ]

    current_texts = [get_block_text(b) for b in cert_blocks]
    current_order = [t for t in current_texts if t]

    if current_order == new_order:
        print(f"  Already up to date.", file=sys.stderr)
        return True

    # Delete all existing cert bullets
    for b in cert_blocks:
        try:
            notion.blocks.delete(block_id=b["id"])
        except Exception:
            pass
    print(f"  Deleted {len(cert_blocks)} existing items", file=sys.stderr)

    # Rebuild: append new bullets right after the certifications heading
    for i, item_text in enumerate(new_order):
        after_block = heading_id if i == 0 else None  # first one after heading, rest auto-follow
        kwargs = {"block_id": page_id}
        if after_block:
            kwargs["after"] = after_block
        notion.blocks.children.append(
            children=[{
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": item_text}}]
                }
            }],
            **kwargs,
        )
        print(f"    + {item_text[:60]}...", file=sys.stderr)

    print(f"  [green]Done.[/green]", file=sys.stderr)
    return True


def main():
    if not NOTION_TOKEN:
        print("ERROR: NOTION_TOKEN not set in .env", file=sys.stderr)
        sys.exit(1)

    success = True
    for label, page_id in RESUME_IDS.items():
        try:
            update_certifications(page_id, label)
        except Exception as e:
            print(f"  [red]Error on {label}: {e}[/red]", file=sys.stderr)
            success = False

    if success:
        print("\n[green]All Notion resume pages updated.[/green]", file=sys.stderr)
    else:
        print("\n[yellow]Some updates failed — check errors above.[/yellow]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
