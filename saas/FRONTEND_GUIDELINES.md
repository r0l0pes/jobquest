# JobQuest — Frontend Guidelines

**INTERNAL — do not commit to git, do not share publicly.**

---

## Design System

- **Framework:** Next.js 14+ App Router
- **Styling:** Tailwind CSS
- **Components:** shadcn/ui (copy-paste, no lock-in)
- **Icons:** Lucide React
- **Font:** System default (Inter via Tailwind)

### Color palette

| Token | Value | Use |
|---|---|---|
| Background | `#030712` (gray-950) | Page backgrounds |
| Surface | `#111827` (gray-900) | Cards, sidebars |
| Border | `#1f2937` (gray-800) | Card borders, dividers |
| Text primary | `#ffffff` | Headings, key values |
| Text secondary | `#9ca3af` (gray-400) | Labels, descriptions |
| Text muted | `#4b5563` (gray-600) | Disabled, timestamps |
| Green (success/CTA) | `#22c55e` (green-500) | Buttons, completed steps, high match |
| Green hover | `#4ade80` (green-400) | Button hover |
| Amber (warning) | `#f59e0b` | Medium match, warnings |
| Red (error) | `#ef4444` | Failed steps, low match |

---

## Component Conventions

- All interactive components are client components (`"use client"`)
- Data fetching happens in server components or server actions
- shadcn/ui base components styled with Tailwind utility classes
- No inline styles — Tailwind only
- No CSS modules

---

## Wow Factor — Differentiating Moments

These are non-negotiable UX moments. Build them into Phase A, not as afterthoughts.

### 1. Match framing

Never use the word "score." Always "match" or "match to this role."

```tsx
// Wrong
<span>ATS score: {run.ats_score}%</span>

// Right
<span>{run.ats_score}% match to this role</span>
```

### 2. Time estimate at the start of every run

First thing shown on the progress screen before any steps:

```tsx
<div className="text-center mb-10">
  <p className="text-sm text-gray-400 font-medium">Estimated time: 2-3 minutes</p>
  <p className="text-xs text-gray-600 mt-1">You can close this tab — we'll email you when it's done.</p>
</div>
```

### 3. Live decisions on the progress screen

Active step shows what the pipeline is deciding, not just a label. `current_step` in Supabase carries a structured string:

```
→  Analysing job requirements...
   Detected: product-led growth, SQL, activation funnel
   Strategy: inserting 3 keywords, updating summary
```

Parse and render the multi-line string. Single-line = step label. Multi-line = step label + decision detail below in `text-gray-500 text-xs`.

### 4. Tailoring brief reveal (mid-run)

After step 3a (`analyse_jd_brief`) completes, the pipeline writes the brief summary to `runs.brief_preview` (a short plaintext string, max 200 chars). The progress screen renders this as a highlighted card between the analysis and tailoring steps:

```tsx
{run.brief_preview && (
  <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 my-3 text-sm">
    <p className="text-green-400 text-xs font-medium mb-2">Here's the plan</p>
    <p className="text-gray-300 whitespace-pre-line">{run.brief_preview}</p>
  </div>
)}
```

### 5. Before/after diff with inline editing

On the results page, show changed bullets as a diff. Each after-bullet is editable in place:

```tsx
// Diff item
<div className="space-y-1">
  <p className="text-sm text-gray-500 line-through">{bullet.before}</p>
  {editing === bullet.id ? (
    <div className="flex gap-2">
      <textarea
        className="flex-1 bg-gray-800 border border-green-500 rounded-lg px-3 py-2 text-sm resize-none"
        defaultValue={bullet.after}
        rows={3}
        onBlur={(e) => handleSave(bullet.id, e.target.value)}
        autoFocus
      />
    </div>
  ) : (
    <div className="flex items-start justify-between gap-3">
      <p className="text-sm text-green-300">{bullet.after}</p>
      <button
        onClick={() => setEditing(bullet.id)}
        className="text-xs text-gray-500 hover:text-white shrink-0"
      >
        edit
      </button>
    </div>
  )}
</div>
```

Saving triggers a server action that rewrites the `.tex` file and re-runs `pdflatex` via Modal. No extra credit charged.

### 6. Email delivers the PDF directly

Run complete email includes the PDF as an attachment (via Resend). Do not just link back to the app.

---

## Screen Templates

### Navigation sidebar (dashboard)

```tsx
<aside className="w-56 bg-gray-900 border-r border-gray-800 p-4 flex flex-col gap-1">
  <span className="text-lg font-bold px-2 py-3 mb-2">JobQuest</span>
  {navItems.map((item) => (
    <a key={item.label} href={item.href}
      className={`text-sm px-3 py-2 rounded-lg ${
        item.active
          ? "bg-gray-800 text-white"
          : "text-gray-400 hover:text-white hover:bg-gray-800"
      }`}>
      {item.label}
    </a>
  ))}
  <div className="mt-auto bg-gray-800 rounded-lg p-3 text-sm">
    <div className="text-gray-400 mb-1">Credits</div>
    <div className="text-2xl font-bold text-green-400">{credits}</div>
    <a href="/dashboard/credits" className="text-xs text-gray-400 hover:text-white mt-1 block">
      Buy more →
    </a>
  </div>
</aside>
```

### Match score display

```tsx
<div className="flex items-center justify-between mb-4">
  <h2 className="font-semibold">Match to this role</h2>
  <span className={`text-2xl font-bold ${
    score >= 70 ? "text-green-400" : score >= 50 ? "text-amber-400" : "text-red-400"
  }`}>
    {score}%
  </span>
</div>
<div className="w-full bg-gray-800 rounded-full h-2">
  <div
    className={`h-2 rounded-full transition-all duration-700 ${
      score >= 70 ? "bg-green-500" : score >= 50 ? "bg-amber-500" : "bg-red-500"
    }`}
    style={{ width: `${score}%` }}
  />
</div>
```

### Progress step item

```tsx
<div className={`flex items-center gap-3 px-4 py-2.5 rounded-lg ${
  active ? "bg-gray-800 border border-gray-700" : ""
}`}>
  <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs shrink-0 ${
    done
      ? "bg-green-500 text-black"
      : active
      ? "border-2 border-green-500 animate-pulse"
      : "border border-gray-700"
  }`}>
    {done && "✓"}
  </span>
  <span className={`text-sm ${
    done ? "text-gray-400 line-through" : active ? "text-white font-medium" : "text-gray-600"
  }`}>
    {step}
  </span>
</div>
```

---

## Accessibility

- All interactive elements keyboard accessible
- Color not used as the only signal (icons + labels alongside color)
- `aria-label` on icon-only buttons
- Focus rings visible (Tailwind `focus:outline-none focus:ring-2 focus:ring-green-500`)

---

## Design Resource

For the "wow factor" visual polish pass (after functional Phase A is complete):
https://impeccable.style/#hero

The current design is functional but generic. The visual differentiation pass is deferred to after Phase A ships.
