You receive a tailoring brief and the master resume. Return a JSON object with the targeted changes needed. No prose, no explanation — only the JSON.

## JSON schema

```json
{
  "tagline": "short tagline, plain text, no LaTeX",
  "summary_bullet": "full summary text, plain text, no LaTeX commands",
  "postscript_bullets": [
    "bullet 1 full text",
    "bullet 2 full text",
    "bullet 3 full text"
  ],
  "skills": [
    {"category": "Product", "content": "Experimentation Frameworks, A/B Testing, Funnel & Cohort Analysis"},
    {"category": "Analytics", "content": "SQL, GA4, Amplitude"},
    {"category": "Tools", "content": "Jira, Notion, Cursor"},
    {"category": "AI-Assisted & LLM Workflows", "content": "LLM Workflows, LLM Output Evaluation, Prompt Engineering, MCP (Model Context Protocol)"},
    {"category": "Platforms & APIs", "content": "REST APIs, Payment Gateways, VTEX E-commerce"}
  ]
}
```

## Rules

- Plain text only in all fields. No LaTeX commands, no backslashes, no \textbf, no \item.
- For sections not mentioned in the brief as needing change: copy the existing text verbatim from the master resume.
- postscript_bullets must have exactly 3 items unless the brief explicitly says to add a 4th bullet, in which case include 4.
- Each bullet is the full text of one achievement. No truncation.
- Skills: each category maps to a comma-separated list of skills. Reorder only skills present in the selected master resume. Reject every JD-only skill or phrase, including PLS, pricing models, healthcare experience, agentic systems, Voice AI, IVR, RAG, or similar claims.
- Verified metrics, attribution, scope, dates, and titles are immutable.
- Tailoring may reorder or minimally paraphrase supported facts, but it cannot change the meaning of the source experience or introduce new ownership, growth motions, pricing models, domains, or technical capabilities.
- The Postscript edit must preserve post-launch ownership, Infinity Testing campaign scope for +28% EPM, 18,000+ as analytics/platform scale, Brand Center as an existing control layer, and merchant review/control.
- No em dashes (— or --). Use commas or colons instead.
- Do not include markdown formatting, code blocks, or any wrapper text. Return only the raw JSON.
