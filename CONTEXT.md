# JobQuest — Discovery & Tracker Context

JobQuest is an automated job application pipeline. The user pastes a job URL and gets a tailored PDF resume, ATS report, fit score, Q&A answers, and cover letter. Manual apply only — no auto-submission.

This document captures the domain language for the Discovery and Tracker subsystem.

## Language

**Job Discovery**:
The process of searching job boards (Exa API) for matching PM positions. Runs 41 queries across multiple search catalog entries, deduplicates results, verifies URLs are still live, and appends new jobs to the queue.
_Avoid_: Job search, scan

**Discovery Pop-up**:
The modal that appears when loading the Discovery page (`/queue`). Displays time range (7d/24h) and queue-clearing options before starting discovery.
_Avoid_: Dialog, prompt, overlay

**Discovery Log**:
The streaming stderr output from `discover_jobs.py` shown live in the Discovery Pop-up while the script runs. Shows which query is being searched, raw results count, dead URL skips, and verification progress.
_Avoid_: Console, terminal, output

**Job Queue**:
The HTML file (`data/job_queue.html`) that lists discovered jobs. Served at `/queue` on the tracker server.
_Avoid_: Queue file, job list

**Tracker Server**:
The Python HTTP server (`serve_tracker.py`) that serves the Tracker page, Discovery page, and REST API. Uses `ThreadingHTTPServer` for concurrent request handling.
_Avoid_: Backend server, API server

**Discovery Run**:
A single execution of `discover_jobs.py` against the Exa API. Started via `POST /api/discover` and monitored via `GET /api/discover-log/<id>`. Runs in a background thread.
_Avoid_: Discovery job, discovery process

**Post-discovery behavior**:
After a discovery run completes (or fails), the Discovery Pop-up stays open showing the result. The user decides whether to close, reload the page to see the updated queue, or investigate an error.
_Avoid_: Completion, finish flow

## Relationships

- A **Discovery Run** is started from the **Discovery Pop-up**
- During a **Discovery Run**, the **Discovery Log** streams live progress into the **Discovery Pop-up**
- After a **Discovery Run**, new results are appended to the **Job Queue**
- The **Tracker Server** handles all requests — pages and API — concurrently using threading, so Tracker pages remain accessible during a **Discovery Run**

## Example dialogue

> **Dev:** "When I start a **Discovery Run** with 7d mode, where does the output go?"
> **User:** "I want to see it live in the **Discovery Pop-up** — each query being searched, how many results, dead URLs skipped. If the script times out, I need to see which query it was stuck on."
>
> **Dev:** "And after it finishes?"
> **User:** "Leave the pop-up open showing the result. I'll decide if I want to close it and reload, or investigate if something went wrong."

## Flagged ambiguities

- "Console" was used to mean both a terminal window and the streaming log area inside the pop-up — resolved: use **Discovery Log** for the pop-up area.
- "Discovery process" was ambiguous between the script (`discover_jobs.py`) and a single execution — resolved: use **Discovery Run** for one execution.
