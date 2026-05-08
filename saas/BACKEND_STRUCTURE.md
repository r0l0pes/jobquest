# JobQuest — Backend Structure

**INTERNAL — do not commit to git, do not share publicly.**

---

## Architecture Overview

```
Next.js (Vercel)
  ├── /app                    ← App Router pages and layouts
  ├── /app/api                ← Server-side API routes (service role key lives here)
  └── /components             ← React components

Supabase
  ├── Auth                    ← Email/password signup, session management
  ├── Postgres                ← All application data (see schema below)
  ├── Storage                 ← PDF files (private bucket, signed URLs)
  └── Real-time               ← Progress screen subscriptions

Modal (Python)
  └── pipeline_function.py   ← Wraps apply.py + modules/pipeline.py
                                Writes status updates to Supabase
                                Uploads PDF to Supabase Storage
```

---

## Database Schema

```sql
-- Extends Supabase Auth users
CREATE TABLE profiles (
  id uuid PRIMARY KEY REFERENCES auth.users ON DELETE CASCADE,
  email text,
  credits integer DEFAULT 2,
  subscription_tier text,              -- null | 'monthly'
  subscription_end_at timestamptz,
  auto_recharge_enabled boolean DEFAULT false,
  auto_recharge_threshold integer DEFAULT 2,
  auto_recharge_pack text DEFAULT 'starter',
  stripe_customer_id text,
  created_at timestamptz DEFAULT now()
);

-- Master resume (one per user in v1)
CREATE TABLE resumes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE,
  content text NOT NULL,
  updated_at timestamptz DEFAULT now()
);

-- Case studies
CREATE TABLE case_studies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE,
  title text NOT NULL,
  content text NOT NULL,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Metrics bank
CREATE TABLE metrics_bank (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE,
  metric text NOT NULL,
  context text,
  created_at timestamptz DEFAULT now()
);

-- Skills and tools bank
CREATE TABLE skills_bank (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE,
  name text NOT NULL,
  category text,         -- 'skill' | 'tool' | 'language' | 'methodology'
  proficiency text,      -- 'expert' | 'proficient' | 'familiar'
  created_at timestamptz DEFAULT now()
);

-- Q&A templates
CREATE TABLE qa_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE,
  question text NOT NULL,
  answer text NOT NULL,
  tags text[],
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Pipeline runs
CREATE TABLE runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE,
  job_url text NOT NULL,
  job_url_hash text,                   -- md5(user_id || job_url) for duplicate detection
  job_title text,
  company text,
  status text DEFAULT 'queued',        -- queued | running | complete | failed
  current_step text,                   -- live step name + decisions for progress screen
  brief_preview text,                  -- short plain-text summary of tailoring brief (shown mid-run)
  credits_charged integer DEFAULT 0,
  ats_score integer,
  ats_verdict text,
  pdf_path text,                       -- Supabase Storage path
  qa_content text,                     -- JSON array of {question, answer}
  diff_content text,                   -- JSON array of {id, before, after} for before/after display
  error_message text,
  application_status text DEFAULT 'applied', -- applied | screening | interview | offer | rejected
  created_at timestamptz DEFAULT now(),
  completed_at timestamptz,
  pdf_expires_at timestamptz,          -- free: now()+24h, paid: now()+30d
  pdf_tier text                        -- 'free' | 'paid'
);

-- Stripe transactions (audit log)
CREATE TABLE transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id) ON DELETE SET NULL,
  stripe_payment_intent_id text UNIQUE,
  pack text,                           -- 'starter' | 'standard' | 'value' | 'subscription'
  credits_purchased integer,
  amount_cents integer,
  created_at timestamptz DEFAULT now()
);

-- Global settings
CREATE TABLE settings (
  key text PRIMARY KEY,
  value text
);
INSERT INTO settings VALUES ('signups_paused', 'false');
INSERT INTO settings VALUES ('free_credits_per_signup', '2');

-- RLS on everything
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE resumes ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_studies ENABLE ROW LEVEL SECURITY;
ALTER TABLE metrics_bank ENABLE ROW LEVEL SECURITY;
ALTER TABLE skills_bank ENABLE ROW LEVEL SECURITY;
ALTER TABLE qa_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own profile" ON profiles FOR ALL USING (auth.uid() = id);
CREATE POLICY "own resumes" ON resumes FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own case studies" ON case_studies FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own metrics" ON metrics_bank FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own skills" ON skills_bank FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own qa templates" ON qa_templates FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own runs" ON runs FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own transactions" ON transactions FOR ALL USING (auth.uid() = user_id);
```

---

## API Routes (Next.js server-side)

All routes use the Supabase service role key. Never exposed to the browser.

