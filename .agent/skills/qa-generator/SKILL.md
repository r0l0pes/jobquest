---
name: qa-generator
description: Generate application answers in Rodrigo's authentic voice by reading job posting, pulling Q&A templates from Notion via scripts, researching company via WebSearch, and crafting specific, metric-backed responses. Use when user pastes application questions or asks to answer motivation/why-company prompts.
---

# Q&A Generator Skill

## Purpose
Generate compelling, authentic application answers that showcase Rodrigo's real experience in his distinctive voice--direct, builder-focused, metric-backed, no corporate fluff.

## When to Use
Activate this skill when:
- User pastes application questions from job form
- User says "answer these questions"
- User asks "help with motivation letter"
- User requests "why this company" response
- Any request involving application text responses

## Prerequisites
- `scripts/notion_reader.py` must be functional
- WebSearch tool available (for company research)
- Tone guide understood (Rodrigo's writing voice)

## Rodrigo's Voice Principles

**Core characteristics:**
- **Direct, no fluff:** Say what you mean. No corporate buzzwords.
- **Concrete over abstract:** Use specific examples, not vague claims.
- **Honest about tradeoffs:** Acknowledge limitations, don't oversell.
- **Action-oriented:** Show what you DO, not what you "believe in."
- **Builder's perspective:** Frame as someone who ships, not someone who "strategizes."
- **Structured thinking:** Break complex answers into digestible parts.
- **No hedging:** Confident but not arrogant. Never "I think maybe..."

**Voice summary:**
> Rodrigo writes like a builder who happens to be a PM, not a PM who talks about building. He's direct, specific, honest about what worked and what didn't, and always ties ideas to concrete outcomes. He doesn't use corporate jargon or hedge with "I believe" statements. When he makes a claim, he backs it with an example or metric.

## Process

### Step 1: Analyze Questions
1. Read all questions user provided
2. Categorize each question:
   - **Motivation:** "Why do you want this job?"
   - **Why Company:** "Why [Company]?"
   - **Technical Depth:** "Describe your PM process"
   - **Product Metrics:** "What metrics have you tracked?"
   - **Experience Validation:** "Tell me about a time..."
   - **Hybrid Work:** "How do you feel about 50/50 onsite?"
   - **Salary/Logistics:** Skip these (user handles separately)

### Step 2: Read Job Posting Context
1. If user provided job posting earlier in conversation, reference it
2. Extract key points:
   - Company name
   - Product/industry
   - Key challenges mentioned
   - Required skills emphasized

### Step 3: Company Research (WebSearch)
For "Why Company" questions, use the WebSearch tool:
1. Search: "[Company name] recent news product launches 2025 2026"
2. Search: "[Company name] product features latest"
3. Identify 1-2 SPECIFIC recent things:
   - New product launch
   - Feature announcement
   - Company milestone
   - Technical challenge they're solving

**Goal:** Find something concrete to reference, not generic "mission" statements.

### Step 4: Pull Relevant Templates from Notion
If Q&A Templates DB is configured (NOTION_QA_TEMPLATES_DB_ID is set in .env), read templates:
```bash
venv/bin/python scripts/notion_reader.py database <QA_TEMPLATES_DB_ID>
```

Match question type to template:
- Motivation questions -> motivation template
- Why Company -> why-company template
- Technical depth -> technical-depth template
- Product metrics -> product-metrics template
- Hybrid work -> hybrid-work template

Templates provide:
- Answer structure
- Example phrases in Rodrigo's voice
- Which experiences to draw from

If Q&A Templates DB is not configured, use the built-in guidance in this skill file.

### Step 5: Select Relevant Experience
Based on question + job posting, choose which of Rodrigo's roles to highlight:

**WFP (AI validation, humanitarian, governance):**
- Use for: AI product roles, user research, validation methodology, stakeholder complexity

**FORVIA HELLA (B2B, post-merger, integration):**
- Use for: Enterprise PM, B2B platforms, organizational complexity, integration projects

**Accenture (growth, multi-market, consulting):**
- Use for: E-commerce, growth PM, international experience, conversion optimization

**C&A Brasil (execution, fast promotion, mobile-first):**
- Use for: Experimentation rigor, mobile optimization, execution speed, career progression

### Step 6: Generate Answer in Rodrigo's Voice

**Answer structure:**
```
[Hook: Specific recent thing about company]

[Connection: Tie to YOUR real experience with metric]

[Depth: 1-2 sentences showing HOW you did it]

[Fit: What you want to bring to THEIR specific challenge]
```

**Example for "Why [Company]?":**

Bad (generic AI answer):
"I'm excited about [Company]'s mission to transform the industry. I believe my experience aligns well with your goals and I'm passionate about making an impact."

Good (Rodrigo's voice):
"[Company]'s recent launch of [X feature] caught my attention--it's solving the same problem I worked on at WFP: getting useful information to users who can't navigate traditional interfaces. At WFP, we validated a generative AI voice agent for 5,000 farmers in Tanzania, measuring adoption, retention, and decision quality. That experience taught me what it takes to ship AI products for real users, not just demos. I want to bring that same rigor to [Company]'s [specific product/challenge]."

### Step 7: Integration with Form Filler
When answers are generated for an application form:
1. Collect all answers into a JSON data object
2. Write to `output/form_data_<CompanyName>.json`
3. This JSON can be passed to `scripts/form_filler.py --data-file` for auto-filling

Example JSON structure:
```json
{
  "name": "Rodrigo Lopes",
  "email": "contact@rodrigolopes.eu",
  "phone": "",
  "linkedin": "https://www.linkedin.com/in/rodecalo",
  "location": "Berlin, Germany",
  "cover_letter": "Generated motivation text...",
  "custom_field_name": "Generated answer..."
}
```

### Step 8: Quality Check Before Output

**Review answer against these criteria:**
- [ ] Mentions something SPECIFIC about company (not generic mission)
- [ ] Ties to REAL experience from your background
- [ ] Includes at least ONE metric or concrete outcome
- [ ] No buzzwords ("passionate," "synergy," "driven," "excited")
- [ ] No hedging ("I believe," "I think," "I would")
- [ ] Sounds like Rodrigo (direct, builder-focused, honest)
- [ ] Length appropriate (100-150 words for short answers, 200-300 for motivation letters)

### Step 9: Output Format
```markdown
## Question: [Original question text]

**Answer:**

[Your generated answer in Rodrigo's voice]

---

**Used:**
- Experience: [Which role you referenced]
- Metric: [Which specific metric you cited]
- Company research: [What recent thing you found]

---
```

## Critical Rules

### NEVER DO THIS:
- Use buzzwords: "passionate," "excited," "synergy," "driven," "leverage"
- Write generic answers: "I believe my experience aligns..."
- Fabricate experience or metrics
- Copy template text verbatim (adapt to specific question)
- Write in corporate-speak or formal tone
- Make unsubstantiated claims

### ALWAYS DO THIS:
- Reference something SPECIFIC about company (product, feature, challenge)
- Tie to REAL experience with metric
- Write in Rodrigo's direct, builder voice
- Back claims with examples
- Keep it concise (no fluff)
- Make connection crystal clear (your experience -> their challenge)

## Templates Quick Reference

**Motivation questions:**
- Structure: What problem they're solving -> Your relevant experience solving similar -> Why now
- Example: "At [Role], I [specific action with metric]. That's the kind of [skill] [Company] needs for [their challenge]."

**Why Company:**
- Structure: Specific recent thing -> Your connection -> What you bring
- MUST include company research (recent launch, feature, news)

**Technical depth:**
- Structure: Methodology name -> Concrete example -> Outcome -> Lesson learned
- Example: "At Accenture, we ran 15+ A/B tests using [specific approach]. One test [specific result]. Learned: [specific lesson]."

**Product metrics:**
- Structure: Metric type -> Context -> How tracked -> Why it mattered
- Pull from case studies (45% conversion, EUR 12M revenue, 60% cost efficiency)

**Hybrid work (50/50 onsite):**
- Key point: Rodrigo is comfortable with hybrid (was onsite at FORVIA, C&A)
- Frame: "Hybrid makes sense for [specific PM activities]. At FORVIA, being onsite helped with [specific example]."

## Script Reference
| Script | Purpose | Example |
|--------|---------|---------|
| `scripts/notion_reader.py` | Read Q&A templates | `venv/bin/python scripts/notion_reader.py database <db_id>` |
| `scripts/form_filler.py` | Fill forms with answers | `venv/bin/python scripts/form_filler.py --url URL --data-file output/form_data.json` |

## Notes
- User applies to 50-100+ jobs (volume strategy)
- Speed matters: generate quickly, user reviews briefly
- 80% reusable for generic questions, 20% custom for company-specific
- Focus on making connection obvious, not writing poetry
