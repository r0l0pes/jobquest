# JobQuest — Implementation Plan

**INTERNAL — do not commit to git, do not share publicly.**

---

## Development Approach: Spec-Driven Development

- **Owner:** Rodrigo Lopes (product decisions)
- **Architect:** Claude (reviews all output before it ships)
- **Developer:** DeepSeek (builds from spec, does not make product decisions)

DeepSeek follows the spec. Ambiguities are flagged to Claude before assuming. Nothing ships without Claude's review. Phases completed in order — no skipping ahead.

---

## Hard Constraints for DeepSeek

Read these before writing any code.

1. **Never start a pipeline run without first deducting a credit atomically.** Credit deduction and run creation must be a single DB transaction. If the deduction fails, the run does not start.
2. **Always refund credits on failed runs.** Any step failure, Modal timeout, or pipeline error triggers a credit refund.
3. **Never modify local pipeline behavior.** `--mode=saas` is additive. Local CLI (`apply.py`) works exactly as before.
4. **RLS before anything else.** Implement and verify RLS policies before building any user-facing feature. Test with a second account.
5. **No service role key in the browser.** Ever.
6. **PDF URLs are always signed and time-limited.** Never generate a public storage URL.
7. **LLM API keys only in Modal secrets and Next.js server env.** Never in DB, never in client code.
8. **Stripe webhook signature verification.** All Stripe webhook handlers must verify the signature before processing.
9. **Never show error details to users.** Log errors server-side. Show generic messages in browser.
10. **Test RLS with a second test account before shipping Phase A.** Log in as User B and verify you cannot access User A's runs, resumes, or PDFs.

---

## Phase A — Foundation

Must be complete before any user can run the pipeline.

**Step 1 — Supabase setup**
- Create project
- Run full schema from `BACKEND_STRUCTURE.md`
- Enable RLS on all tables, add all policies
- Create private storage bucket for PDFs

**Step 2 — Next.js scaffolding**
- Next.js 14+ App Router
- Supabase Auth: email signup, login, session, email verification
- Middleware: protect /dashboard routes

**Step 3 — User profile (Before)**
- Master resume page: paste/edit text, save to `resumes` table
- Case studies page: add/edit/delete named entries
- Metrics bank page: add/edit/delete entries
- Skills and tools bank page: add/edit/delete with category + proficiency
- Q&A templates page: add/edit/delete with tags
- Profile completeness indicator across all five sections
- Onboarding flow: shown once after signup, master resume required before first run

**Step 4 — Modal pipeline function**
- Wrap `apply.py` + `modules/pipeline.py` as Modal function
- Function receives: `run_id`, `supabase_service_key`, `user_profile` dict (full profile)
- Writes granular `current_step` updates to Supabase at each stage
- Writes `brief_preview` after step 3a (tailoring plan summary)
- Writes `diff_content` on completion (before/after bullets as JSON)
- On failure: writes `status='failed'`, refunds credit
- PDF uploaded to Supabase Storage on completion

**Step 5 — Job submission**
- Dashboard form: job URL + optional questions
- Server-side: credits check → atomic deduction → create run row → trigger Modal
- Redirect to progress screen immediately

**Step 6 — Progress screen**
- Supabase real-time subscription on `runs` filtered by `run_id`
- Show estimated time at top: "Estimated time: 2-3 minutes"
- Step list with done/active/pending states
- Active step renders multi-line `current_step`: first line = label, subsequent lines = decisions
- Brief preview card appears mid-run after step 3a completes

**Step 7 — Results page**
- Signed PDF URL (1-hour expiry, server-side only)
- Match % display (never "ATS score")
- Before/after diff with inline editing (save triggers PDF regeneration, no credit charged)
- Q&A answers with copy buttons
- PDF retention notice (24h or 30 days depending on tier)
- Thumbs-down / report issue button

