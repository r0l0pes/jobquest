#!/usr/bin/env python3
"""
Consolidated Notion DB management utility.
- inspect: Show current DB schema
- repair: Add missing properties to Applications DB
- discover: Find all databases in workspace
Outputs JSON to stdout, status to stderr.
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTION_TOKEN, APPLICATIONS_DB_ID
from notion_client import Client

notion = Client(auth=NOTION_TOKEN)

# Actual schema for Applications DB (discovered via API)
EXPECTED_PROPERTIES = {
    "Company": {"type": "title"},
    "Status": {
        "type": "select",
        "options": ["Applied", "Interview", "Offer", "Rejected"],
    },
    "Job Title": {"type": "select"},
    "URL": {"type": "url"},
    "Date applied": {"type": "date"},
    "Tailored Resume": {"type": "files"},
}


def inspect_db(db_id):
    """Show the current schema of a database."""
    print(f"Inspecting database {db_id}...", file=sys.stderr)

    db = notion.databases.retrieve(database_id=db_id)
    title_parts = db.get("title", [])
    title = "".join(t["plain_text"] for t in title_parts)

    properties = {}
    for prop_name, prop_val in db.get("properties", {}).items():
        prop_info = {"type": prop_val["type"]}

        if prop_val["type"] == "select":
            prop_info["options"] = [
                opt["name"] for opt in prop_val.get("select", {}).get("options", [])
            ]
        elif prop_val["type"] == "multi_select":
            prop_info["options"] = [
                opt["name"]
                for opt in prop_val.get("multi_select", {}).get("options", [])
            ]

        properties[prop_name] = prop_info

    result = {
        "id": db_id,
        "title": title,
        "url": db.get("url", ""),
        "properties": properties,
    }

    return result


def repair_db(db_id):
    """Add missing properties to the Applications database."""
    print(f"Repairing database {db_id}...", file=sys.stderr)

    db = notion.databases.retrieve(database_id=db_id)
    existing = set(db.get("properties", {}).keys())
    updates = {}
    added = []

    for prop_name, prop_spec in EXPECTED_PROPERTIES.items():
        if prop_name in existing:
            continue

        ptype = prop_spec["type"]
        if ptype == "title":
            # Title property already exists (every DB has one), might just have a different name
            continue
        elif ptype == "rich_text":
            updates[prop_name] = {"rich_text": {}}
        elif ptype == "url":
            updates[prop_name] = {"url": {}}
        elif ptype == "date":
            updates[prop_name] = {"date": {}}
        elif ptype == "select":
            options = [{"name": o} for o in prop_spec.get("options", [])]
            updates[prop_name] = {"select": {"options": options}}

        added.append(prop_name)

    if updates:
        notion.databases.update(database_id=db_id, properties=updates)
        print(f"Added properties: {added}", file=sys.stderr)
    else:
        print("No missing properties found.", file=sys.stderr)

    return {
        "success": True,
        "added": added,
        "already_existed": list(existing),
    }


def discover_databases():
    """Search for all databases the integration has access to."""
    print("Discovering databases...", file=sys.stderr)

    results = []
    cursor = None

    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        response = notion.search(**params)
        for item in response["results"]:
            if item.get("object") != "database":
                continue
            title_parts = item.get("title", [])
            title = "".join(t["plain_text"] for t in title_parts)

            props = {}
            for pname, pval in item.get("properties", {}).items():
                props[pname] = pval["type"]

            results.append({
                "id": item["id"],
                "title": title,
                "url": item.get("url", ""),
                "properties": props,
            })

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return {"databases": results, "count": len(results)}


def main():
    parser = argparse.ArgumentParser(description="Notion DB management utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Inspect
    inspect_parser = subparsers.add_parser("inspect", help="Show DB schema")
    inspect_parser.add_argument(
        "--db-id", default=APPLICATIONS_DB_ID, help="Database ID to inspect"
    )

    # Repair
    repair_parser = subparsers.add_parser("repair", help="Add missing properties")
    repair_parser.add_argument(
        "--db-id", default=APPLICATIONS_DB_ID, help="Database ID to repair"
    )

    # Discover
    subparsers.add_parser("discover", help="Find all databases in workspace")

    args = parser.parse_args()

    if args.command == "inspect":
        result = inspect_db(args.db_id)
    elif args.command == "repair":
        result = repair_db(args.db_id)
    elif args.command == "discover":
        result = discover_databases()

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
