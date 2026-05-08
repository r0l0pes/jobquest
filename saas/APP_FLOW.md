# JobQuest — Application Flow

**INTERNAL — do not commit to git, do not share publicly.**

---

## The Full Journey — Before, Middle, After

```
BEFORE                       MIDDLE              AFTER
───────────────────────      ──────────────      ──────────────────────────────
Master resume                Pipeline runs       Company
Case studies                 (9 steps,           Date applied
Metrics bank                 2-3 minutes)        Job title
Skills & tools bank                              Job URL
Q&A templates                                    Resume used
                                                 Match % (ATS score)
                                                 Q&A answers
                                                 Application status
                                                 (applied → screening
                                                  → interview → offer
                                                  → rejected)
```

The Before is the user's permanent profile — built once, improved over time, used on every run.
The Middle is the pipeline — identical per run, triggered by a job URL.
The After is the application tracker — one entry per run, status updated manually as the process progresses.

---

## Screen Flow

```
Homepage (/)
    ↓
Sign up (/signup)  ←→  Log in (/login)
    ↓
Onboarding: Build profile (/onboarding)
    ↓
Dashboard (/dashboard)
    ├── New application (default)
    ├── Past applications (/dashboard/history)
    ├── My profile (/dashboard/profile)
    │       ├── Master resume
    │       ├── Case studies
    │       ├── Metrics bank
    │       ├── Skills & tools
    │       └── Q&A templates
    └── Credits (/dashboard/credits)
         ↓
Run triggered → Progress screen (/runs/[id]/progress)
         ↓
Results page (/runs/[id]/results)
```

---

## Screen 1: Homepage

- Headline: "Paste a job URL. Get the application."
- Sub: "JobQuest tailors your resume, checks ATS keywords, and writes your application answers in under 5 minutes."
- CTA: "Start for free" → /signup
- Social proof: "2 free applications — no card required"
- 4-step visual: Paste URL → Tailor resume → See match score → Get answers

---

## Screen 2: Onboarding (profile setup)

Shown once after signup, before the user can run the pipeline.

- Step 1: Master resume (required — blocks progression if empty)
- Steps 2-5: Case studies, metrics bank, skills & tools, Q&A templates (optional but clearly framed as multipliers)
- Profile completeness indicator shown throughout
- Copy: each section explained with what it unlocks ("Case studies power your Q&A answers. Without them, answers will be generic.")
- User can skip optional sections and return later — dashboard always shows completeness %

---

## Screen 3: Dashboard — New Application

- Job posting URL input (required)
- Application questions textarea (optional, one per line)
- Credits remaining shown in sidebar
- "Run — 1 credit" submit button — disabled if no URL or credits = 0
- If credits = 0: "Out of credits. Buy more →"
- If no resume on file: button blocked, "Add your resume first →"

---

## Screen 4: Progress Screen

Shown immediately after run is triggered. Supabase real-time subscription on the `runs` row.

- Header: estimated time ("Estimated time: 2-3 minutes")
- Sub: "You can close this tab — we'll email you when it's done."
- Step list with three states: done (green check + strikethrough), active (pulsing), pending (gray)
- Active step shows live decisions, not just a label:
  ```
  ✓  Found: Senior PM, Growth — N26, Berlin
  ✓  Resume loaded (847 words)
  →  Analysing job requirements...
     Detected: product-led growth, SQL, activation funnel, A/B testing
     Strategy: inserting 3 keywords, updating summary
  ```
- Mid-run pause after step 3a: tailoring brief shown before writing model runs
  ```
  Here's the plan for your application:
  - Leading with product-led growth in your summary
  - Adding "SQL" and "activation funnel" to your WFP bullets
  - Keeping your Accenture section intact — already strong for this role
  - Match target: 8 keywords detected, aiming for 6
  ```

### Pipeline steps shown

```
1.  Scraping job posting
2.  Reading your resume
3.  Analysing job requirements       ← brief revealed here
4.  Tailoring resume
5.  Checking brief compliance
6.  Running match check
7.  Applying keyword edits
8.  Compiling PDF
9.  Generating application answers
10. Done
```

---

## Screen 5: Results Page

### Header
- Green dot + "Complete"
- Job title + company
- "Report issue" button (thumbs-down, logs run ID to Langfuse, does not auto-refund)

### PDF card
- "Tailored resume — PDF, ready to upload"
- "Download PDF" button (signed URL, 1-hour expiry, generated server-side)
- PDF retention notice: "Free users: expires in 23h. Download now." or "Available for 30 days."

### Match score card
- Label: "Match to this role" (never "ATS score")
- Large number, color-coded: green ≥70%, amber ≥50%, red <50%
- Progress bar

### Before/after diff
- Shows 3-5 bullets that changed
- Additions highlighted green, removals struck through
- Each after-bullet has an [edit] affordance
- Clicking [edit]: bullet becomes an inline editable text field
- Save: regenerates PDF with the edit applied
- No extra credit charged for edits within a run

### Q&A answers
- Only shown if application questions were submitted
- One block per question: question in gray, answer below
- "Copy" button per answer

---

## Screen 6: Application Tracker

List view of all past runs.

Columns per entry:
- Job title (or "Unknown role")
- Company
- Date applied
- Match %
- Application status (user-editable dropdown: applied / screening / interview / offer / rejected)
- Link to results page

---

## Screen 7: Profile Pages

Five sub-pages under /dashboard/profile:

| Page | What user does |
|---|---|
| Master resume | Paste/edit full resume text. Single textarea. Auto-saved. |
| Case studies | Add named entries (title + freeform content). Edit/delete. |
| Metrics bank | Add metric + optional context. Edit/delete. |
| Skills & tools | Add name + category (skill/tool/language/methodology) + proficiency (expert/proficient/familiar). |
| Q&A templates | Add question + answer + optional tags. Edit/delete. |

Profile completeness indicator on each page: "3/5 sections complete."

---

## Screen 8: Credits Page

- Current balance (large number)
- Three pack options: Starter €2.99, Standard €5.99, Value €9.99
- Subscription option: €4.99/month for 20 credits
- Auto-recharge toggle: set threshold + pack
- Transaction history

---

## Email Flows

| Trigger | Email content |
|---|---|
| Signup | Confirmation link (Supabase Auth) |
| Run complete | "Your application for [role] at [company] is ready." + PDF attached |
| Auto-recharge | "We charged [pack] to your card. [N] credits added." |
| Run counter alerts | Internal email to Rodrigo at 100/200/300/400 runs/month |