**Step 8 — Application tracker**
- List view of all past runs
- Columns: job title, company, date, match %, application status
- Application status editable inline (applied / screening / interview / offer / rejected)
- Link to results page per run

**Step 9 — Email (Resend)**
- Signup confirmation (Supabase Auth handles the link, Resend sends branded email)
- Run complete notification with PDF attached

---

## Phase B — Monetization

**Step 10 — Stripe credit packs**
- Pricing page: Starter €2.99, Standard €5.99, Value €9.99
- Stripe Checkout for one-time purchases
- Webhook handler: verify signature → add credits → log transaction

**Step 11 — Stripe subscription**
- Monthly plan: €4.99/month, 20 credits
- Stripe Checkout for subscriptions
- Webhook handler: `invoice.paid` → add monthly credits, `customer.subscription.deleted` → update tier

**Step 12 — Auto-recharge**
- User sets threshold and pack
- Supabase function triggered when `credits < threshold`
- Stripe charges saved PaymentMethod
- Email notification on every auto-charge

**Step 13 — Stripe Tax**
- Enable before first payment
- EU digital services VAT compliance

---

## Phase C — Protection

**Step 14 — Run counter alerts**
- Supabase cron job (daily): count runs in current month
- Email Rodrigo at 100/200/300/400 run thresholds via Resend

**Step 15 — Kill switch**
- Check `settings.signups_paused` on signup page
- If true: show waitlist form instead of signup

**Step 16 — Rate limiting**
- Max 5 concurrent runs per user
- Max 10 runs/hour per user

**Step 17 — Disposable email blocklist**
- Maintain blocklist table in Supabase
- Check on signup: mailinator, temp-mail, guerrillamail, throwaway, yopmail, sharklasers, etc.

**Step 18 — PDF auto-delete**
- Supabase cron job (daily): find rows where `pdf_expires_at < now()`
- Delete Storage files, set `pdf_path = null`

---

## Phase D — Retention

**Step 19 — Delete my account (GDPR)**
- Wipes: profiles, resumes, case_studies, metrics_bank, skills_bank, qa_templates, runs, Storage files
- Anonymises Stripe Customer (does not delete — needed for audit)

**Step 20 — Privacy Policy page**
- Static page. Use Termly for v1.
- Lists sub-processors: Supabase, Modal, Stripe, Resend, DeepSeek, Gemini

---

## Phase E — Growth (after validation)

**Step 21 — Google OAuth**
**Step 22 — Multilingual output** (job language detection, output in same language)
**Step 23 — Resume variant management** (Tech-First, Exp-First, AI-PM)
**Step 24 — Referral program** ("Give 2, get 2")

---

## Pre-Launch Checklist

| Item | Why it matters | When |
|---|---|---|
| Domain name (~€15/year) | Only unavoidable upfront cost | Before launch |
| Privacy Policy | EU law, required before storing any user data | Before launch |
| Terms of Service | Required before taking payment | Before launch |
| "Delete my account" | GDPR requirement | Phase D |
| Resend email service | Users need run-complete notification | Phase A |
| Stripe Tax enabled | EU VAT compliance | Before first payment |
| Modal spending cap ($25) | Prevents runaway costs | Day one |
| LLM API spend limits | Prevents key compromise from billing you | Day one |
| Support email | Users with failed runs will contact you | Before launch |
| Pricing page with honest copy | #1 complaint about competitors is hidden billing | Phase B |
| RLS verified with second test account | Security — non-negotiable | End of Phase A |

---

## Session Handoff Protocol

At the start of every build session with DeepSeek:
1. Paste full `SAAS_SPEC.md` as context (source of truth)
2. Reference the relevant spec file for the current phase
3. State exactly which step you are on
4. Do not proceed to the next step until the current one is confirmed working

At the start of every review session with Claude:
1. Paste DeepSeek's output
2. Claude checks against spec, flags security issues, flags deviations
3. Nothing ships until Claude approves
