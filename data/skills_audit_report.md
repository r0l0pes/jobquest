# Resume Skills Audit Report

**Date:** 2026-05-26
**Files audited:**
- `.master_resume_cache_2f40fd98.txt` (cached Notion master resume)
- `prompts/resume_tailor.md` (resume tailoring prompt)
- `prompts/rodrigo-voice-lite.md` (voice enforcement rules)
- `~/Documents/VibeCoding/portifaria/src/components/sections/About.tsx` (portfolio About section)

---

## 1. Skills in Master Resume (from Notion)

### Growth & Product
Experimentation Frameworks, A/B Testing, Funnel & Cohort Analysis, Conversion Rate Optimisation (CRO), Product-Led Growth (PLG), Activation & Onboarding, Roadmap Prioritisation, OKRs, Stakeholder Alignment, Go-to-Market Planning

### Analytics
SQL, Python, GA4, Amplitude, Looker, Power BI, FullStory

### Tools
Jira, Linear, Productboard, Notion, Figma, Zapier, Retool

### AI-Assisted Workflows
Claude Code, GitHub Copilot, ChatGPT/Claude/Gemini, Voice AI (NLP, STT/TTS), ML Use Case Discovery and Validation

### Platforms & APIs
REST APIs, Payment Gateways, Google Maps API, WhatsApp Business API, VTEX E-commerce, IVR Platforms

---

## 2. Skills in Portfolio About (rodrigolopes.xyz)

### Core Skills
Product Strategy, Experimentation Frameworks, Discovery Methods, Roadmap Prioritization, OKRs, Stakeholder Alignment, Go-to-Market Planning

### Tools & Platforms
Jira, Linear, Productboard, Notion, Zapier, n8n, Retool, Granola, Figma, Claude Code, Cursor, Gemini, VS Code, Supabase, PostHog, REST APIs

### Analytics & Methods
SQL, A/B Testing, GA4, Mixpanel, Power BI, Tableau, LLM Workflows, Voice AI, Prompt Engineering

---

## 3. Gap Analysis

### 3a. Skills in Master Resume but NOT in Portfolio

| Skill | Location in Resume | Should add to Portfolio? | Reason |
|-------|-------------------|------------------------|--------|
| Funnel & Cohort Analysis | Growth & Product | ✅ **Yes** | Core growth PM skill, evidenced in every role |
| CRO (Conversion Rate Optimisation) | Growth & Product | ✅ **Yes** | Core growth skill, evidenced in C&A, HELLA, Natura |
| PLG (Product-Led Growth) | Growth & Product | ✅ **Yes** | Evidenced in Postscript role (self-serve, onboarding) |
| Activation & Onboarding | Growth & Product | ✅ **Yes** | Evidenced in Postscript and HELLA |
| Python | Analytics | ⚠️ Maybe | Mentioned but not deeply evidenced in bullet points |
| Amplitude | Analytics | ❌ No | Portfolio uses Mixpanel — pick one and align |
| Looker | Analytics | ❌ No | Less common, portfolio uses Tableau |
| FullStory | Analytics | ❌ No | Niche tool, evidenced in C&A (heatmap data) |
| GitHub Copilot | AI Workflows | ❌ No | Portfolio uses Cursor — pick one (Cursor is current) |
| ML Use Case Discovery | AI Workflows | ⚠️ Maybe | Evidenced in Postscript, could fold into "LLM Workflows" |
| Payment Gateways | Platforms | ❌ No | Too granular for portfolio, evidenced in bullet points |
| Google Maps API | Platforms | ❌ No | Too granular |
| WhatsApp Business API | Platforms | ❌ No | Too granular |
| VTEX E-commerce | Platforms | ❌ No | Deliberately removed from portfolio (too niche) |
| IVR Platforms | Platforms | ❌ No | Niche, fold into "Voice AI" |

### 3b. Skills in Portfolio but NOT in Master Resume

| Skill | Location in Portfolio | Should add to Resume? | Reason |
|-------|----------------------|----------------------|--------|
| **Discovery Methods** | Core Skills | ✅ **Yes** | Valid PM skill, should be in resume |
| **n8n** | Tools | ✅ **Yes** | Current tool, used in Postscript role |
| **Granola** | Tools | ❌ No | Current-use tool, not evidenced in past roles |
| **Cursor** | Tools | ✅ **Yes** | Should replace GitHub Copilot in resume |
| **VS Code** | Tools | ❌ No | Generic, not a differentiator |
| **Supabase** | Tools | ❌ No | Not evidenced in job bullet points (side project tool) |
| **PostHog** | Tools | ✅ **Yes** | Current analytics tool, relevant for growth PM roles |
| **Tableau** | Methods | ❌ No | Resume uses Looker — pick one |
| **Prompt Engineering** | Methods | ⚠️ Maybe | Current skill, relevant but not directly evidenced in bullet points |
| **Mixpanel** | Methods | ❌ No | Resume uses Amplitude — pick one (postscript used Amplitude according to bullet points) |

### 3c. Skills Not Evidenced by Any Job Bullet Point

| Skill | Source | Issue |
|-------|--------|-------|
| **VS Code** | Portfolio | Generic, not a role differentiator — fine to leave in portfolio |
| **Supabase** | Portfolio | No job bullet mentions it. OK for portfolio (side projects) but keep out of resume |
| **Granola** | Portfolio | No job bullet mentions it. Current-use tool, fine for portfolio |
| **Tableau** | Portfolio | No job bullet uses Tableau specifically. Bullet points reference Power BI and GA4 |

