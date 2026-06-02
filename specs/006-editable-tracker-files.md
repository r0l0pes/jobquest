# P6: Editable Q&A, Cover Letter & Resume in Tracker

**Status:** Spec
**Date:** 2026-06-02

## What

Make Q&A, Cover Letter, and Resume fields in the tracker editable via modals.
Each field opens a modal with a textarea pre-filled with content (text or .tex),
a save button, and a recompile-PDF option for the files.

## Why

After applying, the user may refine Q&A answers, edit cover letters, or update
resumes. Currently these fields are read-only — the user must manually edit files
on disk or re-run the pipeline. This adds a tight edit loop in the tracker itself.

## Core Schema

Each application entry in `applications.json` stores three editable fields:

```
qa: string              # Q&A markdown text
cover_letter: string    # path to .tex on disk
cover_letter_content: string  # .tex file contents (editable in modal)
resume: string          # path to .tex on disk
resume_content: string  # .tex file contents (editable in modal)
```

The `_content` fields are the source-of-truth for what gets displayed/edited.
The path fields (`cover_letter`, `resume`) indicate where the file lives for
PDF recompilation.

## Changes

### 1. Pipeline save (`apply.py`)

- `_save_application_json()` already saves `qa` from `qa_{company}.md`
- Add reading of `.tex` content for cover letter and resume files
- Store as `cover_letter_content` and `resume_content`

### 2. Tracker HTML (`data/tracker.html`)

**Q&A column:**
- Click "Q&A" button → opens modal with textarea pre-filled with `qa`
- "Save" button in modal → updates `apps[idx].qa`, marks dirty
- "Cancel" → closes without changes

**Cover Letter column:**
- Click "Cover" link → opens modal with textarea pre-filled with `cover_letter_content`
- If no `cover_letter_content`, show empty textarea with placeholder
- "Save" → updates `apps[idx].cover_letter_content`, marks dirty
- "Recompile PDF" → sends content to server endpoint, replaces cover letter PDF
- "Remove" → clears `cover_letter` and `cover_letter_content`

**Resume column:**
- Same as Cover Letter pattern, using `resume_content` and `resume`
- "Recompile PDF" → replaces resume PDF

### 3. Server endpoint (`serve_tracker.py`)

Add `POST /api/recompile` endpoint:

```python
# Input: { "app_idx": 0, "field": "cover_letter"|"resume", "content": "..." }
# 1. Write content to the .tex file on disk (from apps[idx].cover_letter|resume path)
# 2. Run render_pdf.py on that .tex file
# 3. Return { "ok": true, "pdf_path": "...", "error": "..." } if failed
```

### 4. Save integration

The existing `save()` function already POSTs the full apps array. The modals
update `apps[idx].cover_letter_content` etc., so those changes are included
in the next Save. The modal's "Save" calls `markDirty()`.

## UI Mockup

```
┌──────────────────────────────────────────────────┐
│  Q&A — JustPlay GmbH — Senior Product Manager   │
│  ───                                            │
│  [×] Close                              [Save]  │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │ ### Q: What motivates you...               │ │
│  │                                              │ │
│  │ ### A: JustPlay's assertion that...         │ │
│  │                                              │ │
│  │ _Used: C&A Brasil | 28% conversion...       │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  [ Recompile PDF ]  [ Remove File ]              │
└──────────────────────────────────────────────────┘
```

The Recompile PDF and Remove File buttons only appear on Cover Letter and
Resume modals (not Q&A).

## Test Scenarios

| Category | Scenario |
|----------|----------|
| Happy path | Click Q&A, edit text, Save, verify dirty indicator shows, click Save Changes, reload page and verify text persisted |
| Happy path | Click Cover Letter, edit LaTeX, click Recompile PDF, verify .tex file updated and PDF regenerated |
| Happy path | Click Resume, edit LaTeX, click Recompile PDF, verify .tex file updated and PDF regenerated |
| Edge case | Remove a file reference via the Remove button, verify JSON updated |
| Edge case | Click Save in modal without changing anything, verify no unnecessary dirty |
| Edge case | Recompile PDF when .tex path doesn't exist on disk, verify error shown in modal |
| Edge case | Open modal for entry that has no `cover_letter_content`, verify empty textarea with placeholder |
