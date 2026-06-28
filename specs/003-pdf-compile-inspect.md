# P3: PDF Compile-and-Inspect Loop — Mandatory Quality Gate

**Status:** Spec
**Date:** 2026-06-04
**Source:** ai-job-search `/apply` Step 5 — Compile & Inspect PDFs

---

## What

Add a mandatory PDF compile-and-inspect step after LaTeX generation. After
compiling, visually inspect the PDF for layout bugs: orphaned entry titles,
page budget violations, font mismatches. Iterate until clean.

## Why

Currently `render_pdf.py` compiles and returns success/failure based on the
pdflatex exit code. But LaTeX exit code 0 does NOT guarantee a good layout.
Common silent failures:

- **Orphaned `\cventry` titles** — a job title sits alone at the bottom of
  page 1, its bullets spill to page 2
- **CV spills to page 3** — content overflows, but pdflatex doesn't error
- **Cover letter spills to page 2** — signature block cut off
- **Font mismatches** — bullet list uses wrong font in cover letter
- **Awkward whitespace** — large gaps from over-aggressive `\vspace`

ai-job-search mandates visual PDF inspection after every compile with a
re-Read-the-PDF loop until layout is clean. JobQuest should do the same.

## How

### Inspection Rules

After `pdflatex` succeeds:

1. **Check page count**
   - CV: exactly 2 pages (not 1, not 3+)
   - Cover letter: exactly 1 page (not 2+)

2. **Check for orphaned entries** (CV)
   - A `\cventry` title line must never sit at the bottom of a page with
     bullets on the next page
   - Detection: read the PDF, check for "title text at page bottom + bullets
     at page top"

3. **Check for awkward whitespace** (CV)
   - Section headings isolated at top of page 2 with <3 lines below
   - Large gaps between sections (>2 empty lines equivalent)

4. **Check cover letter**
   - Signature block visible, not cut off
   - Bullet font matches body font (both Raleway-Medium)

### Fixes (when inspection fails)

| Problem | Fix |
|---|---|
| Orphaned CV entry title | Add `\needspace{5\baselineskip}` before `\cventry` |
| CV spills to page 3 (trailing section) | `\enlargethispage{2-3\baselineskip}` on late section |
| CV spills to page 3 (significant content) | Relevance-weighted cutting (see cutting algorithm below) |
| Cover letter spills to 2 pages | Trim content using relevance-weighted logic |
| Cover letter bullet font mismatch | Close `\lettercontent{}`, wrap itemize in Raleway fontspec block |

### Relevance-Weighted Cutting Algorithm

When the CV needs to shrink (genuine overflow, not near-miss):

For every candidate line, score:
1. **Relevance to THIS posting** — does it hit a named tool, keyword, or
   responsibility from the JD?
2. **Uniqueness** — is it the only place this claim appears?
3. **Narrative load** — does the cover letter depend on it?

Cut the lowest-total-score line first, regardless of which section it sits in.

**Pitfall to avoid:** Do NOT mechanically cut "oldest role first" — an older
role that directly matches the JD is worth more than a recent role that doesn't.

### Implementation

**Modify `scripts/render_pdf.py`** (or new module `modules/pdf_inspector.py`):

```python
def compile_and_inspect(tex_path: str, doc_type: str, max_retries: int = 3) -> dict:
    """
    Compile LaTeX and inspect PDF. Retry with fixes up to max_retries.
    
    Returns: {"ok": bool, "pdf_path": str, "pages": int, "issues": list, "fixes": list}
    """
    for attempt in range(max_retries):
        result = _compile(tex_path)
        if not result["ok"]:
            return result  # LaTeX error
        
        issues = _inspect(result["pdf_path"], doc_type)
        if not issues:
            return result  # Clean
        
        _apply_fixes(tex_path, issues)
    
    return {"ok": False, "error": f"Layout issues persist after {max_retries} attempts"}
```

**Inspection via LLM:**
- Read PDF pages as images (or extract text)
- Send to a vision-capable model with inspection checklist
- Model returns: page count, orphaned entries, whitespace issues
- Model can also read the PDF text via pdftotext for structural checks

Alternative: pdftotext + regex for page count and structural checks
(more reliable, no LLM tokens). LLM only for visual issues if needed.

## Changes

| File | Change |
|---|---|
| `scripts/render_pdf.py` | Add `compile_and_inspect()` with retry loop |
| `modules/pipeline.py` | Call `compile_and_inspect()` instead of raw `render_pdf` in steps 7 and 10 |
| `templates/resume.tex` | Add `\usepackage{needspace}` to preamble |

## Implementation Plan

1. Add `\usepackage{needspace}` to `templates/resume.tex`
2. Add `_inspect_pdf()` to `scripts/render_pdf.py` — page count + structural checks
3. Add `_apply_fixes()` — needspace insertion, enlargethispage, content warnings
4. Wire `compile_and_inspect()` into `modules/pipeline.py` steps 7 and 10
5. Add relevance-weighted cutting guidance to `prompts/resume_tailor.md`

## Test Scenarios

| Category | Scenario |
|---|---|
| Happy path | CV compiles clean, 2 pages, no orphans → no fixes needed |
| Happy path | Cover letter compiles clean, 1 page → no fixes needed |
| Edge case | CV has orphaned entry → needspace added, recompile, passes |
| Edge case | CV 2.02 pages (near miss) → enlargethispage, recompile, passes |
| Edge case | CV 3 pages (genuine overflow) → warns user, suggests cutting |
| Edge case | Cover letter ~1.1 pages → warns, suggests trimming |
| Error path | pdflatex compile error → returns error, no inspection attempted |
| Error path | Layout issues persist after 3 retries → returns error with issue log |
| Integration | Pipeline step 7 uses compile_and_inspect, logs inspection results |
| Integration | Pipeline step 10 uses compile_and_inspect for cover letter |
