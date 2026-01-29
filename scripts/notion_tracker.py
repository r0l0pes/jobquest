#!/usr/bin/env python3
"""Track job applications in Notion. Outputs JSON to stdout, status to stderr."""

import sys
import os
import json
import argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTION_TOKEN, APPLICATIONS_DB_ID
from notion_client import Client

notion = Client(auth=NOTION_TOKEN)


def create_entry(title, company, url, status="Applied"):
    """Create a new application entry in the Applications database."""
    print(f"Creating entry: {title} at {company}...", file=sys.stderr)

    # Actual DB schema (discovered via API):
    # Company: title, Status: select, Job Title: select,
    # URL: url, Date applied: date, Tailored Resume: files
    properties = {
        "Company": {
            "title": [{"text": {"content": company}}]
        },
        "Status": {
            "select": {"name": status}
        },
        "Job Title": {
            "select": {"name": title}
        },
        "URL": {
            "url": url
        },
        "Date applied": {
            "date": {"start": date.today().isoformat()}
        },
    }

    response = notion.pages.create(
        parent={"database_id": APPLICATIONS_DB_ID},
        properties=properties,
    )

    result = {
        "success": True,
        "page_id": response["id"],
        "url": response.get("url", ""),
        "title": title,
        "company": company,
    }
    print(f"Created: {response['id']}", file=sys.stderr)
    return result


def update_entry(page_id, **kwargs):
    """Update an existing application entry."""
    print(f"Updating entry {page_id}...", file=sys.stderr)

    properties = {}

    if "status" in kwargs and kwargs["status"]:
        properties["Status"] = {"select": {"name": kwargs["status"]}}

    if not properties:
        return {"success": False, "error": "No properties to update"}

    response = notion.pages.update(page_id=page_id, properties=properties)

    result = {
        "success": True,
        "page_id": response["id"],
    }
    print(f"Updated: {response['id']}", file=sys.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description="Track applications in Notion")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create command
    create_parser = subparsers.add_parser("create", help="Create new application entry")
    create_parser.add_argument("--title", required=True, help="Job title")
    create_parser.add_argument("--company", required=True, help="Company name")
    create_parser.add_argument("--url", required=True, help="Job posting URL")
    create_parser.add_argument("--status", default="Applied", help="Application status")

    # Update command
    update_parser = subparsers.add_parser("update", help="Update existing entry")
    update_parser.add_argument("--page-id", required=True, help="Notion page ID")
    update_parser.add_argument("--status", help="New status")

    args = parser.parse_args()

    if args.command == "create":
        result = create_entry(
            title=args.title,
            company=args.company,
            url=args.url,
            status=args.status,
        )
    elif args.command == "update":
        result = update_entry(
            page_id=args.page_id,
            status=args.status,
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
