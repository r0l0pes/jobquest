#!/usr/bin/env python3
"""Read content from Notion pages and databases. Outputs JSON to stdout, status to stderr."""

import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTION_TOKEN
from notion_client import Client

notion = Client(auth=NOTION_TOKEN)


def fetch_blocks(block_id, depth=0, max_depth=5):
    """Recursively fetch all blocks from a Notion page with pagination."""
    if depth > max_depth:
        return []

    blocks = []
    cursor = None

    while True:
        params = {"block_id": block_id, "page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        response = notion.blocks.children.list(**params)
        for block in response["results"]:
            block_type = block.get("type")
            if not block_type:
                continue

            content = block.get(block_type, {})
            rich_text = content.get("rich_text", [])
            text = "".join(t["plain_text"] for t in rich_text)

            entry = {
                "type": block_type,
                "text": text,
                "id": block["id"],
            }

            # Handle special block types
            if block_type == "child_page":
                entry["title"] = content.get("title", "")
            elif block_type == "child_database":
                entry["title"] = content.get("title", "")
            elif block_type in ("bulleted_list_item", "numbered_list_item", "to_do"):
                if block_type == "to_do":
                    entry["checked"] = content.get("checked", False)

            # Recurse into children
            if block.get("has_children"):
                entry["children"] = fetch_blocks(block["id"], depth + 1, max_depth)

            blocks.append(entry)

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return blocks


def read_page(page_id):
    """Read a Notion page: metadata + all block content."""
    print(f"Reading page {page_id}...", file=sys.stderr)

    # Get page metadata
    page = notion.pages.retrieve(page_id=page_id)
    title = ""
    for prop_name, prop_val in page.get("properties", {}).items():
        if prop_val.get("type") == "title":
            title = "".join(
                t["plain_text"] for t in prop_val.get("title", [])
            )
            break

    # Get all blocks
    blocks = fetch_blocks(page_id)

    result = {
        "id": page_id,
        "title": title,
        "url": page.get("url", ""),
        "blocks": blocks,
    }

    return result


def blocks_to_text(blocks, indent=0):
    """Convert blocks to plain text representation."""
    lines = []
    prefix = "  " * indent
    for block in blocks:
        btype = block["type"]
        text = block.get("text", "")

        if btype == "heading_1":
            lines.append(f"\n{prefix}# {text}")
        elif btype == "heading_2":
            lines.append(f"\n{prefix}## {text}")
        elif btype == "heading_3":
            lines.append(f"{prefix}### {text}")
        elif btype == "bulleted_list_item":
            lines.append(f"{prefix}- {text}")
        elif btype == "numbered_list_item":
            lines.append(f"{prefix}1. {text}")
        elif btype == "to_do":
            check = "x" if block.get("checked") else " "
            lines.append(f"{prefix}- [{check}] {text}")
        elif btype == "child_page":
            lines.append(f"{prefix}[Page: {block.get('title', '')}]")
        elif btype == "divider":
            lines.append(f"{prefix}---")
        elif text:
            lines.append(f"{prefix}{text}")

        if "children" in block:
            lines.extend(blocks_to_text(block["children"], indent + 1).split("\n"))

    return "\n".join(lines)


def read_database(db_id):
    """Read all entries from a Notion database with pagination."""
    print(f"Reading database {db_id}...", file=sys.stderr)

    entries = []
    cursor = None

    while True:
        params = {"database_id": db_id, "page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        response = notion.databases.query(**params)
        for page in response["results"]:
            entry = {"id": page["id"], "properties": {}}
            for prop_name, prop_val in page.get("properties", {}).items():
                ptype = prop_val.get("type")
                if ptype == "title":
                    entry["properties"][prop_name] = "".join(
                        t["plain_text"] for t in prop_val.get("title", [])
                    )
                elif ptype == "rich_text":
                    entry["properties"][prop_name] = "".join(
                        t["plain_text"] for t in prop_val.get("rich_text", [])
                    )
                elif ptype == "select":
                    sel = prop_val.get("select")
                    entry["properties"][prop_name] = sel["name"] if sel else None
                elif ptype == "multi_select":
                    entry["properties"][prop_name] = [
                        s["name"] for s in prop_val.get("multi_select", [])
                    ]
                elif ptype == "url":
                    entry["properties"][prop_name] = prop_val.get("url")
                elif ptype == "date":
                    d = prop_val.get("date")
                    entry["properties"][prop_name] = d["start"] if d else None
                elif ptype == "number":
                    entry["properties"][prop_name] = prop_val.get("number")
                elif ptype == "checkbox":
                    entry["properties"][prop_name] = prop_val.get("checkbox")
                elif ptype == "email":
                    entry["properties"][prop_name] = prop_val.get("email")
                elif ptype == "phone_number":
                    entry["properties"][prop_name] = prop_val.get("phone_number")
                else:
                    entry["properties"][prop_name] = f"[{ptype}]"

            entries.append(entry)

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return {"database_id": db_id, "entries": entries, "count": len(entries)}


def main():
    if len(sys.argv) < 3:
        print("Usage: notion_reader.py page <page_id> [--text]", file=sys.stderr)
        print("       notion_reader.py database <db_id>", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    target_id = sys.argv[2]
    text_mode = "--text" in sys.argv

    if command == "page":
        result = read_page(target_id)
        if text_mode:
            print(f"# {result['title']}\n")
            print(blocks_to_text(result["blocks"]))
        else:
            print(json.dumps(result, indent=2))
    elif command == "database":
        result = read_database(target_id)
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
