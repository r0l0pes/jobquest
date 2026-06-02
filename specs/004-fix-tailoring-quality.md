# PRD: Fix Resume Tailoring Quality Regression

**Priority:** P0
**Status:** Not Implemented
**Date:** 2026-05-19
**Last Updated:** 2026-05-27

## Implementation Status

| Item | Status | Notes |
|------|--------|-------|
| Rewrite `prompts/jd_analysis.md` with concrete instructions | ❌ Not Started | Blocked: needs dry-run validation time |
| Rewrite `prompts/resume_tailor.md` (keep good parts, remove anti-patterns) | ❌ Not Started | Depends on `jd_analysis.md` rewrite |
| Add WFP de-emphasis logic for non-AI roles | ❌ Not Started | Extend existing `_is_ai_heavy_jd()` in `pipeline.py` |
| Add `STRICT_COMPLIANCE` env flag (optional) | ❌ Not Started | Nice-to-have, not blocking |
| Dry-run validation on Every JD | ❌ Not Started | Needs manual review of brief output |
| Dry-run validation on non-AI role | ❌ Not Started | Verify WFP de-emphasis works |
| Dry-run validation on AI role | ❌ Not Started | Verify WFP still foregrounded |

**Blocked by:** `005-pipeline-token-crisis.md` consumed May 27 session. Next available slot.

---

## Problem Statement

The resume tailoring pipeline produces low-quality output for non-AI roles. The generated resumes:

- Fail to emphasize relevant experience (C&A, Accenture/Natura) over irrelevant experience (WFP for e-commerce/CRO roles)
- Miss critical keywords from the JD (e.g., "landing page optimization" for Every)
- Produce generic summaries that don't connect the candidate to the company's specific challenge
- Do not follow the tailoring brief's own instructions (compliance review flags HIGH issues but pipeline doesn't stop)

This is a **regression** introduced in commit `fdb1e95` (prompt architecture overhaul).

## Evidence

### The Every Application (Senior PM Acquisition & CRO)

- **Brief themes:** "Optimizing User Experience", "Data-Driven Decision Making", "Cross-Functional Collaboration" — all generic, none mention acquisition, landing pages, or CRO frameworks
- **Candidate matches:** Theme 3 → WFP "PARTIAL — make cross-functional collaboration more explicit" — instructs writer to make WFP MORE prominent for an e-commerce CRO role
- **Missing:** No mention of "landing page optimization" (appears 4x in JD), no experimentation framework-building narrative, no UX psychology language
- **Compliance review:** 1 HIGH, 2 MEDIUM issues — including "brief said do not change C&A/Accenture bullets but LaTeX rephrased them"

### The Contentful Application (Senior Product Manager)

- **Brief themes:** "Empowering Non-Technical Users", "Defining Ambiguous Scope", "Driving Enterprise Adoption" — generic
- **Candidate matches:** Theme 2 → WFP "PARTIAL (make scoping process explicit)" — again making WFP more prominent
- **De-emphasize:** C&A Brasil "less central to enterprise-scale solutions" — de-emphasizes the strongest checkout/CRO evidence for a role that needs growth PM experience

### The Aignostics Application (AI Product Manager)

- **Brief quality:** Good — themes are specific, WFP correctly foregrounded
- **Conclusion:** The XML "themes" format works for AI roles but fails for non-AI roles because the analyzer cannot distinguish relevance without concrete instructions

## Root Cause Analysis

### What Changed in `fdb1e95`

The prompt architecture overhaul replaced concrete instruction structures with abstract thematic structures:

| Element                  | Old (worked)                                                                                                               | New (broken)                                                               |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| **JD Analysis**          | Top 5 Priorities with exact JD phrases + Bullet Insertion Targets (Replace/With/Why) + Summary Strategy                    | XML themes + candidate matches + do_not_change + de_emphasize              |
| **Resume Tailor**        | Structured 5-step process (Job Analysis → Keyword Extraction → Resume Mapping → Content Refinement → Quality Verification) | Few-shot boundary examples + Bridge Rule + Quality Verification checklist  |
| **Analysis abstraction** | Concrete: "Priority 1: Landing page optimization — insert into C&A bullet"                                                 | Abstract: "Theme 3: Cross-Functional Collaboration — WFP is partial match" |
| **Writer guidance**      | Step-by-step process with explicit keyword prioritization                                                                  | Themes + examples, writer decides where to apply                           |

### Why the New Architecture Fails

