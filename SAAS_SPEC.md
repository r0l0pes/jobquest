# JobQuest SaaS — Product Specification v1

**Product:** JobQuest
**Owner:** Rodrigo Lopes
**Architect:** Claude (oversees spec and reviews output)
**Developer:** DeepSeek (builds from this spec)
**Date:** February 2026
**Status:** Pre-build. Pipeline is working. This document defines what wraps around it.

---

## The One-Line Pitch

Paste a job URL. Get a tailored PDF resume, ATS score, and application answers — in under 5 minutes.

---

## Phase 1 — Brief & Audit

### What the pipeline already does (do not break this)

The existing Python pipeline (`apply.py` + `modules/pipeline.py`) works end-to-end:

1. Scrapes the job posting via structured ATS APIs (Greenhouse, Lever, Ashby, Workable, Personio, Screenloop) with HTML/Playwright/Firecrawl fallback
2. Reads master resume from storage
3. Two-stage LLM tailoring: analysis brief (free-tier LLM) → LaTeX generation (writing LLM) → compliance check
4. ATS keyword check with score and suggested edits
5. Applies edits, compiles PDF via pdflatex
6. Generates Q&A answers to application form questions
7. Tracks the application

This pipeline must keep running locally for Rodrigo during development. The SaaS wraps around it — it does not change it. Changes to the pipeline are a separate concern.

### What needs to be built

| Component | Status | Notes |
|---|---|---|
| Auth (signup/login) | Missing | Required for multi-user |
| Master resume storage | Notion (replace) | Move to DB, user-editable in app |
| Web frontend | Gradio (replace) | Production UI, non-technical users |
| Async job execution | CLI only (wrap) | Pipeline runs as background job |
| Progress feedback | None (replace) | Users need live step-by-step updates |
| PDF storage | Local files (replace) | Store in cloud, serve via URL |
| Application tracker | Notion (replace) | In-app dashboard |
| Payments | None (add) | Credits + subscription |
| Application Q&A display | .md file (replace) | Inline in results page |

### Core risk

The pipeline takes 2-5 minutes. Non-technical users abandon anything that looks frozen. The progress screen is the most important UX component in the product.

---

## Phase 2 — Competitor Analysis

### Market landscape (researched February 2026)

| Tool | What it does | Price | Gap |
|---|---|---|---|
| Rezi | ATS scoring + AI bullet points | $0-$30/mo | No auto-tailoring from URL, no Q&A |
| Teal | Resume tailoring + job tracker | $0-$29/mo | Basic ATS, no Q&A, no PDF re-render |
| Jobscan | Deep ATS analysis (score only) | $0-$50/mo | Analysis only, no rewriting, no Q&A |
| Kickresume | Design + cover letter | $0-$24/mo | Design-first, weak ATS, no tracking |
| Huntr | Tracker + tailoring | Freemium | No ATS score, no Q&A, no PDF |
| Simplify | Auto-fill application forms | Freemium | No resume tailoring |
| LazyApply | Auto-apply at scale | Paid | 25-40% failure rate, generic answers |

### Critical finding

**No tool in the market does all of this in one pipeline:**
- Automatic job scraping from URL (no copy-paste)
- Two-stage tailoring with transparent strategy brief
- ATS keyword check with automatic edits applied to the PDF
- Q&A answer generation using the tailoring context
- Application tracker updated automatically

Each competitor does 1-2 of these. JobQuest does all 5.

### User complaints about existing tools (from Reddit / reviews)

- Resume.io: hidden billing, auto-renewal traps, hard to cancel
- Rezi: generic AI output that needs manual cleanup, slow PDF download
- LazyApply: wrong answers, copy-paste from resume without context
- Teal: "Takes 25+ minutes per application" (defeats the point)
- All: ATS scoring without actually fixing the resume

### Competitive positioning

JobQuest is not competing on design templates or visual polish. It competes on **completeness and speed**. The pitch is:

> One URL. Two minutes. A tailored PDF, an ATS score, and answers to every application question — ready to submit.

### European market gap

No AI resume tool has focused on Europe. Opportunity:
- German/Spanish/French job boards (StepStone, InfoJobs, APEC) unsupported by competitors
- European resume norms differ (no photo requirements, GDPR-compliant, date formats)
- Multilingual pipeline is a v2 feature but plan for it in the data model

---

## Phase 3 — User Flows & Edge Cases

### Primary happy path

