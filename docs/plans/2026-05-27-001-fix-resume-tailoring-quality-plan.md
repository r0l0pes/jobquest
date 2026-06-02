---
title: Fix Resume Tailoring Quality Regression
type: fix
status: active
date: 2026-05-27
origin: specs/004-fix-tailoring-quality.md
---

# Fix Resume Tailoring Quality Regression

## Summary

Revert the abstract "themes-only" prompt architecture introduced in commit `fdb1e95` back to concrete, actionable instructions in the JD analysis brief, while preserving the valuable few-shot boundary examples and quality verification checklist from the newer prompt versions. Add automatic WFP de-emphasis for non-AI roles. Validate with dry-runs on three role types.

---

## Problem Frame

Commit `fdb1e95` replaced concrete instruction structures with abstract thematic structures in the resume tailoring pipeline. The result:

- Generic themes like "Data-Driven Decision Making" that apply to every PM role
- No bullet insertion targets, causing missed keywords
- No summary strategy, leaving the most important paragraph to chance
- WFP chronologically first and never explicitly de-emphasized for non-AI roles
- Compliance review flags HIGH issues but pipeline never blocks

The old architecture worked. The new one fails for non-AI roles because free-tier models cannot derive specific actions from abstract themes.

---

## Requirements

- R1. JD analysis brief must produce concrete instructions: Top 5 Priorities with exact JD phrases, Candidate-to-Priority Mapping, Bullet Insertion Targets (Replace/With/Why), Summary Strategy, Do Not Change list, De-emphasize list.
- R2. Resume tailor prompt must keep: few-shot boundary examples, Bridge Rule for summary, Banned phrases enforcement, Quality Verification checklist, LaTeX escaping rules.
- R3. Resume tailor prompt must remove: "Themes, not keywords" framing, "The brief provides themes, not specific keywords" instruction.
- R4. For non-AI roles, the brief must explicitly de-emphasize WFP with domain-specific reasoning.
- R5. For AI roles, WFP must remain foregrounded (current behavior).
- R6. Generated resume summaries must name 2 concrete things Rodrigo has built + 1 company challenge he has solved, backed by Experience bullets, max 3 sentences.
- R7. Banned word list updated: add "grit" to `prompts/rodrigo-voice-lite.md`.
- R8. Optional: `STRICT_COMPLIANCE` env flag that blocks pipeline on HIGH compliance issues.
- R9. All 22 existing tests must pass after changes.

---

## Scope Boundaries

- In scope: prompt rewrites, pipeline.py WFP de-emphasis logic, voice rule update, optional compliance flag.
- Out of scope: Changing LLM provider selection, web UI changes, ATS check logic, form filler.
- Deferred to Follow-Up Work: A/B testing old vs new prompt quality with scoring rubric.

---

## Context & Research

### Relevant Code and Patterns

- `prompts/jd_analysis.md` — current abstract XML brief (~50 lines)
- `prompts/resume_tailor.md` — current few-shot + Bridge Rule version
- `prompts/rodrigo-voice-lite.md` — voice rules, ~500 tokens
- `modules/pipeline.py` — `_is_ai_heavy_jd()` detects AI roles; step logic injects prompts
- `modules/llm_client.py` — prompt building and LLM calls
- `templates/resume.tex` — LaTeX template the tailor modifies

### Institutional Learnings

- The old prompt architecture (pre-`fdb1e95`) produced better results for non-AI roles.
- The new prompt's few-shot examples and boundary rules are genuinely valuable and should be preserved.
- The "grit" incident demonstrates banned-word enforcement is load-bearing.
- Targeted edits mode (`TARGETED_EDITS=1`) is now default — prompts must work with JSON patch output, not full LaTeX.

---

## Key Technical Decisions

- **Prompt architecture**: Hybrid — restore concrete instruction structure from pre-`fdb1e95`, merge in few-shot boundary examples and quality checklist from post-`fdb1e95`. Best of both worlds.
- **WFP de-emphasis trigger**: Reuse existing `_is_ai_heavy_jd()` in `pipeline.py`. If `False`, inject a de-emphasis instruction into the brief system prompt. No new role detection needed.
- **Compliance flag**: Optional env var `STRICT_COMPLIANCE=1`. When set and step 3c finds HIGH issues, pipeline raises an exception with the issue details. Default (unset) preserves current behavior.
- **Validation posture**: Dry-run on three real JDs (AI role, growth/PM role, generalist role) before marking done.

---

## Open Questions

### Resolved During Planning

- **Q: Should we fully revert `fdb1e95` or merge old+new?** → Merge. The old structure worked for instructions; the new additions (few-shot, Bridge Rule, banned words, checklist) improve quality.
- **Q: Where does WFP de-emphasis live?** → In `pipeline.py` as a conditional prompt injection, not in the static prompt files. Keeps prompts generic.

