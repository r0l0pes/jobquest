# 010: August 2026 PM Market Targeting

**Status:** Implemented (re-verified 2026-09-13)
**Date:** 2026-08-29
**Scope:** Germany, Spain, Denmark, France, and EU/EMEA-remote Product, Growth Product, and AI Product roles

## Evidence standard

Use dated live postings and current job-board snapshots as directional signals, not as a census. Exclude undated listings, obvious repost farms, non-target countries, and search-result counts from fit conclusions. Keep company-specific requirements in the job description rather than treating market signals as candidate facts.

## Current signals

- General PM roles repeatedly ask for end-to-end ownership, discovery, strategy and roadmap, customer research, cross-functional work with Engineering/Design/Data, and measurable outcomes.
- Growth PM roles repeatedly ask for funnel ownership, activation, retention, monetization, experimentation, analytics, and KPI ownership.
- AI PM roles increasingly ask for production AI/ML or GenAI delivery, LLM/agent workflows, evaluation and observability, responsible AI/governance, technical fluency, and the ability to prototype or work closely with engineers.
- Germany has strong English-friendly Berlin and country-wide supply, while German is a meaningful filter for locally regulated, payroll, and traditional-market roles.
- Spain has substantial Barcelona/Madrid supply and remote roles. English is common in international technology employers; Spanish remains valuable for local-market and customer-facing roles.
- Denmark is smaller but concentrated around Copenhagen and English-friendly international companies. Technical/product ownership, analytics, experimentation, and stakeholder collaboration recur; Danish is role-dependent rather than a universal gate.
- France has the largest visible Paris-centered supply among the four in the sampled sources. English-only roles exist, but French is frequently required for local-market, regulated, and customer-facing roles.
- EU-remote roles are a distinct channel and should be searched by country eligibility, not treated as location-free. Employer-of-record, tax, time-zone, and language constraints still apply.

## Implementation decisions

1. Add Denmark (`dk`) and France (`fr`) to discovery, with country and language query variants.
2. Keep country-specific location whitelists so broad Exa results do not become false positives.
3. Expand career preferences to the four target countries while retaining Berlin and EU/EMEA remote as priorities.
4. Add market context to fit evaluation as a conservative interpretation aid. It must never add unsupported resume claims.
5. Refresh Gemini model identifiers and add OpenRouter DeepSeek V4 Flash as an explicitly selectable writing option.
6. Keep application submission manual. `--auto-apply` remains an internal pipeline shortcut for bypassing a review gate and does not submit applications.

## Source snapshots

- Glassdoor Germany, August 2026: <https://www.glassdoor.com/Job/germany-senior-product-manager-jobs-SRCH_IL.0,7_IN96_KO8,30.htm>
- Arbeitnow Germany, August 2026: <https://www.arbeitnow.com/jobs/product-manager>
- EnglishJobs Germany, August 2026: <https://englishjobs.de/jobs/product_manager>
- Clarivate Senior Product Manager, Barcelona, posted 2026-06-22: <https://careers.clarivate.com/job/JREQ135893/Senior-Product-Manager>
- Workable Spain current search: <https://jobs.workable.com/search/spain/product-manager-jobs>
- EnglishJobs Spain, August 2026: <https://englishjobs.es/jobs/product_manager>
- EnglishJobs France, August 2026: <https://englishjobs.fr/jobs/product_manager>
- Built In France current search: <https://builtin.com/jobs/eu/france/product/search/product-manager>
- EnglishJobs Denmark/Copenhagen, August 2026: <https://englishjobs.dk/in/kobenhavn/product_manager>
- Remote Rocketship Denmark, current snapshot: <https://www.remoterocketship.com/country/denmark/jobs/product-manager/>
- Remote Rocketship EU senior PM snapshot: <https://www.remoterocketship.com/country/europe/jobs/senior-product-manager/>
- Google Gemini model lifecycle documentation, accessed 2026-08-29: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions>
- DeepSeek V4 Flash research/model identifier evidence: <https://arxiv.org/html/2606.19348v1> and <https://arxiv.org/html/2608.02372v1>

## Re-verification 2026-09-13

Re-checked 15 days after the baseline. Findings (evidence in
`research/market-sep-2026/SEP-2026-RECHECK.md`):

1. **No material market-structure change.** Salary benchmarks moved under 1% on
   Levels.fyi (DE €94,989 -> €95,334, 6 Sep 2026; Berlin €98,312 -> €98,170,
   3 Sep 2026; Paris €75,562 -> €76,207, 29 Aug 2026; Copenhagen avg DKK 790,000,
   29 Aug 2026). The recurring requirement patterns held.