```
1. User lands on homepage
2. Signs up (email + password or Google OAuth)
3. Onboarding: pastes or uploads their master resume (one-time, required before first run)
4. Dashboard: pastes job URL
   - Optional: pastes application questions
   - Optional: selects resume variant (if configured)
5. Clicks "Run"
6. Progress screen: live step updates
   - Scraping job posting...
   - Reading your resume...
   - Tailoring resume (analysis)...
   - Tailoring resume (writing)...
   - Running ATS check...
   - Applying keyword edits...
   - Compiling PDF...
   - Generating answers...
   - Done
7. Results page:
   - Download PDF button (primary CTA)
   - ATS score + keyword breakdown
   - Q&A answers (copy-button per answer)
   - "Save to tracker" (auto-saved, but user can edit)
8. Application appears in tracker dashboard
```

### Edge cases — must handle in v1

| Scenario | Handling |
|---|---|
| Job URL requires login (LinkedIn, internal portals) | Show error: "This URL requires login. Paste the job description text instead." Provide text fallback input |
| User runs pipeline before completing resume | Block at submission: "Complete your profile first" with link to resume editor |
| Pipeline fails mid-run | Show exactly which step failed. Offer retry. Do NOT charge credits for failed runs |
| User submits same URL twice | Detect duplicate (hash job URL). Show "You already applied here on [date]. Run again?" |
| PDF quality is poor | Thumbs down button on results page. Logs run ID + user feedback for debugging |
| Very long job description (>5000 words) | Truncate at 5000 words, show notice: "Long job description — using first 5,000 words" |
| Non-English job posting | Detect language (v1: warn user "Non-English JD detected — output may be in English"). V2: full multilingual |
| Free credits exhausted mid-session | Block at the submission stage before run starts, never mid-run |
| pdflatex compilation error | Show: "PDF compilation failed. Your LaTeX file is saved — contact support." Do not charge |
| All LLM providers rate-limited | Show: "LLM providers are busy. Your job is queued and will run in a few minutes." |

### Edge cases — defer to v2

- Resume variant switching (Growth PM vs Generalist) — store variants but only expose in v2
- Bulk submission (multiple URLs at once)
- Re-run with updated resume
- Browser extension

---

## Phase 4 — Recommendations & Build Order

### Pricing model

**Unit economics:**
- LLM cost per run: ~€0.015 (DeepSeek steps 3+8, Gemini free for 3a/3c/5)
- Modal compute per run: ~€0.007 (5 min, 2 CPU cores)
- Storage per run (PDF ~500KB): ~€0.001
- **Total cost per run: ~€0.023**

**Price points:**
- Pay-as-you-go: **€0.39 per application**
- Starter pack: **€4.99 for 15 credits** (€0.33/run)
- Standard pack: **€9.99 for 40 credits** (€0.25/run)
- Monthly subscription: **€7.99/month = 35 credits** (€0.23/run, unused credits roll over)

Margin at €0.39: 94%. Even at the cheapest tier (€0.23), margin is 90%.

**Signup offer:** 3 free credits on signup, no card required. Users get a real result before paying.

**Why not a higher free tier:** job seekers are unemployed (as Rodrigo noted), so the pricing has to be accessible. €0.39 per application is less than a coffee. But unlimited free would attract abuse. 3 credits is enough to validate the product.

### Infrastructure — cost-optimized stack

Everything below has a generous free tier. Initial cost: €0/month until revenue starts.

| Component | Tool | Free Tier | Paid |
|---|---|---|---|
| Auth + DB + Storage | Supabase | 500MB DB, 1GB files, 50k MAUs | $25/mo |
| Async pipeline execution | Modal | $30 compute credits/mo (~400 runs) | ~$0.07/run after |
| Frontend hosting | Vercel | Unlimited static, 100GB bandwidth | $0 for early stage |
| Payments | Stripe | No monthly fee | 2.9% + €0.30/transaction |
| Frontend framework | Next.js | Open source | Free |

**Notion is dropped.** Master resume and application tracking live in Supabase. Users manage everything inside the app.

### What NOT to use (from user's list)

- **Appwrite** — self-hosted = you manage the server. More headaches, not fewer.
- **Convex** — TypeScript-first reactive backend. The pipeline is Python. Language boundary adds complexity.
- **Firebase** — NoSQL is the wrong shape for structured resume/application data. Firebase Auth is good but Supabase gives you Auth + DB + Storage in one.
- **Neon** — just a database. You'd need separate auth (Clerk: $25+/mo) and storage (S3). More services, more integration work, more cost.

### Build order (phases)

