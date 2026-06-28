# Agent-Friendly Documentation — Research Findings

> Research date: 2026-06-07
> Sources: Agent-Friendly Documentation Spec, Medium, Atlan, Vercel Academy, Cursor Workshop, NexaSphere, Chase Seibert blog

## Core Principles

### Concise Root File
- Keep `AGENTS.md` / `CLAUDE.md` under 150 lines — essential context only
- List exact build, test, lint commands
- Point to task-specific files for deeper rules
- Front-load primary keywords and one-sentence project description after H1

### Operational Over Narrative
- Write implementation contracts: specify inputs, expected behaviors, verification steps
- Prefer "New endpoints must return `{ data, error }`" over "Keep the API consistent"
- Use specific, imperative language in rules
- Document stop conditions: "ask before editing billing"

### Structured Data (Tables)
- Use tables for technical specifications (stack, env vars, endpoints)
- Tables are more parseable than bulleted lists for agents
- HTTP methods and paths in standalone code blocks
- Parameters in markdown tables with real example values (never placeholders)
- Document every possible error response

### Layered Documentation
- Root file: router with high-level context only
- Task guides near the relevant code (not all in root)
- Each page should be self-contained — agent can understand context without navigating elsewhere

### Discovery
- Serve markdown directly
- Use stable semantic URLs
- Create `llms.txt` at site root for agent index (< 50K chars)
- Additive tags (e.g., `Agent` blocks) for agent-only hints — keeps UI clean

### Maintenance
- Automate freshness checks
- Validate links in CI
- Enforce page/file size limits to prevent context drift and token waste

## Key Sources

| Source | URL |
|--------|-----|
| Agent-Friendly Documentation Spec | https://agentdocsspec.com/spec/ |
| Agent-Readable Documentation (Medium) | https://medium.com/toward-next-ai/agent-readable-documentation-how-to-write-docs-ai-coding-agents-can-actually-use-7e5d86d3d426 |
| Steering Coding Agents with Repo-Native Docs | https://chase-seibert.github.io/blog/2026/02/28/coding-agent-repo-native-docs.html |
| How to Write Agent-Friendly Docs (Farming Labs) | https://docs.farming-labs.dev/docs/guides/agent-friendly-docs |
| Agent-Friendly Docs (Vercel Academy) | https://vercel.com/academy/agent-friendly-apis/agent-friendly-docs |
| How to Write an AGENTS.md File (Atlan) | https://atlan.com/know/how-to-write-agents-md/ |
| How to Write AI Coding Rules Files (NexaSphere) | https://nexasphere.io/blog/how-to-write-ai-coding-rules-files-2026 |
| Documentation as Effective AI Context | https://developertoolkit.ai/en/shared-workflows/context-management/documentation-as-context/ |