| Route | Method | What it does |
|---|---|---|
| `/api/runs` | POST | Credit check → deduct → create run row → trigger Modal |
| `/api/runs/[id]/pdf` | GET | Generate signed URL for PDF download |
| `/api/runs/[id]/edit` | POST | Accept bullet edit → trigger Modal re-render |
| `/api/webhooks/stripe` | POST | Verify signature → credit user on payment |
| `/api/profile` | GET/PUT | Read/write profile sections |

---

## Financial Protection

**Credits deducted BEFORE the pipeline starts. Not after. Not on completion. Before.**

```
User clicks Run
  → Check credits > 0 (if not, block at API level)
  → Deduct 1 credit atomically (single DB transaction)
  → Create run row with status='queued'
  → Trigger Modal function
  → If run succeeds: done
  → If run fails: refund 1 credit + set status='failed' + log error
```

Credit deduction and run creation must be a single atomic operation. If the deduction fails, the run does not start.

### Spending caps (set on day one)

- **Modal:** hard monthly limit $25, email alert at $15
- **DeepSeek:** $10/month limit (~666 runs)
- **Gemini:** free tier only (250 req/day)

### Kill switch

If total runs in a calendar month exceed 400 AND Stripe revenue that month is less than €20, set `signups_paused = true` in the settings table. Signup page checks this flag.

### Run counter alerts (Supabase cron, daily)

| Total runs | Action |
|---|---|
| 100 | Email Rodrigo: check Modal balance |
| 200 | Email Rodrigo: review revenue vs run count |
| 300 | Email Rodrigo: decide on free credits or Modal upgrade |
| 400 | Email Rodrigo: Modal free tier exhausted |

---

## Security Rules (non-negotiable before launch)

1. **RLS on all tables.** Verify with a second test account before shipping.
2. **Service role key never in the browser.** Only in Modal secrets and Next.js server API routes.
3. **PDF downloads via signed URLs only.** 1-hour expiry. No public storage URLs ever.
4. **LLM API keys in Modal secrets only.** Never in DB, never in client code.
5. **Stripe webhook signature verification.** Every handler verifies the signature before processing.
6. **No error details to users.** Log server-side. Show generic messages in browser.
7. **HTTPS everywhere.** Vercel enforces by default. Supabase uses SSL. Modal uses TLS.

---

## GDPR Compliance

- Privacy Policy required before storing any user data
- "Delete my account" feature: wipes profiles, resumes, case_studies, metrics_bank, skills_bank, qa_templates, runs, Storage files, and anonymises Stripe Customer
- Do not store raw job description text permanently. Store only job_title, company, job_url. Full JD lives in Modal during the run only.
- PDF retention: free tier 24 hours, paid 30 days. Enforced by Supabase cron on `pdf_expires_at`.

---

## Modal Pipeline Function

The Modal function wraps the existing Python pipeline in SaaS mode.

```python
# Receives
run_id: str
supabase_service_key: str
user_profile: dict  # {
#   name, email, phone, linkedin, location,
#   master_resume_text,
#   case_studies: [{title, content}],
#   metrics_bank: [{metric, context}],
#   skills_bank: [{name, category, proficiency}],
#   qa_templates: [{question, answer, tags}],
# }

# Writes to Supabase at each step
runs.current_step = "step label\ndetail line 1\ndetail line 2"

# Writes brief preview after step 3a
runs.brief_preview = "short plain-text summary of tailoring plan"

# On completion
runs.status = 'complete'
runs.ats_score = int
runs.pdf_path = 'resumes/{user_id}/{run_id}.pdf'
runs.diff_content = '[{"id": "...", "before": "...", "after": "..."}]'
runs.qa_content = '[{"question": "...", "answer": "..."}]'
runs.completed_at = now()
runs.pdf_expires_at = now() + (24h if free else 30d)

# On failure
runs.status = 'failed'
runs.error_message = str  # internal detail, never shown to user
# + refund 1 credit to profiles.credits
```

---

## LangGraph Pipeline (SaaS mode)

LangGraph replaces the `build_steps()` / `execute_step()` orchestration in `pipeline.py` for the Modal version only. Local CLI is unchanged.

```
[scrape_job] → [read_resume] → [analyse_jd_brief] → [tailor_latex] → [compliance_check]
                                                                             │
                                                                   [write_tex_file]
                                                                             │
                                                                    [ats_check]
                                                                        / \
                                                                 score≥60  score<60
                                                                   /           \
                                                          [compile_pdf]   [apply_ats_edits] → [ats_check] (loop, max 2x)
                                                               │
                                                          [generate_qa]
```

Each node writes its output to Supabase before returning. Enables resume-from-failed-step without re-running steps 1-N.