### Deferred to Implementation

- **Q: Exact wording of the de-emphasis instruction** — depends on seeing how the model responds. Start with explicit: "WFP: AI/humanitarian work with no [domain] relevance — keep bullets minimal, do not insert [domain] keywords here."

---

## Implementation Units

### U1. Rewrite `prompts/jd_analysis.md` with hybrid concrete+few-shot architecture

**Goal:** Restore actionable brief structure while keeping valuable new additions.

**Requirements:** R1, R6

**Dependencies:** None

**Files:**
- Modify: `prompts/jd_analysis.md`
- Test: `tests/test_prompts.py` (new — characterization tests for prompt structure)

**Approach:**
- Restore sections: Role Diagnosis, Top 5 Priorities (exact JD phrases), Candidate-to-Priority Mapping, Bullet Insertion Targets (Replace/With/Why), Summary Strategy, Do Not Change, De-emphasize.
- Keep: XML structure for readability, few-shot examples for boundary clarity.
- Ensure targeted-edits compatible: brief should guide JSON patch generation, not full LaTeX rewriting.

**Execution note:** Characterization-first — write a test that asserts the prompt contains the key structural sections before modifying the file.

**Patterns to follow:** Pre-`fdb1e95` prompt structure (from git history if needed).

**Test scenarios:**
- **Happy path:** Prompt contains all required sections (Top 5 Priorities, Bullet Insertion Targets, Summary Strategy, Do Not Change, De-emphasize)
- **Edge case:** Prompt length under 500 lines (avoid bloat)
- **Integration:** Running dry-run with new prompt produces brief containing "Replace/With/Why" instructions

**Verification:**
- `pytest tests/test_prompts.py -v` passes
- Dry-run on Every JD produces brief with "landing page optimization" as a priority

---

### U2. Rewrite `prompts/resume_tailor.md` — keep good, remove anti-patterns

**Goal:** Remove "themes not keywords" framing, preserve valuable additions.

**Requirements:** R2, R3, R6

**Dependencies:** U1

**Files:**
- Modify: `prompts/resume_tailor.md`
- Test: `tests/test_prompts.py`

**Approach:**
- Remove: "Themes, not keywords" paragraph, "The brief provides themes, not specific keywords" instruction.
- Keep: Few-shot boundary examples, Bridge Rule for summary, Banned phrases enforcement, Quality Verification checklist, LaTeX escaping rules.
- Update summary rule to match R6: "Name 2 things Rodrigo has built that this company specifically needs, using his language. Then name 1 company challenge he has solved before. No more than 3 sentences. Every claim must be backed by an Experience bullet."

**Test scenarios:**
- **Happy path:** Prompt contains few-shot examples, Bridge Rule, banned phrases, quality checklist
- **Happy path:** Prompt does NOT contain "themes, not keywords" or "brief provides themes"
- **Edge case:** Prompt length reasonable (< 300 lines)

**Verification:**
- `pytest tests/test_prompts.py -v` passes
- Dry-run summary follows the 2+1 sentence rule with Experience bullet backing

---

### U3. Add WFP de-emphasis logic for non-AI roles

**Goal:** Automatically instruct the brief to minimize WFP for non-AI roles.

**Requirements:** R4, R5

**Dependencies:** U1

**Files:**
- Modify: `modules/pipeline.py`
- Test: `tests/test_pipeline.py` (new test for `_is_ai_heavy_jd` + de-emphasis injection)

**Approach:**
- In `step_analyze_jd` or where the brief prompt is assembled, check `_is_ai_heavy_jd(jd_text)`.
- If `False`: append de-emphasis instruction: "WFP: AI/humanitarian work with no [detected_domain] relevance — keep bullets minimal, do not insert [detected_domain] keywords here."
- If `True`: append emphasis instruction (or none, preserving current behavior).
- `[detected_domain]` can be inferred from the role title or JD keywords (growth, e-commerce, SaaS, etc.).

**Patterns to follow:** Existing `_is_ai_heavy_jd()` usage in `pipeline.py`.

**Test scenarios:**
- **Happy path (non-AI growth role):** `_is_ai_heavy_jd` returns False → brief contains WFP de-emphasis
- **Happy path (AI role):** `_is_ai_heavy_jd` returns True → brief does NOT contain WFP de-emphasis
- **Edge case (ambiguous role):** Default to non-AI behavior (safer — de-emphasize WFP)
- **Integration:** Dry-run on non-AI JD shows WFP bullets unchanged or minimized

**Verification:**
- `pytest tests/test_pipeline.py -v` passes
- Dry-run on Every JD: brief explicitly says "De-emphasize: WFP"
- Dry-run on AI JD: brief foregrounds WFP

