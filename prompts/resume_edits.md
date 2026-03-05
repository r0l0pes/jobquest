You receive a tailoring brief and the master resume. Return a JSON object with the targeted changes needed. No prose, no explanation — only the JSON.

## JSON schema

```json
{
  "tagline": "short tagline, plain text, no LaTeX",
  "summary_bullet": "full summary text, plain text, no LaTeX commands",
  "wfp_bullets": [
    "bullet 1 full text",
    "bullet 2 full text",
    "bullet 3 full text"
  ],
  "skills": [
    {"category": "Product", "content": "skill1, skill2, skill3"},
    {"category": "Analytics", "content": "SQL, A/B Testing, GA4, Mixpanel, Power BI, Tableau"},
    {"category": "Tools", "content": "Jira, Linear, Productboard, Notion, Zapier, n8n"},
    {"category": "Rapid Prototyping & Automation", "content": "Figma, Claude Code, Cursor, MCP, Supabase"},
    {"category": "AI & ML", "content": "LLM Evaluation, Prompt Engineering, Voice AI, Agentic Workflows"},
    {"category": "Platforms & APIs", "content": "REST APIs, Third-Party Integrations, IVR Voice Platforms, VTEX"}
  ]
}
```

## Rules

- Plain text only in all fields. No LaTeX commands, no backslashes, no \textbf, no \item.
- For sections not mentioned in the brief as needing change: copy the existing text verbatim from the master resume.
- wfp_bullets must have exactly 3 items unless the brief explicitly says to add a 4th bullet, in which case include 4.
- Each bullet is the full text of one achievement. No truncation.
- Skills: each category maps to a comma-separated list of skills. Add or reorder skills to match the brief. Do not invent skills not present in the master resume.
- No em dashes (— or --). Use commas or colons instead.
- Do not include markdown formatting, code blocks, or any wrapper text. Return only the raw JSON.
