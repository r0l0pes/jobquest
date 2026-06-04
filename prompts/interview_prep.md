# Interview Preparation Generator — LLM Prompt

You are generating a structured interview preparation document for Rodrigo Lopes.
The output will be an `.md` file the candidate reads before the interview.

## Input Context

You receive:
- **Company Research:** Recent news, product info, team structure, culture
- **Job Description:** The full JD with requirements and responsibilities
- **Master Resume:** Rodrigo's full professional background
- **Story Bank:** Pre-written STAR+R stories to match against likely questions
- **Q&A Answers:** Answers already generated for application questions (useful for consistency)

If company research is empty, omit the company-specific sections gracefully.

If the story bank is empty, generate generic behavioral questions — do not fabricate STAR examples.

## Output Structure

Output the full interview prep document as Markdown with these sections:

### Company Context
Summarize 3-5 key facts from company research: mission, recent news, products, team/culture hints.
Keep it concise — 4-6 bullet points. If no research, note "No company research available."

### Likely Questions

Generate questions the interviewer is likely to ask, organized by type.

#### Technical / Role-Specific
Derive 3-5 questions from JD requirements. For each:
- The question itself
- **Talking points:** Specific experience from Rodrigo's resume that answers it
- **STAR:** Reference to a story bank entry if one matches (format: `### Story Title`)

#### Behavioral
Generate 2-3 standard behavioral questions matched to this role. For each:
- The question
- **STAR:** Best-matching story from the story bank

#### Company-Specific
Generate 1-2 company-specific questions based on research (e.g., "Why this company?").
- **Talking points:** Company research + relevant experience

### Questions to Ask Them

Generate questions Rodrigo should ask the interviewer, organized by category.

#### About the Role
- "What does success look like in the first 6 months?"
- 1-2 role-specific questions derived from JD gaps or responsibilities

#### About the Team
- "How does the team divide work between PM, design, and engineering?"
- 1 team-specific question from company research if available

#### About Culture
- "What do people who thrive here have in common?"
- 1 culture-specific question from company research if available

### STAR Examples (Pre-Selected)

For each story in the story bank that matches a likely question:
```
### [Story Title] — for "[Question Type]"
**S:** [Situation from story bank]
**T:** [Task from story bank]
**A:** [Action from story bank]
**R:** [Result from story bank]
**Reflection:** [Reflection from story bank]
```

Only include stories that MATCH the likely questions. If the story bank is empty, skip this section.

### Follow-Up Timeline

Give concrete follow-up guidance:
- If no response after 2 weeks: suggest brief, professional follow-up
- Reference something specific about the company conversation if possible

## Quality Rules

- Every question must be grounded in the JD or company research — no generic questions
- STAR references must match actual story bank entries
- Talking points must reference real experience from the master resume
- No fabrications — if you don't know something, don't include it
- Keep the tone professional and confident
