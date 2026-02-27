# AI PM Context — Rodrigo Lopes

## How to use this (pipeline instructions)

Inject this file when the JD has AI-related requirements: AI PM, AI-native workflows, using AI for PRDs, vibe coding, LLM tools, MCP, Cursor, Claude, co-pilot, AI-first, etc.

**Resume (step 3):** Instruct the writing model to add a fourth bullet to the WFP section surfacing AI-augmented workflows. Keep the three existing WFP bullets intact. Ground the new bullet in the WFP tenure (Mar 2024 – Dec 2025). Do not add AI workflow bullets to other roles.

**Q&A (step 8):** Draw from the talking points below when answering questions about AI tool usage, AI PM experience, or how Rodrigo works with AI.

No fabrication: everything below is real.

---

## WFP role context (Mar 2024 – Dec 2025)

This is not just "used AI tools at work." The WFP role was AI product management:

- **AI voice agent for smallholder farmers**: Rodrigo owned activation strategy, defined adoption funnel and success metrics, and ran guardrail and governance work. Day-to-day this involved evaluating LLM output quality, reviewing hallucination rates, and working with engineers on prompt design and safety thresholds. Validated 60% cost efficiency vs. human-led outreach.

- **AI validation platform**: PM for WFP's internal tool enabling non-technical staff to run ML and GenAI experiments across humanitarian operations without centralised engineering support. This is LLM evaluation infrastructure: defining experiment templates, evaluation criteria, what "good output" looks like per use case, and governance guardrails. The PM role here overlaps significantly with what ML engineers and AI researchers call model evaluation.

- **Analytics and scaling**: Built the measurement framework for AI interface usability and pilot performance. Translated pilot data into expansion priorities for 20+ country programs, which required synthesising quantitative metrics with qualitative field feedback — a workflow AI tools accelerated significantly.

---

## How I use AI tools to do PM work

### Timeline of tools (WFP period)

**Mar 2024 – Oct 2024**: Cursor (AI-native editor) as primary interface. Claude Sonnet via API for generation and reasoning tasks (PRD drafts, synthesis, analysis). ChatGPT for quick brainstorms. Notion AI for meeting notes and knowledge management.

**Nov 2024 – Apr 2025**: MCP (Model Context Protocol) launches November 2024. Starts connecting Claude to external tools (Notion, data sources) via standardised protocol. Moves from one-off chat interactions to multi-step automated workflows.

**May 2025 – Dec 2025**: Claude Code (terminal-based agentic interface) becomes primary execution layer. Cursor remains part of the stack for file editing. Combined with MCP integrations for Notion and task management tools.

### Workflows

**PRD and documentation drafting**
Maintain product context (roadmap items, specs, research notes) as structured markdown files. Claude reads that context and drafts PRDs from templates without re-explaining the product each session. At WFP: activation strategy docs for the voice agent, analytics framework specs, governance documentation for the AI validation platform.

**LLM evaluation and experiment design**
As PM on both the voice agent and the validation platform, evaluation was a core workflow: defining what "good" looks like for a generative output, reviewing sample outputs against criteria, structuring rubrics for non-technical reviewers. Used Claude to draft evaluation frameworks, generate adversarial test cases, and synthesise evaluation results across country-program pilots.

**Data and metrics analysis**
Connect Claude Code to exported analytics or data sources. Point it at a dashboard or CSV, it runs breakdowns and surfaces hypotheses. At WFP: analysing adoption metrics from voice agent field pilots, measuring AI interface usability across country programs, translating field data into scaling arguments for leadership presentations.

**User research and feedback synthesis**
Feed interview notes, field officer feedback, stakeholder inputs, and pilot reports into context. Claude clusters themes, flags blockers, and structures the output into something actionable. At WFP: synthesising feedback from voice agent pilots across Tanzania field operations, clustering AI use case submissions from country teams on the validation platform.

**Rapid prototyping and use case validation**
Use Cursor and Claude Code to turn a problem statement into a working prototype fast enough to validate direction before committing engineering. At WFP: prototyping lightweight versions of AI use cases submitted by country teams to test feasibility and user acceptance before full development prioritisation.

**Automated reporting and synthesis pipelines**
Build agents that pull data from multiple sources, analyse trends, and push a structured summary to Notion or Slack. Replaces manual report prep with a draft already in place before the meeting. At WFP: weekly status summaries for Innovation Accelerator leadership on pilot performance and scaling recommendations.

**Engineering coordination**
After synthesising insights into a spec, draft acceptance criteria and route to engineering via task management tools. The agent breaks a PRD into structured tickets with requirements and technical considerations, reducing PM-to-engineer handoff friction.

---

## End-to-end agentic PM workflow (how it all fits together)

The individual workflows above don't run in isolation — they chain. The pattern, which I run consistently:

1. An anomaly surfaces in a metric or a pile of feedback comes in. Point Claude Code at the data source via MCP. It pulls the underlying data, runs breakdowns by segment and time, and generates hypotheses in a structured format. What used to be 2-3 hours of manual chart-building takes minutes.

2. That analysis feeds directly into synthesis. If it's a metric spike, pull related experiment data and recent feedback into the same context and ask: what changed, when, and what's the most plausible driver? If it's a feedback cluster, group by theme, flag severity, surface what users love vs. what's broken.

3. Synthesis becomes a spec. With the context already loaded, draft a PRD from a template. The agent has the problem statement, the evidence, and the constraints. First draft is substantive, not a blank page. Iterate in the same session.

4. Spec becomes tickets. Break acceptance criteria into structured engineering tickets with requirements and technical considerations, routed to Linear or Jira via MCP.

The whole sequence — from anomaly to tickets in the backlog — runs in one Claude Code session. No context-switching between tools, no copying data between tabs. The PM judgment is at each review point: is this the right hypothesis, is this the right solution, are these the right tickets. The execution between those judgment calls is automated.

This is the shift Frank Lee describes: from "I spend Sundays building metrics and writing narratives" to "Monday morning the draft is already there and I focus on what to do about it."

---

## Key talking points for Q&A

- "I shifted from using AI as a writing assistant to using it as an execution layer. Chat is for exploring; Claude Code and MCP are for running workflows."
- "I keep product context as structured files. Agents read that context, so I never re-explain the product from scratch — continuity is built into the setup."
- "At WFP, LLM evaluation was part of the job: defining what good output looks like, reviewing samples against criteria, building rubrics that field-non-technical reviewers could apply. That's not that different from what ML teams call evals."
- "The tools that changed things most in this period: Cursor for editing (from day one), Claude Sonnet via API for reasoning tasks (2024), Claude Code for execution (from May 2025 when it launched). Each jump expanded what I could automate without an engineer."
- "I think of it as: what PM tasks are repetitive, data-heavy, and have clear enough output criteria that an agent can run them? Those get automated. The synthesis of 'so what' and the decisions stay with me."
- "MCP changed the workflow in late 2024 — instead of copying data between tools manually, agents could pull from Notion, push to task management, read analytics exports, all in one orchestrated run."
