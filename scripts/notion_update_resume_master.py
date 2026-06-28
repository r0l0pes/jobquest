#!/usr/bin/env python3
"""
Update Notion master resume pages with:
1. Move certifications under the "Certifications" heading (from under Technical Proficiency)
2. Rename "AI-Assisted Workflows" → "AI-Assisted & Agentic Workflows" with new skills
3. Deduplicate cert entries (Growth PM has 3 copies)
4. Remove the stray divider after empty Certifications heading

Usage:
    python scripts/notion_update_resume_master.py [--dry-run | --apply]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTION_TOKEN
from notion_client import Client

notion = Client(auth=NOTION_TOKEN, notion_version="2022-06-28")

PAGES = {
    "growth_pm": {
        "id": "2f40fd98-227b-8083-a78f-c61c38e55a12",
        "name": "Master Resume (Growth PM)",
        "ai_workflows_block_id": "60b1e98f-009b-4383-bf29-b9f32e4cce83",
        "cert_heading_id": "f6ee6b51-0e19-4b96-987b-f22d06604a71",
        "cert_divider_id": "7deb471a-fb25-4282-b341-8091f2d5b039",
        "languages_heading_id": "81b40b4d-5765-4ef3-a3e3-d8b5ea634446",
        # New skills text for AI-Assisted & Agentic Workflows
        "new_ai_workflows_text": "AI-Assisted & Agentic Workflows: Claude Code, Cursor, LLM Workflows, Prompt Engineering, MCP (Model Context Protocol), Agentic Systems Design, Voice AI (NLP, STT/TTS), ML Use Case Discovery and Validation, Agent-Ready Systems Thinking",
        # Certs to add under Certifications heading (deduplicated set)
        "certs": [
            "2026 -- Introduction to Subagents, Anthropic",
            "2026 -- Claude Code in Action, Anthropic",
            "2026 -- AI Fluency Framework & Foundations, Anthropic",
            "2021 -- Certified Scrum Product Owner\u00ae, Scrum Alliance",
            "2020 \u2013 Enterprise Design Thinking: Team Essentials for AI, IBM",
            "2020 \u2013 Design Sprint Masterclass, AJ&Smart",
        ],
    },
    "generalist": {
        "id": "30b0fd98-227b-8195-9649-fe5287cb8cb9",
        "name": "Generalist PM Resume",
        "ai_workflows_block_id": "30b0fd98-227b-8185-b08e-e15b86ca0e5d",
        "cert_heading_id": "30b0fd98-227b-812c-8def-e2ea79d0da64",
        "cert_divider_id": "30b0fd98-227b-81f4-b38a-ddfe4f458fcb",
        "languages_heading_id": "30b0fd98-227b-8138-b21e-d747bb317b6b",
        "new_ai_workflows_text": "AI-Assisted & Agentic Workflows: Claude Code, GitHub Copilot, ChatGPT/Claude/Gemini, MCP (Model Context Protocol), Agentic Systems Design, Voice AI (NLP, STT/TTS), ML Use Case Discovery and Validation, Agent-Ready Systems Thinking",
        "certs": [
            "2026 -- Introduction to Subagents, Anthropic",
            "2026 -- Claude Code in Action, Anthropic",
            "2026 -- AI Fluency Framework & Foundations, Anthropic",
            "2021 -- Certified Scrum Product Owner\u00ae, Scrum Alliance",
            "2020 \u2013 Enterprise Design Thinking: Team Essentials for AI, IBM",
            "2020 \u2013 Design Sprint Masterclass, AJ&Smart",
        ],
    },
}


def fetch_all_blocks(page_id):
    """Fetch all top-level blocks (children of the page) with pagination."""
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


def find_block_index(blocks, block_id):
    for i, b in enumerate(blocks):
        if callable(block_id):
            if block_id(b):
                return i
        elif b["id"] == block_id:
            return i
    return -1


def update_page(page_config, dry_run=True):
    page_id = page_config["id"]
    name = page_config["name"]
    print(f"\n=== {name} ({page_id}) ===")

    blocks = fetch_all_blocks(page_id)
    print(f"  Total blocks: {len(blocks)}")

    # --- Step 1: Update AI-Assisted Workflows paragraph ---
    ai_block_id = page_config["ai_workflows_block_id"]
    ai_idx = find_block_index(blocks, ai_block_id)
    if ai_idx == -1:
        print(f"  ⚠️  AI Workflows block {ai_block_id} not found — might already be updated?")
    else:
        current_text = blocks[ai_idx].get("paragraph", {}).get("rich_text", [{}])[0].get("plain_text", "")
        print(f"  📝 AI Workflows:")
        print(f"     Before: {current_text[:80]}...")
        print(f"     After:  {page_config['new_ai_workflows_text'][:80]}...")

        if not dry_run:
            notion.blocks.update(
                block_id=ai_block_id,
                paragraph={
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": page_config["new_ai_workflows_text"]}
                    }]
                },
            )
            print(f"     ✅ Updated")

    # --- Step 2: Find cert bullet blocks under Technical Proficiency ---
    # Find the Technical Proficiency heading
    tp_idx = find_block_index(
        blocks,
        lambda b: b.get("type") == "heading_2"
        and any("Technical Proficiency" in t.get("plain_text", "")
                for t in b.get("heading_2", {}).get("rich_text", []))
    )

    if tp_idx == -1:
        print("  ⚠️  Technical Proficiency heading not found!")
        return

    # Collect cert bullets after Technical Proficiency (after the last paragraph under it)
    # First find the last non-bullet block under TP
    cert_bullets_to_delete = []
    for i in range(tp_idx + 1, len(blocks)):
        b = blocks[i]
        btype = b.get("type")
        if btype == "heading_2":
            break  # stop at next section
        if btype == "bulleted_list_item":
            text = b.get("bulleted_list_item", {}).get("rich_text", [{}])[0].get("plain_text", "")
            # Only grab cert-like bullets (have year in them)
            if any(year in text for year in ["2026", "2021", "2020"]):
                cert_bullets_to_delete.append(b)

    print(f"  🎯 Found {len(cert_bullets_to_delete)} cert bullet blocks to remove from Technical Proficiency")

    # --- Step 3: Remove the stray divider after empty Certifications heading ---
    cert_divider_id = page_config["cert_divider_id"]
    divider_idx = find_block_index(blocks, cert_divider_id)

    # --- Step 4: Add cert bullets under Certifications heading ---
    cert_heading_id = page_config["cert_heading_id"]
    cert_heading_idx = find_block_index(blocks, cert_heading_id)

    if cert_heading_idx == -1:
        print("  ⚠️  Certifications heading not found!")
        return

    languages_idx = find_block_index(blocks, page_config["languages_heading_id"])

    new_cert_children = [
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": cert_text}}]
            },
        }
        for cert_text in page_config["certs"]
    ]

    if dry_run:
        print(f"  🗑️  Would REMOVE divider: {cert_divider_id}")
        print(f"  🗑️  Would DELETE {len(cert_bullets_to_delete)} cert bullets from Technical Proficiency:")
        for cb in cert_bullets_to_delete:
            text = cb.get("bulleted_list_item", {}).get("rich_text", [{}])[0].get("plain_text", "")
            print(f"        - {text[:70]}...")
        print(f"  ✏️  Would APPEND {len(new_cert_children)} cert bullets after Certifications heading ({cert_heading_id})")
        for child in new_cert_children:
            print(f"        + {child['bulleted_list_item']['rich_text'][0]['text']['content'][:70]}...")
        print(f"  (dry run – no changes made)")
        return

    # --- APPLY ---
    print(f"\n  🗑️  Removing divider {cert_divider_id}...")
    notion.blocks.delete(block_id=cert_divider_id)

    print(f"  🗑️  Deleting {len(cert_bullets_to_delete)} cert bullets from Technical Proficiency...")
    for cb in cert_bullets_to_delete:
        notion.blocks.delete(block_id=cb["id"])

    print(f"  ✏️  Appending {len(new_cert_children)} cert bullets after Certifications heading...")
    notion.blocks.children.append(
        block_id=page_id,
        after=cert_heading_id,
        children=new_cert_children,
    )

    print(f"  ✅ Done!")


def main():
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv
    apply = "--apply" in sys.argv or "-a" in sys.argv

    if not apply and not dry_run:
        dry_run = True
        print("⚠️  No flag specified — running in DRY RUN mode. Use --apply to execute.")

    for key, config in PAGES.items():
        update_page(config, dry_run=dry_run)

    if dry_run:
        print("\n--- DRY RUN COMPLETE ---")
        print("Run with --apply to execute all changes.")


if __name__ == "__main__":
    main()
