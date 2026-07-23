#!/usr/bin/env python3
"""
July 2026 AI-repositioning update for both Notion master resume pages.

Applies the decisions from docs/plans/2026-07-23-resume-market-audit.md:
1. Summary rewrite (AI-as-gate, Builder PM + integrator, evals vocabulary)
2. Postscript bullets 1 & 3 rewrite (loop + evaluation criteria + growth loop)
3. Postscript end date Apr 2026 -> Jun 2026
4. Generalist date unification to canonical dates (FORVIA, Accenture, C&A, Education 2017)
5. Header: Location -> "12435, Berlin", drop Phone line
6. Technical Proficiency: add Growth Loops, Agile Delivery, LLM Output Evaluation;
   sync Generalist tools with Growth; trim Analytics to verified set

Usage:
    python scripts/notion_reposition_ai_2026.py --dry-run
    python scripts/notion_reposition_ai_2026.py --apply
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTION_TOKEN
from notion_client import Client

notion = Client(auth=NOTION_TOKEN, notion_version="2022-06-28")

# --- New shared texts -------------------------------------------------------

NEW_POSTSCRIPT_BULLET_1 = (
    "Led product development of an AI-powered message optimization engine for Shopify merchants, "
    "owning the full loop: generative AI produces brand-aligned message variants, predictive "
    "analytics evaluates them against live subscriber segments, and the model learns from every "
    "send. Defined the evaluation criteria (brand fit, predicted CTR, earnings-per-message) that "
    "gated what shipped, driving a 28% increase in earnings-per-message through continuous model learning."
)

NEW_POSTSCRIPT_BULLET_3 = (
    "Built analytics instrumentation to measure SMS program health across 18,000+ merchant accounts, "
    "establishing earnings-per-message and click-through rate as primary KPIs. Identified engagement "
    "decay patterns unique to SMS versus email, translating insights into a re-engagement automation "
    "roadmap that closed the retention growth loop with the optimization engine."
)

NEW_ANALYTICS = "Analytics: SQL, Python, GA4, Amplitude, Mixpanel, Power BI, Tableau, FullStory"

NEW_POSTSCRIPT_DATE = "Jul 2024 – Jun 2026 | Remote"

# --- Per-page edit specs ----------------------------------------------------
# Each edit: (match_prefix, block_type, new_text or None to delete)

PAGES = {
    "growth_pm": {
        "id": "2f40fd98-227b-8083-a78f-c61c38e55a12",
        "name": "Master Resume (Growth PM)",
        "edits": [
            ("Senior Growth Product Manager with 8+ years", "paragraph",
             "Senior Growth Product Manager with 8+ years turning data into product decisions across "
             "B2C e-commerce, B2B platforms, and AI-powered products in Europe and LatAm. Led an AI "
             "message optimization engine at Postscript: generative AI variant generation, predictive "
             "evaluation against live subscriber segments, continuous model learning, driving a 28% "
             "earnings-per-message lift across 18,000+ merchants. Builds prototypes and agentic "
             "workflows with Claude Code, Cursor, and MCP, and aligns engineering, data, and "
             "commercial teams around structured experimentation."),
            ("Jul 2024 – Apr 2026", "paragraph", NEW_POSTSCRIPT_DATE),
            ("Led product development for an AI-powered message optimization engine", "bulleted_list_item",
             NEW_POSTSCRIPT_BULLET_1),
            ("Built analytics instrumentation", "bulleted_list_item", NEW_POSTSCRIPT_BULLET_3),
            ("Location: Berlin, Germany", "paragraph", "Location: 12435, Berlin"),
            ("Phone:", "paragraph", None),  # delete
            ("Growth & Product:", "paragraph",
             "Growth & Product: Experimentation Frameworks, A/B Testing, Funnel & Cohort Analysis, "
             "Conversion Rate Optimisation (CRO), Product-Led Growth (PLG), Growth Loops, Activation & "
             "Onboarding, Roadmap Prioritisation, OKRs, Stakeholder Alignment, Go-to-Market Planning, "
             "Agile Delivery"),
            ("Analytics:", "paragraph", NEW_ANALYTICS),
            ("AI-Assisted & Agentic Workflows:", "paragraph",
             "AI-Assisted & Agentic Workflows: Claude Code, Cursor, LLM Workflows, LLM Output "
             "Evaluation, Prompt Engineering, MCP (Model Context Protocol), Agentic Systems Design, "
             "Voice AI (NLP, STT/TTS), ML Use Case Discovery and Validation, Agent-Ready Systems Thinking"),
        ],
    },
    "generalist": {
        "id": "30b0fd98-227b-8195-9649-fe5287cb8cb9",
        "name": "Generalist PM Resume",
        "edits": [
            ("Senior Product Manager with 8+ years", "paragraph",
             "Senior Product Manager with 8+ years leading cross-functional discovery, roadmap "
             "strategy, and delivery across B2C e-commerce, B2B platforms, and AI-powered products "
             "in Europe and LatAm. Shipped an AI message optimization engine at Postscript used by "
             "18,000+ merchants, owning the evaluation criteria and model-learning loop end to end. "
             "Connects engineering, data, and commercial teams from user research through "
             "go-to-market, turning data into product decisions that scale."),
            ("Jul 2024 – Apr 2026", "paragraph", NEW_POSTSCRIPT_DATE),
            ("Led product development for an AI-powered message optimization engine", "bulleted_list_item",
             NEW_POSTSCRIPT_BULLET_1),
            ("Built analytics instrumentation", "bulleted_list_item", NEW_POSTSCRIPT_BULLET_3),
            # Canonical date unification
            ("Jul 2022 – Jan 2024", "paragraph", "Nov 2022 – May 2024 | Berlin, Germany"),
            ("Feb 2020 – Apr 2022", "paragraph", "Jun 2020 – Aug 2022 | São Paulo, Brazil"),
            ("Mar 2018 – Jan 2020", "paragraph", "Aug 2018 – May 2020 | São Paulo, Brazil"),
            ("2016 – Bachelor", "bulleted_list_item",
             "2017 – Bachelor’s Degree, Business Administration and Management, Universidade de São Paulo"),
            ("Location: Berlin, Germany", "paragraph", "Location: 12435, Berlin"),
            ("Phone:", "paragraph", None),  # delete
            ("Product & Strategy:", "paragraph",
             "Product & Strategy: Product Discovery, Roadmap Prioritisation, Stakeholder Alignment, "
             "OKRs, Go-to-Market Planning, Experimentation Frameworks, A/B Testing, Funnel & Cohort "
             "Analysis, Conversion Rate Optimisation (CRO), Product-Led Growth (PLG), Growth Loops, "
             "Activation & Onboarding, Agile Delivery"),
            ("Analytics:", "paragraph", NEW_ANALYTICS),
            ("Tools:", "paragraph",
             "Tools: Jira, Linear, Productboard, Notion, Figma, Zapier, Retool, n8n, PostHog, Cursor"),
            ("AI-Assisted & Agentic Workflows:", "paragraph",
             "AI-Assisted & Agentic Workflows: Claude Code, GitHub Copilot, Cursor, LLM Workflows, "
             "LLM Output Evaluation, Prompt Engineering, MCP (Model Context Protocol), Agentic "
             "Systems Design, Voice AI (NLP, STT/TTS), ML Use Case Discovery and Validation, "
             "Agent-Ready Systems Thinking"),
        ],
    },
}


def get_block_text(block):
    content = block.get(block.get("type", ""), {})
    return "".join(t["plain_text"] for t in content.get("rich_text", []))


def fetch_all_blocks(page_id):
    blocks, cursor = [], None
    while True:
        r = notion.blocks.children.list(block_id=page_id, page_size=100, start_cursor=cursor)
        blocks.extend(r["results"])
        if not r.get("has_more"):
            break
        cursor = r["next_cursor"]
    return blocks


def apply_page(page_key, spec, dry_run):
    print(f"\n=== {spec['name']} ===")
    blocks = fetch_all_blocks(spec["id"])
    matched, missed = 0, []

    for prefix, btype, new_text in spec["edits"]:
        hit = next(
            (b for b in blocks if b.get("type") == btype and get_block_text(b).startswith(prefix)),
            None,
        )
        if not hit:
            missed.append(prefix)
            continue
        matched += 1
        if dry_run:
            action = "DELETE" if new_text is None else "UPDATE"
            print(f"  [DRY] {action}: {get_block_text(hit)[:70]}...")
            continue
        if new_text is None:
            notion.blocks.delete(block_id=hit["id"])
            print(f"  DELETED: {get_block_text(hit)[:70]}")
        else:
            notion.blocks.update(
                block_id=hit["id"],
                **{btype: {"rich_text": [{"type": "text", "text": {"content": new_text}}]}},
            )
            print(f"  UPDATED: {prefix[:50]}...")

    if missed:
        print(f"  ⚠ NOT MATCHED ({len(missed)}): {missed}")
    print(f"  {matched}/{len(spec['edits'])} edits matched")
    return not missed


def main():
    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("DRY RUN — pass --apply to write changes")
    ok = all(apply_page(k, s, dry_run) for k, s in PAGES.items())
    if not ok:
        print("\n⚠ Some edits did not match. Review before re-running.", file=sys.stderr)
        sys.exit(1)
    print("\nDone." + (" (dry run, nothing written)" if dry_run else " All changes applied."))


if __name__ == "__main__":
    main()
