# Mode: prep-interview — Company-Specific Interview Intelligence

When the user has an interview at a specific company+role, or when a job scores

> = 60, run this mode.

## Inputs

1. **Company name** and **role title** (required)
2. **Evaluation report** in `output/` (if pipeline was run) — read for ATS match
3. **Story bank** at `interview-prep/story-bank.md` — read for existing stories
4. **CV** at Notion (master resume) — read for proof points
5. **Pipeline score** from `data/applications.json` — context on fit

## Step 1 — Research the Company

Run these searches. Extract structured data, cite sources.

| Query                                                       | What to extract                                        |
| ----------------------------------------------------------- | ------------------------------------------------------ |
| `"{company} {role} interview questions site:glassdoor.com"` | Actual questions, difficulty, process timeline, rounds |
| `"{company} interview process site:teamblind.com"`          | Candid process descriptions, hiring bar                |
| `"{company} engineering blog"` OR `"{company} tech blog"`   | Tech stack, values, technical priorities               |
| `"{company} about page"`                                    | Mission, product, recent news                          |

If the company is small and yields few results: broaden to similar-stage
companies and note that intel is sparse.

**NEVER fabricate questions.** Label inferences from JD analysis as
`[inferred from JD]`, not sourced from candidates.

## Step 2 — Process Overview

```markdown
## Process Overview

- **Rounds:** {N} rounds, ~{X} days end-to-end
- **Format:** {e.g., recruiter screen → technical phone → take-home → onsite}
- **Difficulty:** {X}/5 (Glassdoor avg, N reviews)
- **Known quirks:** {e.g., "pair programming instead of whiteboard"}
- **Sources:** {links}
```

If data insufficient for any field, write "unknown" rather than guessing.

## Step 3 — Likely Questions (Categorized)

### Technical

Questions about system design, coding, architecture, domain knowledge.
For each: the question, source, and what a strong answer looks like for THIS
candidate (reference CV proof points).

### Behavioral

Questions about leadership, conflict, collaboration, failure.
For each: the question, source, and which story from `story-bank.md` maps best.

### Role-Specific

Questions tied to the specific job description.
For each: the question, why they're likely asking it (what JD requirement
it maps to), and the candidate's best angle.

## Step 4 — Story Mapping

| #   | Likely question                              | Story from story-bank.md         | Fit          |
| --- | -------------------------------------------- | -------------------------------- | ------------ |
| 1   | "Tell me about a time you improved a metric" | Checkout Conversion at Accenture | strong       |
| 2   | ...                                          | ...                              | partial/none |

For each gap: "You need a story about {topic}. Consider: {specific experience
from Notion resume that could become a STAR+R story}."

## Step 5 — Company Signals

- **Values they screen for:** name them, cite source
- **Vocabulary to use:** terms the company uses internally
- **Things to avoid:** anti-patterns flagged in interview reviews
- **Questions to ask them:** 2-3 sharp questions tied to recent news/blog posts

## Output

Save to `interview-prep/{company-slug}-{role-slug}.md`. Format:

```markdown
# Interview Intel: {Company} — {Role}

**Researched:** {YYYY-MM-DD}
**Sources:** {N} Glassdoor reviews, {N} Blind posts, {N} other
```