1. **"Themes, not keywords" rule is too abstract for free-tier models.** The analyzer produces generic themes like "Data-Driven Decision Making" that apply to every PM role. The writer cannot derive specific actions from these themes.

2. **No bullet insertion targets means no keyword coverage.** The old prompt explicitly identified where JD keywords were missing and told the writer exactly which bullet to modify. The new prompt expects the writer to "naturally" find insertion points — it misses them.

3. **No summary strategy means weak summaries.** The old prompt told the analyzer: "The summary should foreground exactly these 3 themes, in this order, using this specific language." The new prompt says "The resume writer decides the summary" — leaving the most important paragraph to chance.

4. **WFP is chronologically first and the brief never says "minimize it."** The analyzer sees WFP as a "partial match" for collaboration and tells the writer to make it "more explicit." The old prompt would have said: "De-emphasize: WFP — humanitarian AI work with zero e-commerce relevance. Keep minimal."

### Why the Research Was Misapplied

The handoff cites: "2026 OpenAI Anthropic prompting standards (short XML-structured, few-shot over abstract rules, outcome-first)."

This research was about **reducing prompt length and using few-shot examples instead of lengthy abstract rules**. It was not about removing concrete instructions. The implementation conflated:

- ✅ Good: Short prompts with few-shot examples
- ❌ Bad: Removing structured instructions and replacing with abstract themes

The research says "specific constraints produce usable results, while vague prompts yield generic output." The new prompts are vague.

## Solution

### 1. Revert `jd_analysis.md` to Concrete Instructions (with improvements)

Bring back the structured output that produced actionable briefs:

- **Role Diagnosis** (keep)
- **Top 5 Priorities** — exact JD phrases, priority order
- **Candidate-to-Priority Mapping** — strongest evidence per priority
- **Bullet Insertion Targets** — exact bullet, Replace/With/Why
- **Summary Strategy** — exactly what to foreground, in what order, using what language
- **Do Not Change** — bullets already strong
- **De-emphasize** — what to minimize and why

**Add to De-emphasize:** Explicit instruction for non-AI roles: "WFP: AI/humanitarian work with no [domain] relevance — keep bullets minimal, do not insert [domain] keywords here."

### 2. Keep the Good Parts of `resume_tailor.md`

The new `resume_tailor.md` has valuable additions that should be preserved:

- ✅ Few-shot boundary examples (good reframe vs bad stuffing)
- ✅ Bridge Rule for summary
- ✅ Banned phrases enforcement
- ✅ Quality Verification checklist
- ✅ LaTeX escaping rules

Remove:

- ❌ "Themes, not keywords" framing (the brief already handles this)
- ❌ "The brief provides themes, not specific keywords" (the brief SHOULD provide specific keywords)

### 3. Add WFP De-Emphasis Rule for Non-AI Roles

In `pipeline.py`, the `_is_ai_heavy_jd()` function already detects AI roles. Extend this logic:

- If role is NOT AI-heavy: Add explicit de-emphasis instruction for WFP to the brief
- If role IS AI-heavy: Keep current behavior (WFP is relevant)

### 4. Make Compliance Review Block on HIGH Issues (Optional)

The compliance review (step 3c) currently logs issues but never blocks. Add an env flag `STRICT_COMPLIANCE=1` that:

- If review finds HIGH issues: Stop pipeline and show user the issue
- Default behavior (unset): Continue as now (log but don't block)

This gives users the choice without breaking the pipeline by default.

## Implementation Plan

### Phase 1: Fix Prompts (immediate)

1. Rewrite `prompts/jd_analysis.md` — restore concrete instruction structure
2. Rewrite `prompts/resume_tailor.md` — keep good parts, remove anti-patterns
3. Add WFP de-emphasis logic to `pipeline.py`

### Phase 2: Validation

1. Dry-run on Every JD — inspect brief quality
2. Dry-run on a generic non-AI role — verify WFP is de-emphasized
3. Dry-run on an AI role — verify WFP is still foregrounded
4. Run `pytest tests/ -v` — 22 tests must pass

## Success Criteria

- [ ] Brief for Every contains: "landing page optimization" as a priority, bullet insertion target for C&A/Accenture, summary strategy foregrounding acquisition + CRO
- [ ] Brief for non-AI role explicitly says "De-emphasize: WFP — keep minimal"
- [ ] Brief for AI role correctly foregrounds WFP
- [ ] Generated resume summary names 2 concrete things + 1 company challenge
- [ ] Compliance review shows PASS or only LOW issues
- [ ] `pytest tests/ -v` — all 22 tests pass