**Phase A — Foundation (before any user can run the pipeline)**
1. Supabase project setup: schema, auth config, storage buckets
2. Next.js project scaffolding with Supabase auth (sign up, login, session)
3. Resume onboarding page (paste text + save to Supabase)
4. Modal deployment of the existing pipeline (wrap `apply.py` as a Modal function)
5. Job submission form (URL input → triggers Modal job → returns job ID)
6. Progress screen (poll job status, show step-by-step updates)
7. Results page (PDF download link, ATS score, Q&A answers)

**Phase B — Monetization**
8. Stripe integration (credit packs + subscription)
9. Credit check before pipeline run
10. Credit deduction on successful completion
11. Pricing page

**Phase C — Retention**
12. Application tracker dashboard (list of past runs with PDF links)
13. Run history and detail pages
14. Email: signup confirmation, run complete notification

**Phase D — Growth (post-validation)**
15. Google OAuth
16. Multilingual support
17. Resume variant management
18. Referral system ("Give 3, get 3")

---

## Data Model

### Supabase tables

```sql
-- Users (managed by Supabase Auth, extended here)
profiles (
  id uuid PRIMARY KEY REFERENCES auth.users,
  email text,
  credits integer DEFAULT 3,          -- starts with 3 free credits
  subscription_tier text,             -- null | 'monthly'
  subscription_end_at timestamptz,
  created_at timestamptz DEFAULT now()
)

-- Master resume (one per user for now; variants in v2)
resumes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id),
  content text NOT NULL,              -- full resume text (markdown/plain)
  updated_at timestamptz DEFAULT now()
)

-- Pipeline runs
runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id),
  job_url text NOT NULL,
  job_title text,
  company text,
  status text DEFAULT 'queued',       -- queued | running | complete | failed
  current_step text,                  -- e.g. "Tailoring resume..."
  credits_charged integer DEFAULT 0,
  ats_score integer,
  ats_verdict text,
  pdf_path text,                      -- Supabase storage path
  qa_content text,                    -- markdown string
  error_message text,
  created_at timestamptz DEFAULT now(),
  completed_at timestamptz
)

-- Stripe transactions (lightweight log)
transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id),
  stripe_payment_intent_id text,
  credits_purchased integer,
  amount_cents integer,
  created_at timestamptz DEFAULT now()
)
```

### Supabase storage buckets

```
resumes/          -- PDF outputs, path: {user_id}/{run_id}.pdf
```

---

## Phase 5 — UI Prototypes

### Design system

