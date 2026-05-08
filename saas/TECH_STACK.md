# JobQuest — Tech Stack

**INTERNAL — do not commit to git, do not share publicly.**

---

## Stack Decisions

| Layer | Tool | Free tier | Why |
|---|---|---|---|
| Frontend + hosting | Next.js 14+ on Vercel | Generous free tier | Zero infrastructure, App Router, server components |
| Auth + DB + Storage | Supabase | 500MB DB, 1GB files, 50k MAUs | One service for auth, database, storage, and real-time |
| Pipeline execution | Modal | $30 compute credits/month (~400 runs) | Serverless Python, no servers to manage, scales to zero |
| Payments | Stripe | No monthly fee | Industry standard, 2.9% + €0.30/transaction |
| Email | Resend | 3,000 emails/month free | Transactional email with Next.js SDK, supports attachments |
| Observability | Langfuse | 50k events/month free | LangGraph tracing, prompt versioning, LLM evals |

### Cost at zero revenue: €0/month

Everything runs on free tiers. No cost until ~400 runs/month. By then there is revenue.

---

## Do Not Use

| Tool | Why not |
|---|---|
| Appwrite | Self-hosted = you manage a server |
| Convex | TypeScript-first, pipeline is Python |
| Firebase | NoSQL is wrong shape for structured resume data |
| Neon alone | Just a database, needs separate auth + storage |
| LangSmith | $39/seat/month, vendor lock-in to LangChain ecosystem |

---

## Frontend

- **Framework:** Next.js 14+ App Router
- **Styling:** Tailwind CSS
- **Components:** shadcn/ui (free, copy-paste, no lock-in)
- **Icons:** Lucide React
- **Color palette:** dark background (#030712), green (#22c55e) for success/CTA, amber for warnings, red for errors
- **Real-time:** Supabase client-side subscription (`postgres_changes`) for progress screen

---

## Backend

- **API routes:** Next.js server-side API routes (never client components)
- **Database:** Supabase Postgres
- **Auth:** Supabase Auth (email/password; Google OAuth in Phase E)
- **Storage:** Supabase Storage (private bucket, signed URLs only)
- **Pipeline execution:** Modal serverless function (Python 3.14)
- **Orchestration:** LangGraph (SaaS mode only; local CLI keeps existing pipeline.py)

---

## Pipeline Execution on Modal

The existing Python pipeline (`apply.py` + `modules/pipeline.py`) runs as a Modal function in SaaS mode.

- Modal function receives: `run_id`, `supabase_service_key`, `user_profile` dict
- Pipeline writes `current_step` to Supabase at each stage (progress screen reads via real-time)
- On completion: writes `status='complete'`, `ats_score`, `pdf_path`, `completed_at`
- On failure: writes `status='failed'`, `error_message`, refunds credit
- PDF uploaded to Supabase Storage at `resumes/{user_id}/{run_id}.pdf`

Modal secrets store: all LLM API keys (DeepSeek, Gemini, Groq). Never in DB, never in browser.

---

## LLM Providers

Two tiers — never mix them:

**Writing steps (3b, 6, 8) — quality-critical:**
Primary: DeepSeek V3.2 (~€0.015/run with caching)
Fallback chain: DeepSeek → OpenRouter/Qwen3.5-397B → Groq → SambaNova

**Analysis/check steps (3a, 3c, 5) — speed-critical:**
Primary: Gemini 2.0 Flash (free, 250 RPD)
Fallback: Groq → SambaNova

---

## Observability — Langfuse

Every LLM call inside the LangGraph pipeline is automatically traced via `CallbackHandler`.

```python
from langfuse.callback import CallbackHandler

langfuse_handler = CallbackHandler(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    session_id=run_id,
    user_id=user_id,
)

graph.invoke(state, config={"callbacks": [langfuse_handler]})
```

Thumbs-down on results page writes a score of 0 to that run's Langfuse trace. User feedback becomes an eval signal automatically.

---

## Environment Variables

### Next.js (server-side only)
```env
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...        # never in client components
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
RESEND_API_KEY=...
```

### Modal secrets
```env
SUPABASE_SERVICE_ROLE_KEY=...
DEEPSEEK_API_KEY=...
GEMINI_API_KEY=...
GROQ_API_KEY=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
```
