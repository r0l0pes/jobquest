# Mode: discover — Job Discovery

When the user asks to discover jobs, search across multiple sources and add
results to `data/job_queue.md` for review.

## Target Roles

Cast wide within the Growth PM lane. Search each cluster separately.

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

### Generalist fallback (when Growth roles are thin)
Senior Product Manager, Senior PM – Platform / Core Product

## Target Locations
Germany (Berlin-first), Spain (Madrid / Barcelona / remote), Remote EU

## Execution

Run these searches. Add each result to `data/job_queue.md` as a checklist item
with URL, company, title, and source.

### Layer 1 — Web Search (broad discovery)

For each target role cluster, run a web_search query:

```
site:linkedin.com/jobs "Senior Growth Product Manager" Berlin 2026
site:stepstone.de "Senior Product Manager Growth"
site:berlinstartupjobs.com "product manager"
site:wellfound.com "growth product manager" berlin
```

### Layer 2 — Known ATS APIs (targeted)

For companies in `portals.yml` with `api:` config, use web_fetch to hit their
ATS endpoint. Use the same patterns as `modules/scrapers/job_postings.py`:
- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{company}/jobs`
- Lever: `https://api.lever.co/v0/postings/{company}?mode=json`
- Ashby: POST to GraphQL endpoint

### Layer 3 — Career Pages (direct)

For companies with `careers_url` in `portals.yml`, use Playwright to navigate
and extract job listings.

## Output Format

Append to `data/job_queue.md`:

```markdown
## [YYYY-MM-DD] — Discovered [N] jobs

- [ ] [URL] | [Company] | [Title] | [Source]
```

## Anti-Duplication

Before adding a job, check:
1. `data/job_queue.md` — already queued?
2. `data/applications.json` — already applied?
3. `output/*/pipeline_context.json` — already processed?

If a job has been seen before, skip it.

## Post-Discovery

After adding jobs to the queue, tell the user:
- How many new jobs found
- Top 3 by apparent fit (company name matches Berlin/Spain, role contains "Growth")
- Suggest running `python apply.py <URL>` on the most promising one
