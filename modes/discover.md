# Mode: discover — Job Discovery

When the user asks to discover jobs, search across multiple sources and add
results to `data/job_queue.md` for review.

## Target Roles

Three resume variants in Notion (Growth PM, Generalist, AI-PM). Search all three.
Cast wide — the variant matching happens in the pipeline, not in discovery.

### Growth PM (primary)

Senior Growth Product Manager, Senior Product Manager – Growth, Product Manager
Growth, Senior PM – Growth & Monetisation, Senior PM – Revenue Growth, Senior PM
– Core Growth, Principal Product Manager – Growth, Growth Product Lead

### Experimentation & Conversion

Senior Product Manager – Conversion, Senior PM – Experimentation, Senior PM –
A/B Testing & Experimentation, Senior PM – Funnel Optimisation, Senior PM –
Checkout / Conversion / Payments, Senior PM – Transactions

### Activation, Retention & Lifecycle

Senior PM – Self-Serve / Activation / Retention, Senior PM – User Activation,
Senior PM – Onboarding, Senior PM – Engagement & Retention, Senior PM – Lifecycle

### PLG / Revenue / Monetisation

Senior PM – Product-Led Growth, Senior PM – Monetisation, Senior PM – Revenue,
Senior PM – Pricing & Packaging

### E-commerce & Marketplace

Senior PM – E-commerce, Senior Product Manager – Marketplace, Senior PM –
Commerce & Payments

### Generalist PM

Senior Product Manager, Senior PM – Platform / Core Product, Product Manager,
Senior PM – B2B, Senior PM – SaaS, Senior Technical Product Manager

### AI PM

Senior AI Product Manager, AI Product Manager, Senior PM – AI, Senior PM –
AI/ML, Product Manager AI, Senior PM – AI Platform, Senior PM – Generative AI,
Senior PM – AI Agents, Senior PM – LLM, Senior PM – Machine Learning

## Target Locations

All of Germany, all of Spain. No city restrictions.
Remote EU roles also accepted.

Search each location separately with different keywords to surface different companies.
Never restrict searches to a single city — use country-wide terms:
- Germany: "Germany" OR "Deutschland" OR "DE"
- Spain: "Spain" OR "España" OR "ES"

## Execution

**Minimum 10 search rounds. Target 40-80 jobs per session.**
Volume is the goal. No company filters. No quality pre-judging.
If the role title matches, include it. The user reviews later.

### Search Strategy

Never search for specific companies. Only search by role title + location.
Rotate through these patterns across 10+ rounds.

**Platforms to cycle through:**
LinkedIn Jobs, StepStone, Indeed, Wellfound, Berlin Startup Jobs, InfoJobs,
Tecnoempleo, Arbeitnow, startup.jobs, Working Nomads, Google Jobs

**Query patterns (rotate, never repeat the same query):**

```
# Growth PM — Germany
"Senior Growth Product Manager" Germany site:linkedin.com/jobs
"Product Manager Growth" Germany -Berlin site:linkedin.com/jobs
"Senior Growth PM" Deutschland site:stepstone.de
"Growth Product Manager" Germany startup site:linkedin.com/jobs

# Growth PM — Spain
"Senior Growth Product Manager" Spain site:linkedin.com/jobs
"Product Manager Growth" España site:infojobs.net
"Growth Product Manager" Spain remote site:linkedin.com/jobs

# AI PM — Germany
"Senior AI Product Manager" Germany site:linkedin.com/jobs
"AI Product Manager" Deutschland site:stepstone.de
"Product Manager AI ML" Germany startup site:linkedin.com/jobs

# AI PM — Spain
"Senior AI Product Manager" Spain site:linkedin.com/jobs
"Product Manager AI" España site:infojobs.net

# Generalist PM — Germany
"Senior Product Manager" Germany startup site:linkedin.com/jobs
"Senior Produktmanager" Deutschland site:stepstone.de
"Senior Product Manager" Germany remote site:linkedin.com/jobs

# Generalist PM — Spain
"Senior Product Manager" Spain site:linkedin.com/jobs
"Senior Product Manager" España remote site:infojobs.net

# Startup-focused (cast wider net)
site:wellfound.com "Product Manager" Germany
site:berlinstartupjobs.com "Senior Product"
"Product Manager" Germany startup site:arbeitnow.com

# German language (catch companies that post only in German)
"Senior Produktmanager" Wachstum Deutschland
"Produktmanager" Berlin Startup site:stepstone.de

# Spanish language
"Senior Product Manager" España startup site:tecnoempleo.com
"Product Manager" Barcelona startup site:linkedin.com/jobs
```

### Rules

1. **No company names in queries.** Role title + location only.
2. **Maximum 2 jobs from the same company per session.** If you see the same
   company appearing, note it and move to the next query.
3. **10+ rounds minimum.** Do not stop at 3. The first 3 rounds surface big
   companies. Rounds 5-10 surface startups and lesser-known companies.
4. **Use different phrasings.** "Growth PM" vs "Product Manager Growth" vs
   "Senior PM Growth" return different results. Rotate.
5. **Search in German and Spanish** alongside English. Local-language queries
   find companies that English queries miss.

## Output Format

Append to `data/job_queue.md`:

```markdown
## [YYYY-MM-DD] — Discovered [N] jobs

### 🇩🇪 Germany

#### Growth PM
- [ ] <URL> | <Company> | <Title> | <Source> | <City/Remote>

#### AI PM
- [ ] <URL> | <Company> | <Title> | <Source> | <City/Remote>

#### Generalist PM
- [ ] <URL> | <Company> | <Title> | <Source> | <City/Remote>

### 🇪🇸 Spain
...
```

Group by country, then by role type. Include city or "Remote".

## Anti-Duplication

Before adding a job, check:
1. Already in this session's results?
2. `data/job_queue.md` — already queued from previous sessions?
3. `data/applications.json` — already applied?
4. More than 3 jobs from the same company already in this session? Skip.