- **Framework:** Next.js 14+ (App Router)
- **Styling:** Tailwind CSS
- **Components:** shadcn/ui (free, copy-paste, no lock-in)
- **Icons:** Lucide React
- **Fonts:** Inter (system font stack, no external dependency)
- **Color scheme:** Dark background, accent green (#22c55e) for success states, amber for warnings

---

### Screen 1: Landing Page (Hero)

```jsx
// app/page.tsx
export default function LandingPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
        <span className="text-xl font-bold tracking-tight">JobQuest</span>
        <div className="flex gap-3">
          <a href="/login" className="text-sm text-gray-400 hover:text-white px-4 py-2">
            Log in
          </a>
          <a href="/signup" className="text-sm bg-green-500 hover:bg-green-400 text-black font-medium px-4 py-2 rounded-lg">
            Try free
          </a>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-3xl mx-auto px-6 pt-24 pb-16 text-center">
        <div className="inline-flex items-center gap-2 bg-gray-800 text-green-400 text-xs px-3 py-1 rounded-full mb-6">
          <span className="w-1.5 h-1.5 bg-green-400 rounded-full" />
          3 free applications — no card required
        </div>

        <h1 className="text-5xl font-bold leading-tight tracking-tight mb-6">
          Paste a job URL.<br />
          <span className="text-green-400">Get the application.</span>
        </h1>

        <p className="text-lg text-gray-400 mb-10 max-w-xl mx-auto">
          JobQuest tailors your resume, checks ATS keywords, and writes
          your application answers — in under 5 minutes. One URL in,
          everything out.
        </p>

        <a href="/signup"
          className="inline-block bg-green-500 hover:bg-green-400 text-black font-semibold text-lg px-8 py-4 rounded-xl transition-colors">
          Start for free
        </a>

        <p className="text-sm text-gray-500 mt-4">
          From €0.25 per application. No subscription required.
        </p>
      </section>

      {/* How it works */}
      <section className="max-w-4xl mx-auto px-6 pb-24">
        <h2 className="text-center text-sm text-gray-500 uppercase tracking-widest mb-10">
          How it works
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[
            { step: "1", title: "Paste the URL", desc: "Any job posting. We scrape it automatically." },
            { step: "2", title: "We tailor your resume", desc: "ATS keywords added, PDF compiled in seconds." },
            { step: "3", title: "See your ATS score", desc: "Know exactly which keywords you're missing." },
            { step: "4", title: "Get application answers", desc: "Every form question answered in your voice." },
          ].map((item) => (
            <div key={item.step} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <span className="text-green-400 text-sm font-mono font-bold mb-3 block">
                {item.step}
              </span>
              <h3 className="font-semibold mb-1">{item.title}</h3>
              <p className="text-sm text-gray-400">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}
```

---

### Screen 2: Dashboard (main app)

```jsx
// app/dashboard/page.tsx
"use client"
import { useState } from "react"

export default function Dashboard({ user, credits }) {
  const [jobUrl, setJobUrl] = useState("")
  const [questions, setQuestions] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    // POST to /api/runs → triggers Modal job → redirect to /runs/[id]
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Sidebar */}
      <div className="flex">
        <aside className="w-56 min-h-screen bg-gray-900 border-r border-gray-800 p-4 flex flex-col gap-1">
          <span className="text-lg font-bold px-2 py-3 mb-2">JobQuest</span>
          {[
            { label: "New application", href: "/dashboard", active: true },
            { label: "Past applications", href: "/dashboard/history" },
            { label: "My resume", href: "/dashboard/resume" },
            { label: "Credits", href: "/dashboard/credits" },
          ].map((item) => (
            <a key={item.label} href={item.href}
              className={`text-sm px-3 py-2 rounded-lg transition-colors ${
                item.active
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}>
              {item.label}
            </a>
          ))}
          <div className="mt-auto">
            <div className="bg-gray-800 rounded-lg p-3 text-sm">
              <div className="text-gray-400 mb-1">Credits remaining</div>
              <div className="text-2xl font-bold text-green-400">{credits}</div>
              <a href="/dashboard/credits"
                className="text-xs text-gray-400 hover:text-white mt-1 block">
                Buy more →
              </a>
            </div>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 p-8 max-w-2xl">
          <h1 className="text-2xl font-bold mb-1">New application</h1>
          <p className="text-gray-400 text-sm mb-8">
            Paste a job URL and we handle the rest. Takes 2-5 minutes.
          </p>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium mb-2">Job posting URL</label>
              <input
                type="url"
                value={jobUrl}
                onChange={(e) => setJobUrl(e.target.value)}
                placeholder="https://jobs.lever.co/company/job-id"
                className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm placeholder-gray-500 focus:outline-none focus:border-green-500 focus:ring-1 focus:ring-green-500"
                required
              />
              <p className="text-xs text-gray-500 mt-1">
                Supports Greenhouse, Lever, Ashby, Workable, Personio, and most other job boards.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                Application questions
                <span className="text-gray-500 font-normal ml-2">(optional)</span>
              </label>
              <textarea
                value={questions}
                onChange={(e) => setQuestions(e.target.value)}
                placeholder={"Why do you want to work here?\nTell us about a time you led a product launch."}
                rows={4}
                className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm placeholder-gray-500 focus:outline-none focus:border-green-500 focus:ring-1 focus:ring-green-500 resize-none"
              />
              <p className="text-xs text-gray-500 mt-1">
                One question per line. We generate written answers for each.
              </p>
            </div>

            <button
              type="submit"
              disabled={loading || !jobUrl || credits === 0}
              className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-700 disabled:text-gray-500 text-black font-semibold py-3 rounded-xl transition-colors flex items-center justify-center gap-2">
              {loading ? "Starting..." : "Run pipeline — 1 credit"}
            </button>

            {credits === 0 && (
              <p className="text-sm text-amber-400 text-center">
                You're out of credits.{" "}
                <a href="/dashboard/credits" className="underline">
                  Buy more →
                </a>
              </p>
            )}
          </form>
        </main>
      </div>
    </div>
  )
}
```

---

### Screen 3: Progress Screen

```jsx
// app/runs/[id]/progress.tsx
const STEPS = [
  "Scraping job posting",
  "Reading your resume",
  "Analysing job requirements",
  "Tailoring resume",
  "Checking brief compliance",
  "Running ATS check",
  "Applying keyword edits",
  "Compiling PDF",
  "Generating application answers",
  "Done",
]