### 3d. Skills Evidenced in Bullet Points but NOT Listed in Skills Section

| Skill | Evidenced In | Where |
|-------|-------------|-------|
| **Salesforce Marketing Cloud** | C&A role | "integrated with Salesforce Marketing Cloud for order notifications" |
| **Userlane** | HELLA role | "implemented in-product onboarding (Userlane)" |
| **A/B Testing** (in bullet text) | Accenture/Natura | "structured A/B experiments" — listed in skills ✅ |
| **Google Maps API** (in bullet text) | Accenture/Natura | "address autocomplete (Google Maps)" — listed in resume ✅ |
| **WhatsApp Business API** (in bullet text) | C&A role | "earliest enterprise WhatsApp Business API deployments" — listed in resume ✅ |

---

## 4. Prompt Alignment Check

The `prompts/resume_tailor.md` says:
- "Reorder skills within each category to prioritize job-relevant skills first"
- "Do NOT add new skills not present in the master resume"
- "Never substitute one tool for another"

**Finding:** The prompt explicitly forbids adding skills not in the master resume. This means if the master resume is outdated, the tailored resumes will be too. The prompt is correct — it enforces honesty. But the **source data** (master resume) needs updating first.

**Voice rules** (`prompts/rodrigo-voice-lite.md`) don't affect skills directly, but the summary bridge rule requires "Name 2 things Rodrigo has actually built" — this is fine.

---

## 5. Recommended Changes

### Priority 1 — Update Master Resume Skills (in Notion)

These changes align the master resume with the portfolio and actual job experience:

**Growth & Product** — ADD these skills (evidenced in bullet points):
- `Discovery Methods` (not currently in resume)
- These are already present: CRO, PLG, Activation & Onboarding, Funnel & Cohort Analysis

**Analytics** — REPLACE to align with portfolio:
- `Amplitude` → keep if Postscript used it. Add `Mixpanel` if HELLA or C&A used it. Or pick one.
- `Looker` → replace with `Tableau` (current portfolio standard)
- `FullStory` → keep (evidenced in C&A heatmap work)

**Tools** — ADD:
- `n8n` (evidenced in Postscript automation work)
- `PostHog` (current analytics stack)
- `Cursor` (replace GitHub Copilot — current tool)
- REMOVE `GitHub Copilot` (replaced by Cursor)

**AI-Assisted Workflows** — UPDATE:
- Replace `ChatGPT/Claude/Gemini` with `LLM Workflows`
- Add `Prompt Engineering`

**Platforms & APIs** — No changes needed (already covers evidenced skills)

### Priority 2 — Update Portfolio About Section

- ADD to Core Skills: `CRO`, `PLG`, `Activation & Onboarding`, `Funnel & Cohort Analysis`
- These 4 skills are evidenced in bullet points and are core to the Growth PM role

### Priority 3 — Clean up applications.json Duplicates

The file has 18 entries but only 5 unique applications (Contentful 8×, Every 4×, Aignostics 2×, Sunday 2×, Sixt 4×). Dedup by URL is needed.

---

## 6. Exact Text Changes Required

### Master Resume — Notion Edit

**Growth & Product section** (line ~"Growth & Product:"):

**Current:**
```
Growth & Product: Experimentation Frameworks, A/B Testing, Funnel & Cohort Analysis, Conversion Rate Optimisation (CRO), Product-Led Growth (PLG), Activation & Onboarding, Roadmap Prioritisation, OKRs, Stakeholder Alignment, Go-to-Market Planning
```

**Recommended** (add Discovery Methods):
```
Growth & Product: Experimentation Frameworks, A/B Testing, Funnel & Cohort Analysis, Conversion Rate Optimisation (CRO), Product-Led Growth (PLG), Activation & Onboarding, Discovery Methods, Roadmap Prioritisation, OKRs, Stakeholder Alignment, Go-to-Market Planning
```

**Tools section:**

**Current:**
```
Tools: Jira, Linear, Productboard, Notion, Figma, Zapier, Retool
```

**Recommended:**
```
Tools: Jira, Linear, Productboard, Notion, Figma, Zapier, Retool, n8n, PostHog, Cursor
```

**AI-Assisted Workflows section:**

**Current:**
```
AI-Assisted Workflows: Claude Code, GitHub Copilot, ChatGPT/Claude/Gemini, Voice AI (NLP, STT/TTS), ML Use Case Discovery and Validation
```

**Recommended:**
```
AI-Assisted Workflows: Claude Code, Cursor, LLM Workflows, Prompt Engineering, Voice AI (NLP, STT/TTS), ML Use Case Discovery and Validation
```

**Analytics section:**

**Current:**
```
Analytics: SQL, Python, GA4, Amplitude, Looker, Power BI, FullStory
```

**Recommended** (add Mixpanel to align with portfolio):
```
Analytics: SQL, Python, GA4, Amplitude, Mixpanel, FullStory, Power BI, Tableau
```

### Portfolio About — Edit `About.tsx:16-19`

Add 4 growth skills to coreSkills array:
```
'Product Strategy', 'Experimentation Frameworks', 'Discovery Methods',
'Roadmap Prioritization', 'OKRs', 'Stakeholder Alignment', 'Go-to-Market Planning',
'CRO', 'PLG', 'Activation & Onboarding', 'Funnel & Cohort Analysis'
```