2. **AI-skill posting prevalence is ~24% EU-wide**, not 61%. Best corpus count:
   3,504 live EU product listings, 24% name at least one AI skill, vs 19% on
   7,422 engineering listings (workinproduct.eu, snapshot 31 Jul 2026). Demand is
   seniority-weighted (11.8% mid-level -> 44.8% principal). The CAVISIO 75% figure
   is practitioner *usage*, not posting prevalence, and must not be cited as the latter.
3. **AI PM salary premium is unsubstantiated.** The only same-source like-for-like
   German comparison shows KI Product Manager (€71.0K median) *below* Produktmanager
   (€75.5K median), i.e. -6% (Robert Half 2026). Use employer-disclosed bands instead.
4. **EU AI Act high-risk deadlines were deferred** by Regulation (EU) 2026/1744
   (OJ 24 Jul 2026, in force 27 Jul 2026): Annex III standalone 2 Aug 2026 ->
   **2 Dec 2027**; Annex I embedded 2 Aug 2027 -> **2 Aug 2028**. Art. 50
   transparency obligations and Commission GPAI enforcement powers were **not**
   deferred and apply from **2 Aug 2026**. "EU AI Act awareness" in a Sep 2026 JD
   means transparency, AI-content marking and GPAI duties, not Annex III conformity.
5. **EU Pay Transparency Directive** (2023/970) transposition deadline passed
   7 Jun 2026 with only four member states holding full implementing law; the
   pre-employment salary-range duty applies from 7 Jun 2027. Salary disclosure in
   postings will rise slowly and unevenly, not abruptly.
6. **Posting-level facts decay fast.** Modjo's AI PM was recorded filled on 29 Aug
   and re-opened on 28 Aug as a new listing. Re-check every employer ATS on
   application day; salary and structural numbers hold for about a quarter.
7. **Requirement expectations moved; see `research/market-sep-2026/REQUIREMENT-DELTA.md`.**
   From 13 postings published 29 Aug - 13 Sep 2026, three changes affect fit scoring:
   - AI PM has **forked into two opposite archetypes**. *Deep technical AI PM* (N26,
     Barcelona, 11 Sep) demands production GenAI/agent depth (RAG, ReAct,
     function-calling, state/memory, multi-agent orchestration, fine-tuning, eval
     framework design, latency) and states verbatim that "utilizing off-the-shelf AI
     productivity tools is not sufficient". *AI-native builder PM* (Product Hunter,
     Madrid, 3 Sep) makes Cursor/Claude/n8n/Zapier fluency an indispensable requirement
     with no years-of-experience gate. A single "AI-literate PM" score cannot serve both.
   - Evaluation vocabulary is now **ML-engineering grade**: precision/recall/F1,
     confidence thresholds, hallucination rates, inference latency, retraining cadence,
     cost/explainability trade-offs.
   - **Interviews are now tested unaided.** Libra/Wolters Kluwer (3 Sep) disqualifies
     AI-assisted interview answers and requires in-person presence without virtual
     backgrounds. AI fluency is required on the job and forbidden in the interview.
8. **Fit-evaluation context refreshed to September 2026.**
   `prompts/fit_evaluation.md` market context updated to reflect item 7, the corrected
   AI Act framing (transparency/GPAI live 2 Aug 2026; Annex III deferred to 2 Dec 2027),
   ARR/GM ownership on AI PM roles, the new platform stack, and the weakened local-language
   gate for AI roles. The candidate profile is unchanged: no resume claim is added by this
   refresh, and the "never invent resume claims" guard is preserved and tested.
   A drift test now asserts the load-bearing vocabulary stays present.
9. **Deep phase supersedes the two-archetype framing.**
   `research/pm_market_deep_phase_sep2026.md` (64-role stratified sample across
   DE/ES/DK/FR plus a Q4/2025 comparator) refines the AI PM fork into **five work
   architectures** — AI Application/Agents, AI Platform/ML/Infra, AI
   Automation/Internal/Vertical, Growth/PLG/Lifecycle, and Generalist/Technical/Domain
   — and adds a **0-4 hiring-gate scale**, **bundle** co-occurrence thinking, and
   **seniority-as-scope**. It also downgrades two baseline claims: "AI-native is
   baseline for every PM" is segment-level, not universal, and the AI PM salary
   premium is not confirmed. Raw job-board counts are rejected as a time series.
   `prompts/fit_evaluation.md` was rebuilt on this framework; the two-archetype
   wording in item 7 is retained only as the AI-Application subset.

## Non-conclusions

The sources do not support a precise country-wide vacancy count, salary benchmark, or universal language requirement. Aggregator counts vary materially and are retained only as discovery-volume signals.