export default function ProgressScreen({ run }) {
  const currentIndex = STEPS.indexOf(run.current_step)

  return (
    <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
      <div className="max-w-md w-full px-6">
        <div className="text-center mb-10">
          <div className="w-12 h-12 border-2 border-green-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <h1 className="text-xl font-semibold mb-1">Working on it</h1>
          <p className="text-gray-400 text-sm">
            {run.job_title
              ? `Tailoring for ${run.job_title} at ${run.company}`
              : "Processing your application..."}
          </p>
        </div>

        <div className="space-y-2">
          {STEPS.map((step, i) => {
            const done = i < currentIndex
            const active = i === currentIndex
            const pending = i > currentIndex

            return (
              <div key={step}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all ${
                  active ? "bg-gray-800 border border-gray-700" : ""
                }`}>
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs flex-shrink-0 ${
                  done ? "bg-green-500 text-black" :
                  active ? "border-2 border-green-500 animate-pulse" :
                  "border border-gray-700"
                }`}>
                  {done && "✓"}
                </span>
                <span className={`text-sm ${
                  done ? "text-gray-400 line-through" :
                  active ? "text-white font-medium" :
                  "text-gray-600"
                }`}>
                  {step}
                </span>
              </div>
            )
          })}
        </div>

        <p className="text-xs text-gray-600 text-center mt-8">
          This takes 2-5 minutes. You can close this tab — we'll email you when it's done.
        </p>
      </div>
    </div>
  )
}
```

---

### Screen 4: Results Page

```jsx
// app/runs/[id]/results.tsx
export default function ResultsPage({ run }) {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-3xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="w-2 h-2 bg-green-400 rounded-full" />
              <span className="text-sm text-green-400 font-medium">Complete</span>
            </div>
            <h1 className="text-2xl font-bold">{run.job_title}</h1>
            <p className="text-gray-400">{run.company}</p>
          </div>
          <div className="flex items-center gap-2">
            <button className="text-sm text-gray-400 hover:text-white px-3 py-1.5 rounded-lg border border-gray-700 flex items-center gap-1">
              👎 Report issue
            </button>
          </div>
        </div>

        {/* PDF Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold mb-1">Tailored resume</h2>
              <p className="text-sm text-gray-400">PDF, ready to upload</p>
            </div>
            <a href={run.pdf_url} download
              className="bg-green-500 hover:bg-green-400 text-black font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors">
              Download PDF
            </a>
          </div>
        </div>

        {/* ATS Score Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">ATS keyword coverage</h2>
            <span className={`text-2xl font-bold ${
              run.ats_score >= 70 ? "text-green-400" :
              run.ats_score >= 50 ? "text-amber-400" :
              "text-red-400"
            }`}>
              {run.ats_score}%
            </span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2">
            <div
              className={`h-2 rounded-full ${
                run.ats_score >= 70 ? "bg-green-500" :
                run.ats_score >= 50 ? "bg-amber-500" : "bg-red-500"
              }`}
              style={{ width: `${run.ats_score}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Target: 60-80%. Above 80% risks keyword stuffing.
          </p>
        </div>

        {/* Q&A Answers */}
        {run.qa_answers?.length > 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
            <h2 className="font-semibold mb-4">Application answers</h2>
            <div className="space-y-5">
              {run.qa_answers.map((qa, i) => (
                <div key={i} className="border-t border-gray-800 pt-4 first:border-0 first:pt-0">
                  <p className="text-sm text-gray-400 mb-2">{qa.question}</p>
                  <p className="text-sm leading-relaxed">{qa.answer}</p>
                  <button
                    onClick={() => navigator.clipboard.writeText(qa.answer)}
                    className="text-xs text-gray-500 hover:text-white mt-2 transition-colors">
                    Copy
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
```

---

### Screen 5: Application Tracker

```jsx
// app/dashboard/history/page.tsx
export default function ApplicationTracker({ runs }) {
  return (
    <div className="flex-1 p-8">
      <h1 className="text-2xl font-bold mb-1">Applications</h1>
      <p className="text-gray-400 text-sm mb-8">{runs.length} applications tracked</p>

      <div className="space-y-3">
        {runs.map((run) => (
          <a key={run.id} href={`/runs/${run.id}`}
            className="flex items-center justify-between bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-xl p-4 transition-colors group">
            <div>
              <div className="font-medium group-hover:text-green-400 transition-colors">
                {run.job_title || "Unknown role"}
              </div>
              <div className="text-sm text-gray-400">
                {run.company} · {new Date(run.created_at).toLocaleDateString("en-GB")}
              </div>
            </div>
            <div className="flex items-center gap-4">
              {run.ats_score && (
                <span className={`text-sm font-mono font-bold ${
                  run.ats_score >= 70 ? "text-green-400" :
                  run.ats_score >= 50 ? "text-amber-400" : "text-red-400"
                }`}>
                  {run.ats_score}%
                </span>
              )}
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                run.status === "complete" ? "bg-green-900 text-green-300" :
                run.status === "failed" ? "bg-red-900 text-red-300" :
                "bg-gray-800 text-gray-300"
              }`}>
                {run.status}
              </span>
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}
```

---

## Phase 6 — Full Report

### What we are building

JobQuest SaaS: a web application that wraps the existing Python pipeline, serves it to any job seeker, and charges per application. No Notion. No terminal. Just a URL field and a download button.

### The gap we fill

No existing tool does the full loop: scrape → tailor → ATS check → Q&A → track. Competitors stop at 1-2 steps. JobQuest is the only end-to-end pipeline.

### Stack decision

| Layer | Tool | Why |
|---|---|---|
| Frontend | Next.js on Vercel | Zero infrastructure, free tier covers early stage |
| Auth + DB + Storage | Supabase | One service covers all three, free tier, Python SDK |
| Pipeline execution | Modal | Serverless Python, no servers to manage, $30 free/month |
| Payments | Stripe | Industry standard, no monthly fee |

### Cost at zero revenue

- Supabase: free (under 500MB DB, 1GB storage, 50k MAUs)
- Modal: free ($30/month credits = ~400 pipeline runs)
- Vercel: free
- Stripe: 0% (no transactions)
- **Total monthly cost: €0 until ~400 runs/month**

### When costs start

- After ~400 runs/month: Modal credits run out → ~€0.007/run billed
- After revenue starts: upgrade Supabase to Pro ($25/month) for reliability
- This means the product is self-funding by design: you don't pay until you have users

### Pricing (final recommendation)

**Why no single-run purchase option:**
Stripe charges €0.30 + 2.9% per transaction. On a €0.39 charge you keep €0.08. That is not viable. Minimum transaction must be ~€3 to keep Stripe fees below 15%. All pricing is therefore credit packs or subscription — no single-run option.

**Credit packs (one-time purchase):**

| Pack | Price | Credits | Per-run | You keep after Stripe |
|---|---|---|---|---|
| Starter | €2.99 | 5 | €0.60 | €2.52 (84%) |
| Standard | €5.99 | 15 | €0.40 | €5.41 (90%) |
| Value | €9.99 | 30 | €0.33 | €9.40 (94%) |

**Subscription:**

| Plan | Price | Credits/month | Per-run | Rollover |
|---|---|---|---|---|
| Monthly | €4.99/mo | 20 | €0.25 | Yes, unused credits roll over (capped at 40) |

At €4.99/month after Stripe: you keep €4.54. Your cost for 20 runs at €0.023 = €0.46. **Net per subscriber: ~€4.08/month.**

**Signup bonus:** 2 free credits, no card required. (Not 3 — see abuse protection below.)

**Auto-recharge (Anthropic model):**
Users can opt in to automatic top-up. When credits drop below a chosen threshold (e.g. 2), Stripe automatically charges the saved card for a chosen pack. User sets: threshold + pack size. This is opt-in, clearly labelled, with email notification on every charge. Prevents the friction of running out mid job-search. Implementation: Stripe Customer + saved PaymentMethod + scheduled charge triggered by a Supabase function when `credits < threshold`.

### What the personal pipeline (Rodrigo's local tool) does NOT change

The existing CLI (`apply.py`) keeps running exactly as-is using Notion, the local `.env`, and the local output directory. The SaaS version is a separate deployment of the same pipeline code with different config. No changes to the pipeline itself during SaaS development.

### Open questions for DeepSeek — ANSWERED

1. **Progress screen polling:** Use Supabase real-time (built-in WebSocket subscriptions, no extra cost). The frontend subscribes to `postgres_changes` on the `runs` table filtered by `run_id`. The pipeline writes `current_step` to Supabase at each stage transition. No polling loop needed. Implementation: `supabase.channel('run_' + runId).on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'runs', filter: 'id=eq.' + runId }, callback).subscribe()`.

2. **Modal job status:** The Modal function receives `run_id` and `supabase_service_key` as parameters. At the start of each pipeline step, it executes: `supabase.table('runs').update({'current_step': step_name, 'status': 'running'}).eq('id', run_id).execute()`. This is 2 lines added to the `execute_step` wrapper in `apply.py`. On completion: update `status = 'complete'`, `completed_at`, `ats_score`, `pdf_path`. On failure: update `status = 'failed'`, `error_message`.

3. **PDF delivery:** After `render_pdf.py` succeeds, the Modal function reads the compiled PDF bytes and uploads to Supabase Storage: `supabase.storage.from_('resumes').upload(f'{user_id}/{run_id}.pdf', pdf_bytes)`. Then writes the storage path to `runs.pdf_path`. The Next.js API serves a signed URL (1-hour expiry) generated on demand: `supabase.storage.from_('resumes').create_signed_url(path, 3600)`. Never a public URL.

4. **Multi-tenancy:** Add a `user_profile` dict parameter to the pipeline entry point (SaaS mode only). Contains: `name`, `email`, `phone`, `linkedin`, `location`, `master_resume_text`. These override the env-var equivalents. The pipeline's `config.py` values are the fallback (local mode). In SaaS mode, `master_resume_text` is passed directly into `ctx` in step 2, skipping the Notion read entirely.

5. **Notion removal for SaaS:** Add `ctx['mode']` flag (`'local'` or `'saas'`). Step 2 checks: if `saas`, read resume from `ctx['master_resume_text']` (passed in at invocation) — skip Notion call. Step 9 checks: if `saas`, skip entirely — tracking is handled by the `runs` table. The `--mode` flag defaults to `local` so zero changes to the existing CLI behavior.

### Constraints (hard rules for DeepSeek)

- Never modify the local pipeline behavior. The SaaS path is additive, not a replacement.
- Never charge credits for failed runs.
- Never store raw LLM API keys in the database. Each user brings their own API keys OR the operator (Rodrigo) provides them via server-side env vars. For v1, operator-provided keys only.
- Never show another user's resume, PDFs, or run history. Supabase Row Level Security (RLS) must be enabled on all tables.
- All Supabase queries from the frontend go through the Supabase JS client with the user's session token. Never expose the service role key to the browser.
- The PDF download URL must be a signed URL (time-limited), never a public URL.

---

---

## Financial Protection — Worst-Case Scenarios

**Rule zero:** You never spend money you haven't already received. Every cost below has a ceiling and a mitigation.

### Scenario 1: Free tier abuse (multiple accounts)
- **Risk:** Someone creates 50 accounts, gets 100 free credits, costs you 100 × €0.023 = €2.30.
- **Why it's not serious:** €2.30 is the total exposure per abuser. Even 100 abusers = €230 in LLM/compute costs, spread over months.
- **Mitigation:** Email verification required before free credits are granted. One verified email = one account. Disposable email domains (mailinator, temp-mail, etc.) blocked at signup. If abuse is detected, revoke credits and ban the email domain.

### Scenario 2: A single run costs much more than expected
- **Risk:** 15,000-word job description, 10 retries due to LLM timeouts, costs €0.50 instead of €0.02.
- **Mitigation (already in pipeline):** Job descriptions truncated at 5,000 words. LLM fallback chain tries cheaper providers first. Modal function has a hard timeout (set to 10 minutes max). If the run times out, it fails cleanly — user gets their credit back, you pay ~€0.08 in compute and nothing more.
- **Ceiling per run:** Hard cap Modal at 10 minutes = €0.08 maximum compute regardless of what happens.

### Scenario 3: Modal free credits run out
- **Risk:** More than ~400 runs in a month before you have revenue.
- **Reality check:** 400 runs at 2 free credits each = 200 users. If 200 users ran their 2 free trials, you have a product worth paying for. Upgrade Modal at that point — revenue should already cover it.
- **Mitigation:** Set a Modal spend alert at $25/month. If it fires before revenue, pause the signup free credits temporarily (change to 0 free credits, require card).

### Scenario 4: Stripe dispute / chargeback
- **Risk:** User buys €9.99 pack, uses all 30 credits, disputes the charge. You lose €9.99 + ~€15 chargeback fee = €24.99 total loss.
- **Mitigation:** Credits are consumed immediately on use (non-refundable digital goods, clearly stated in Terms). Stripe Radar handles fraud detection. Keep dispute rate under 0.1% or Stripe may suspend the account. At low volume this is not a meaningful risk.

### Scenario 5: LLM provider raises prices
- **Risk:** DeepSeek raises prices 10x overnight. Your cost per run goes from €0.02 to €0.20.
- **Mitigation:** Multi-provider fallback is already built. Switch `WRITING_PROVIDER` to OpenRouter/Qwen or Anthropic/Haiku. Costs stay under €0.10/run even at worst case. Margin compresses but never goes negative at current pricing.

### Scenario 6: Supabase storage accumulates
- **Risk:** 10,000 PDFs × 500KB = 5GB. Supabase Pro includes 100GB.
- **Mitigation:** Auto-delete PDFs older than 90 days (cron job in Supabase). Users who want permanent storage can download. This is a v2 feature — at early stage, 5GB is nowhere near the limit.

### Scenario 7: VAT / tax liability (important)
- **Risk:** EU VAT rules apply to digital services sold to EU consumers. Once you exceed €10,000/year in cross-border EU sales, you must register for VAT OSS (One-Stop Shop) and collect VAT per customer country.
- **Mitigation:** Stripe Tax handles collection and reporting automatically. Enable it before launch. Cost: 0.5% of transactions. Budget this in from day one.
- **Before €10,000/year:** You are below the threshold. No VAT registration required. Still, display prices as "excl. VAT" and handle it cleanly when you cross the threshold.

### Summary: your actual maximum monthly exposure at zero revenue

| Item | Monthly cost | Notes |
|---|---|---|
| Supabase | €0 | Free tier covers early stage |
| Modal | €0 | $30 free credits (~400 runs) |
| Vercel | €0 | Free tier |
| Stripe | €0 | No transactions, no fees |
| Free credit abuse (100 abusers) | ~€2.30 | One-time cost, not recurring |
| **Total** | **~€0** | |

You will not spend money before you earn money.

---

## What You Might Be Missing

### Things with real consequences if skipped

**1. Email service**
You need transactional email: signup confirmation, "run complete" notification, password reset. Resend.com is free up to 3,000 emails/month and has a good Next.js integration. Without it, users won't know their run finished if they closed the tab. Add this to Phase A.

**2. GDPR compliance (serious for EU)**
You are storing resumes — highly personal documents — of EU citizens. Required before launch:
- Privacy policy (what you store, why, for how long)
- Cookie consent banner (if using analytics)
- Data deletion: users must be able to delete their account and all their data
- Data processing: you are a data processor for user resumes. Supabase is your sub-processor. Check Supabase's GDPR docs.
- Add a "Delete my account" button that wipes the `profiles`, `resumes`, `runs` rows and Supabase Storage files.

**3. Rate limiting**
Without rate limiting, a single user can hammer your API endpoint and rack up Modal costs. Add: max 5 concurrent runs per user, max 10 runs per hour per user. Implement in the Next.js API route before triggering Modal.

**4. Terms of service**
Required before taking any payment. Minimum: no refunds on used credits (digital goods), acceptable use policy (no bulk scraping competitors, no automated abuse), limitation of liability. Use a generator like Termly for v1 — fix it properly when revenue justifies a lawyer.

**5. A domain name**
`jobquest.io`, `jobquest.app`, or `getjobquest.com` — check availability. ~€15/year on Cloudflare Registrar (cheapest registrar, no markup). This is the only unavoidable upfront cost besides your time.

### Things that matter for growth but can wait

**6. Analytics**
Posthog (open-source, generous free tier) tells you which steps users drop off at, which pricing tier converts best, and where the funnel breaks. Add it in Phase B. Do not add it before you have users — premature optimization.

**7. Multilingual support**
Your pipeline already handles non-English job postings (with a warning). For the SaaS, the UI language is the main gap. v2 feature: detect browser language, offer UI in German/Spanish/French. The pipeline output language should follow the job posting language.

**8. Referral program**
"Give a friend 3 credits, get 3 credits yourself." Classic growth mechanic, costs you ~€0.07 per referred user (3 × €0.023). Extremely high ROI for word-of-mouth among job seekers. Phase D.

**9. A way to contact you**
A visible email address or Tally form for support. Job seekers who hit a failed run will want to know why. Without a contact channel you'll get chargeback disputes instead of support tickets. Add a simple `support@jobquest.io` forwarding to your personal email.

**10. Pricing page clarity**
Make the "no subscription required, pay as you go" message extremely visible. The #1 complaint about competitors is hidden billing. Your pricing model is honest — make sure it reads that way. Show the price before asking for a card, always.

---

*This document is the authoritative source for v1. Changes to scope, stack, or constraints should be discussed with Claude before implementation.*
