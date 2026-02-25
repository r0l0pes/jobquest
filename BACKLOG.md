# JobQuest Backlog

Items deferred during implementation. Revisit when relevant.

---

## Claude Code subagent for automated post-run review

**What:** A `.claude/agents/resume-reviewer.md` definition that automatically runs after step 3 to compare the tailoring brief against the generated LaTeX and flag discrepancies without manual invocation.

**Why deferred:** The `.claude/agents/` subagent format from Claude Code docs was unverified at time of implementation. Created `/review-resume` as a skill instead (manual invocation). The skill works; the subagent would make it automatic.

**What to do:** Confirm the `.claude/agents/` frontmatter format from Anthropic docs, then create the agent definition and optionally hook it into `step_tailor_resume()` as a stage 3c validation pass.

**Priority:** Medium. The `/review-resume` skill covers the need for now.

---

## Hook review-resume into the pipeline as step 3c

**What:** After stage 3b generates LaTeX, run a lightweight LLM call that checks the brief's "Do Not Change" and "Bullet Insertion Targets" sections against the actual LaTeX output and logs any misses to the run dir.

**Why deferred:** Adds latency and an LLM call per run. Low priority until quality issues are confirmed to persist after the two-stage tailoring.

**What to do:** Add `step_review_tailor()` in `pipeline.py` using the free-tier LLM, triggered only when ATS score drops below threshold or on explicit flag.