---

### U4. Update voice rules — add "grit" to banned words

**Goal:** Prevent generic buzzword from appearing in generated resumes.

**Requirements:** R7

**Dependencies:** None (can parallelize with U1)

**Files:**
- Modify: `prompts/rodrigo-voice-lite.md`
- Test: `tests/test_prompts.py`

**Approach:**
- Add "grit" to the banned phrases list with brief rationale.

**Test scenarios:**
- **Happy path:** `rodrigo-voice-lite.md` contains "grit" in banned list

**Verification:**
- `pytest tests/test_prompts.py -v` passes

---

### U5. Add optional `STRICT_COMPLIANCE` env flag

**Goal:** Allow users to block pipeline on HIGH compliance issues.

**Requirements:** R8

**Dependencies:** None (can parallelize with U1-U3)

**Files:**
- Modify: `modules/pipeline.py`
- Test: `tests/test_pipeline.py`

**Approach:**
- In `step_review_tailoring`, after running compliance review:
  - If `os.getenv("STRICT_COMPLIANCE") == "1"` and any HIGH issue found:
    - Raise `ComplianceError` with issue details, halting pipeline
  - Else: log warning and continue (current behavior)
- Add `ComplianceError` exception class if not existing.

**Test scenarios:**
- **Happy path (strict off):** HIGH issue logged, pipeline continues
- **Happy path (strict on, no issues):** Pipeline continues normally
- **Error path (strict on, HIGH issue):** Pipeline raises `ComplianceError` with details
- **Edge case (strict on, only MEDIUM/LOW):** Pipeline continues

**Verification:**
- `pytest tests/test_pipeline.py -v` passes
- Manual test: `STRICT_COMPLIANCE=1 python apply.py "URL" --dry-run` halts on HIGH issue

---

### U6. Validate with dry-runs and update smoke tests

**Goal:** Verify the fixes work on real JDs and all tests pass.

**Requirements:** R9

**Dependencies:** U1, U2, U3, U4, U5

**Files:**
- Modify: `tests/test_smoke.py` (if step count or behavior changes)
- Test: `tests/test_prompts.py`, `tests/test_pipeline.py`

**Approach:**
- Dry-run on Every JD (growth/CRO role): inspect brief quality
- Dry-run on a generic non-AI role: verify WFP de-emphasis
- Dry-run on an AI role: verify WFP foregrounded
- Run `pytest tests/ -v` — all 22+ tests pass

**Test scenarios:**
- **Integration (Every JD):** Brief contains "landing page optimization" priority, bullet insertion target for C&A/Accenture, summary strategy foregrounding acquisition + CRO
- **Integration (non-AI):** Brief explicitly says "De-emphasize: WFP — keep minimal"
- **Integration (AI):** Brief correctly foregrounds WFP
- **Integration (summary):** Generated summary names 2 concrete things + 1 company challenge
- **Integration (compliance):** Review shows PASS or only LOW issues

**Verification:**
- `pytest tests/ -v` — all tests pass
- Dry-run outputs inspected and approved

---

## System-Wide Impact

- **Interaction graph:** Prompt changes affect steps 3 (JD analysis), 3b (resume tailor), 3c (compliance review). No other steps touched.
- **Error propagation:** `STRICT_COMPLIANCE=1` adds a new failure mode — pipeline halts with clear error message.
- **State lifecycle risks:** None — prompts are stateless.
- **API surface parity:** No CLI or UI changes.
- **Unchanged invariants:** LLM provider selection, ATS check logic, form filler, tracker, PDF compilation.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Restored concrete prompts may be too long for small-context providers (Groq 12K) | Already handled by `_condense_prompt()` from `005` fix. Brief is ~50% shorter than pre-`fdb1e95` due to XML structure. |
| Free-tier models still fail to follow concrete instructions | Few-shot examples and quality checklist provide guardrails. Validation on 3 real JDs before marking done. |
| WFP de-emphasis logic mis-classifies hybrid AI+growth roles | Default to non-AI (de-emphasize) — safer for quality. Can tune `_is_ai_heavy_jd()` threshold later. |

---

## Documentation / Operational Notes

- Update `AGENTS.md` or `SESSION_HANDOFF.md` with new banned word.
- Document `STRICT_COMPLIANCE=1` in CLI help if adding to argparse.

---

## Sources & References

- **Origin document:** `specs/004-fix-tailoring-quality.md`
- Related code: `prompts/jd_analysis.md`, `prompts/resume_tailor.md`, `prompts/rodrigo-voice-lite.md`, `modules/pipeline.py`
- Related commit: `fdb1e95` (regression introduction)
