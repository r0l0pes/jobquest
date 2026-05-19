# Job Discovery — Reference

## Target Roles

Three resume variants in Notion (Growth PM, Generalist, AI-PM). Search all three.
Cast wide — variant matching happens in the pipeline, not in discovery.

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

## Platforms

### General / Local Platforms

LinkedIn Jobs, StepStone, Indeed, Wellfound, Berlin Startup Jobs, InfoJobs,
Tecnoempleo, Arbeitnow, startup.jobs, Google Jobs

### Remote-Only Job Boards (100% verified remote)

We Work Remotely, Remote OK, Himalayas.app, Remotive, RemoteOrNothing,
RemoteRocketship, weloveproduct.co, RemotePMJobs.com, ProductJobsAnywhere.com,
Remote-Only.dev, Working Nomads, Arc.dev

## Query Patterns

Rotate through these patterns across 10+ rounds. Never repeat the same query.

### Growth PM — Germany

```
"Senior Growth Product Manager" Germany site:linkedin.com/jobs
"Product Manager Growth" Germany -Berlin site:linkedin.com/jobs
"Senior Growth PM" Deutschland site:stepstone.de
"Growth Product Manager" Germany startup site:linkedin.com/jobs
```

### Growth PM — Spain

```
"Senior Growth Product Manager" Spain site:linkedin.com/jobs
"Product Manager Growth" España site:infojobs.net
"Growth Product Manager" Spain remote site:linkedin.com/jobs
```

### AI PM — Germany

```
"Senior AI Product Manager" Germany site:linkedin.com/jobs
"AI Product Manager" Deutschland site:stepstone.de
"Product Manager AI ML" Germany startup site:linkedin.com/jobs
```

### AI PM — Spain

```
"Senior AI Product Manager" Spain site:linkedin.com/jobs
"Product Manager AI" España site:infojobs.net
```

### Generalist PM — Germany

```
"Senior Product Manager" Germany startup site:linkedin.com/jobs
"Senior Produktmanager" Deutschland site:stepstone.de
"Senior Product Manager" Germany remote site:linkedin.com/jobs
```

### Generalist PM — Spain

```
"Senior Product Manager" Spain site:linkedin.com/jobs
"Senior Product Manager" España remote site:infojobs.net
```

### Startup-Focused (cast wider net)

```
site:wellfound.com "Product Manager" Germany
site:berlinstartupjobs.com "Senior Product"
"Product Manager" Germany startup site:arbeitnow.com
```

### Remote-Only Boards (prioritize for remote-first roles)

```
site:weworkremotely.com "Product Manager" Europe
site:remoteok.com "Senior Product Manager" remote
site:himalayas.app "Product Manager" Europe timezone
site:remotive.com "Senior Product Manager" remote
site:remoterocketship.com "Senior Product Manager" Europe
site:weloveproduct.co "Senior Product Manager" remote
site:remoteornothing.com "Product Manager" remote
site:remotepmjobs.com "Senior Product Manager"
site:productjobsanywhere.com "Product Manager" EMEA
site:arc.dev "Product Manager" remote
```

### German Language (catch companies that post only in German)

```
"Senior Produktmanager" Wachstum Deutschland
"Produktmanager" Berlin Startup site:stepstone.de
```

### Spanish Language

```
"Senior Product Manager" España startup site:tecnoempleo.com
"Product Manager" Barcelona startup site:linkedin.com/jobs
```

## Company URL Lookup (Best-Effort)

After finding a job on a board, try to locate the company's own career page listing.
The user prefers applying directly on company sites, not through job boards.

**Strategy:**

1. Search: `"[Company Name]" careers "[Job Title]"` or `site:[companydomain]/careers "[keywords]"`
2. Check the company's careers page for the exact job title
3. If found, store the direct link in the `companyUrl` field
4. If not found within 1-2 searches, leave `companyUrl` empty — do not spend excessive time
5. Never block discovery on this step. The board link (`url`) is always the fallback

**Fallback behavior:**

- If `companyUrl` is empty, the queue HTML shows the board link as the primary link
- The user can still Google the company career page manually

## Recency Filters

When searching, apply recency filters based on the mode:

| Mode | Filter                            |
| ---- | --------------------------------- |
| 24h  | Past 24 hours, past day, today    |
| 7d   | Past week, past 7 days, last week |

Most job boards support these filters via URL parameters or search UI. For boards
that don't, filter manually by comparing the posting date against the current date.
