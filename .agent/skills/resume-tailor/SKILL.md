---
name: resume-tailor
description: Generate tailored resume by reading job posting, extracting ATS keywords from Master Resume in Notion, and creating a complete LaTeX file compiled to PDF. Use when user pastes job posting and wants customized resume for application.
---

# Resume Tailor Skill

## Purpose
Generate ATS-optimized, tailored resume versions by intelligently inserting job-specific keywords into your master resume while maintaining professional formatting and honest representation. Outputs a compiled PDF via LaTeX.

## When to Use
Activate this skill when:
- User pastes a job posting URL or full job description
- User says "tailor my resume for this job"
- User says "customize resume for [company]"
- User requests ATS keyword optimization

## Prerequisites
- `scripts/notion_reader.py` must be functional
- `scripts/render_pdf.py` must be functional
- `templates/resume.tex` exists as structural reference
- pdflatex installed on system

## Process

### Step 1: Read Job Posting
1. If user provided URL, use WebFetch to get the page content
2. If user pasted text, use that directly
3. Extract key information:
   - Job title
   - Company name
   - Required skills (technical + soft skills)
   - Required experience level
   - Industry-specific terminology
   - Tools/technologies mentioned
   - Methodologies mentioned (Agile, OKRs, etc.)

### Step 2: Read Master Resume from Notion
Run via Bash:
```bash
venv/bin/python scripts/notion_reader.py page 2f40fd98-227b-8083-a78f-c61c38e55a12 --text
```
Parse the returned text to extract:
- Summary section
- Experience section (all roles: WFP, FORVIA HELLA, Accenture, C&A Brasil)
- Skills section
- Education section

### Step 3: Extract ATS Keywords
Identify keywords that:
- Appear 2+ times in job posting (high importance)
- Match your actual experience (only truthful additions)
- Are missing from current resume OR could be emphasized more

**Categorize keywords:**
- **High Priority:** Required skills you have but aren't emphasized
- **Medium Priority:** Nice-to-have skills you possess
- **Skip:** Skills you don't actually have (NEVER add fake skills)

### Step 4: Strategic Keyword Placement
Insert keywords naturally in these locations:

**Summary Section:**
- Add 2-3 high-priority keywords that match your actual experience
- Example: If job mentions "cross-functional leadership" and you coordinated teams, add this phrase

**Experience Bullets:**
- For each role, identify 1-2 bullets where keywords fit naturally
- Replace generic terms with job-specific terms:
  - Generic: "managed product roadmap"
  - Tailored: "managed product roadmap using OKRs" (if job mentions OKRs)

**Skills Section:**
- Reorder to prioritize job-relevant skills
- Add specific tools mentioned in posting (only if you've used them)

### Step 5: Generate Complete LaTeX File
Write a complete `.tex` file to `output/resume_tailored_<CompanyName>.tex`.

Use `templates/resume.tex` as structural reference but generate the FULL content inline (no Jinja2 variables).

#### LaTeX Escaping Rules
The following characters MUST be escaped in all text content:
- `%` → `\%`
- `&` → `\&`
- `$` → `\$`
- `#` → `\#`
- `_` → `\_`
- `{` and `}` → `\{` and `\}` (only when literal, not LaTeX commands)
- `~` → `\textasciitilde{}`
- `^` → `\textasciicircum{}`

#### Experience Entry Format
Each experience entry should follow this structure:
```latex
\textbf{Job Title} \hfill Location \\
\textit{Company Name} \hfill Dates \\
\begin{itemize}[nosep, leftmargin=*]
  \item Achievement or responsibility with metric
  \item Another achievement with keyword naturally inserted
\end{itemize}
```

#### Contact Line
```latex
\centerline{Berlin, Germany | \href{mailto:contact@rodrigolopes.eu}{contact@rodrigolopes.eu} | \href{https://www.linkedin.com/in/rodecalo}{LinkedIn}}
```

### Step 6: Compile to PDF
Run via Bash:
```bash
venv/bin/python scripts/render_pdf.py output/resume_tailored_<CompanyName>.tex
```
This runs pdflatex twice and returns the PDF path.

### Step 7: Show Changes Summary
After generating the PDF, provide:
```
## Keywords Added:
- [Keyword 1]: Added to Summary + [Role] experience
- [Keyword 2]: Added to [Role] experience
- [Keyword 3]: Moved to top of Skills section

## Sections Modified:
- Summary: [brief change description]
- [Role at Company]: [which bullets changed]
- Skills: [reordering details]

## Output:
- LaTeX: output/resume_tailored_<CompanyName>.tex
- PDF: output/resume_tailored_<CompanyName>.pdf

## Review Checklist:
- [ ] All additions are truthful (no fake skills)
- [ ] Keywords fit naturally (not keyword-stuffed)
- [ ] Original voice/tone maintained
- [ ] PDF renders correctly
```

## Critical Rules

### NEVER DO THIS:
- Add skills you don't have
- Fabricate experience or metrics
- Keyword-stuff (unnatural repetition)
- Change metrics or achievements
- Inflate scope (e.g., "led" when you "coordinated")
- Use Jinja2 variables — write complete LaTeX content directly

### ALWAYS DO THIS:
- Only add keywords for skills you actually possess
- Maintain honest scope (coordinated != led, managed roadmap != managed team)
- Keep original tone and voice
- Preserve all verified metrics exactly as-is
- Make keyword insertion feel natural
- Escape special LaTeX characters in all text content
- Use `templates/resume.tex` as structural reference only

## Example: Good vs Bad Keyword Insertion

**Job posting mentions:** "Experience with A/B testing and experimentation frameworks"

**Master resume bullet:**
"Increased conversion rate by 28% through iterative optimization"

**Bad (keyword-stuffed):**
"Increased conversion rate by 28% through A/B testing and experimentation frameworks using iterative optimization"

**Good (natural):**
"Increased conversion rate by 28\% through A/B testing and iterative experimentation"

## Output Location
- LaTeX file: `output/resume_tailored_<CompanyName>.tex`
- PDF file: `output/resume_tailored_<CompanyName>.pdf`

## Script Reference
| Script | Purpose | Example |
|--------|---------|---------|
| `scripts/notion_reader.py` | Read master resume | `venv/bin/python scripts/notion_reader.py page <id> --text` |
| `scripts/render_pdf.py` | Compile LaTeX to PDF | `venv/bin/python scripts/render_pdf.py output/file.tex` |
