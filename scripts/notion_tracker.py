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

notion = Client(auth=NOTION_TOKEN, notion_version="2022-06-28")


def create_entry(title, company, url, status="Applied", qa=None, variant=None):
    """Create a new application entry in the Applications database."""
    print(f"Creating entry: {title} at {company}...", file=sys.stderr)

    # Actual DB schema (discovered via API):
    # Company: title, Status: select, Job Title: select,
    # URL: url, Date applied: date, Tailored Resume: files, Q/A: rich_text
    # Resume Variant: select (optional - for A/B testing resume layouts)
    # Core properties (required)
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
    }

    # Date property
    date_value = {"date": {"start": date.today().isoformat()}}
    date_prop_names = ["Date"]

    # Optional properties (may not exist in all DB schemas)
    optional_props = {}

    if qa:
        # Notion rich_text has a 2000 char limit per block; split if needed
        qa_blocks = []
        for i in range(0, len(qa), 2000):
            qa_blocks.append({"text": {"content": qa[i:i+2000]}})
        properties["Q/A"] = {"rich_text": qa_blocks}

    # Add variant to optional props if provided
    if variant:
        optional_props["Resume Variant"] = {"select": {"name": variant}}

    def _create_page(props):
        return notion.pages.create(
            parent={"database_id": APPLICATIONS_DB_ID},
            properties=props,
        )

    # Try each date property name until one works
    for date_name in date_prop_names:
        all_props = {**properties, **optional_props, date_name: date_value}
        try:
            response = _create_page(all_props)
            print(f"Created: {response['id']}", file=sys.stderr)
            return {
                "success": True,
                "page_id": response["id"],
                "url": response.get("url", ""),
                "title": title,
                "company": company,
            }
        except Exception as e:
            error_msg = str(e)
            if date_name in error_msg and "is not a property" in error_msg:
                continue  # Try next date name variation
            # Handle other optional prop errors (like Resume Variant)
            if "Resume Variant" in error_msg:
                optional_props.pop("Resume Variant", None)
                # Retry immediately with date but without Resume Variant
                response = _create_page({**properties, date_name: date_value})
                print(f"Created: {response['id']}", file=sys.stderr)
                return {
                    "success": True,
                    "page_id": response["id"],
                    "url": response.get("url", ""),
                    "title": title,
                    "company": company,
                }
            raise

    # Final attempt without any date property
    print("No matching date property in Notion DB, creating without date...", file=sys.stderr)
    response = _create_page({**properties, **optional_props})
    print(f"Created: {response['id']}", file=sys.stderr)
    return {
        "success": True,
        "page_id": response["id"],
        "url": response.get("url", ""),
        "title": title,
        "company": company,
    }


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
