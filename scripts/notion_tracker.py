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


def create_entry(title, company, url, status="Applied", qa=None, variant=None):
    """Create a new application entry in the Applications database."""
    print(f"Creating entry: {title} at {company}...", file=sys.stderr)

    # Actual DB schema (discovered via API):
    # Company: title, Status: select, Job Title: select,
    # URL: url, Date applied: date, Tailored Resume: files, Q/A: rich_text
    # Resume Variant: select (optional - for A/B testing resume layouts)
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

    if qa:
        # Notion rich_text has a 2000 char limit per block; split if needed
        qa_blocks = []
        for i in range(0, len(qa), 2000):
            qa_blocks.append({"text": {"content": qa[i:i+2000]}})
        properties["Q/A"] = {"rich_text": qa_blocks}

    # Try to create entry, handling optional Resume Variant property
    def _create_page(props):
        return notion.pages.create(
            parent={"database_id": APPLICATIONS_DB_ID},
            properties=props,
        )

    # First attempt: with variant if provided
    if variant:
        properties["Resume Variant"] = {"select": {"name": variant}}
        try:
            response = _create_page(properties)
        except Exception as e:
            error_msg = str(e)
            # If Resume Variant property doesn't exist, retry without it
            if "Resume Variant" in error_msg or "is not a property" in error_msg:
                print("Resume Variant property not found in Notion DB, retrying without it...", file=sys.stderr)
                del properties["Resume Variant"]
                response = _create_page(properties)
            else:
                raise
    else:
        response = _create_page(properties)

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

    if "qa" in kwargs and kwargs["qa"]:
        qa = kwargs["qa"]
        qa_blocks = []
        for i in range(0, len(qa), 2000):
            qa_blocks.append({"text": {"content": qa[i:i+2000]}})
        properties["Q/A"] = {"rich_text": qa_blocks}

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
    create_parser.add_argument("--qa", help="Q&A content (questions and answers)")
    create_parser.add_argument("--variant", help="Resume variant for A/B testing (e.g., Tech-First, Exp-First)")

    # Update command
    update_parser = subparsers.add_parser("update", help="Update existing entry")
    update_parser.add_argument("--page-id", required=True, help="Notion page ID")
    update_parser.add_argument("--status", help="New status")
    update_parser.add_argument("--qa", help="Q&A content (questions and answers)")

    args = parser.parse_args()

    if args.command == "create":
        result = create_entry(
            title=args.title,
            company=args.company,
            url=args.url,
            status=args.status,
            qa=args.qa,
            variant=args.variant,
        )
    elif args.command == "update":
        result = update_entry(
            page_id=args.page_id,
            status=args.status,
            qa=args.qa,
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
