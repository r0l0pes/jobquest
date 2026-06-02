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

**General / Local Platforms:**
LinkedIn Jobs, StepStone, Indeed, Wellfound, Berlin Startup Jobs, InfoJobs,
Tecnoempleo, Arbeitnow, startup.jobs, Google Jobs

**Remote-Only Job Boards (100% verified remote):**
We Work Remotely, 4dayweek.io, Jobspresso.co, Himalayas.app, FlexJobs,
Nodesk.co, Working Nomads, TrulyRemote.co, Flexa.careers, Jobgether,
Oomple.com, Remote OK, Remotive, RemoteOrNothing, RemoteRocketship,
CareerVault.io, DailyRemote.com, weloveproduct.co, RemotePMJobs.com,
ProductJobsAnywhere.com, Remote-Only.dev, Remotely.de, euRemoteJobs.com,
Arc.dev

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

# Remote-only boards (prioritize for remote-first roles)
site:weworkremotely.com "Product Manager" Europe
site:4dayweek.io "Product Manager" remote
site:jobspresso.co "Product Manager" Europe
site:himalayas.app "Product Manager" Europe timezone
site:flexjobs.com "Product Manager" remote
site:nodesk.co "Product Manager" remote
site:workingnomads.com "Senior Product Manager" remote
site:trulyremote.co "Product Manager" remote
site:flexa.careers "Product Manager" remote
site:jobgether.com "Product Manager" remote
site:oomple.com "Product Manager" remote
site:remotely.de "Product Manager" Germany
site:euremotejobs.com "Product Manager" Europe
site:remoteok.com "Senior Product Manager" remote
site:remotive.com "Senior Product Manager" remote
site:remoterocketship.com "Senior Product Manager" Europe
site:careervault.io "Product Manager" remote
site:dailyremote.com "Product Manager" Europe
site:weloveproduct.co "Senior Product Manager" remote
site:remoteornothing.com "Product Manager" remote
site:remotepmjobs.com "Senior Product Manager"
site:productjobsanywhere.com "Product Manager" EMEA
site:arc.dev "Product Manager" remote

# Experimentation-specific (niche board, high-signal for CRO/Experiment roles)
site:experimentationjobs.com "Product Manager"
site:experimentationjobs.com "Growth" Europe
site:experimentationjobs.com "Conversion" Europe

# German language (catch companies that post only in German)
"Senior Produktmanager" Wachstum Deutschland
"Produktmanager" Berlin Startup site:stepstone.de

# Spanish language
"Senior Product Manager" España startup site:tecnoempleo.com
"Product Manager" Barcelona startup site:linkedin.com/jobs
```

### Rules

1. **No company names in queries.** Role title + location only.
2. **No company filtering.** If a company has multiple relevant roles, include all of them. The user decides which are worth applying to.
3. **10+ rounds minimum.** Do not stop at 3. The first 3 rounds surface big
   companies. Rounds 5-10 surface startups and lesser-known companies.
4. **Use different phrasings.** "Growth PM" vs "Product Manager Growth" vs
   "Senior PM Growth" return different results. Rotate.
5. **Search in German and Spanish** alongside English. Local-language queries
   find companies that English queries miss.

## Output Format

Add discovered jobs to `data/job_queue.html` by appending entries to the
`JOBS` array inside the `<script>` tag. Format each entry as:

```javascript
{ company: "CompanyName", title: "Role Title", url: "https://...", location: "City, Country", country: "de", roleType: "growth", date: "YYYY-MM-DD", source: "linkedin" }
```

Fields:

- `country`: "de" or "es" (or "remote" for location-independent roles)
- `roleType`: "growth", "ai", or "generalist"
- `date`: date the job was posted or discovered
- `source`: platform where found (linkedin, stepstone, infojobs, wellfound,
  weworkremotely, remoteok, himalayas, remotive, remoterocketship, weloveproduct,
  remoteornothing, remotepmjobs, productjobsanywhere, arc, experimentationjobs, etc.)

Group entries by country, then by role type, separated by comments.

## Anti-Duplication

Before adding a job, check the `JOBS` array in `data/job_queue.html` for:

- Same URL → skip
- Same company + same title → skip
- More than 2 jobs from the same company already in the array → skip
