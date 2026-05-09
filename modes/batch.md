# Mode: batch — Batch Pipeline Processing

When the user has multiple jobs in `data/job_queue.md` they want to process
through the pipeline, run them sequentially.

## Prerequisites

- `data/job_queue.md` has unchecked jobs (`- [ ]`)
- The pipeline is working (`python apply.py --dry-run` passes)

## Execution

1. Read `data/job_queue.md` — extract all unchecked URLs
2. For each URL:
   a. Run `python apply.py "<URL>"` (or with `--questions`, `--company-url` if known)
   b. Wait for completion
   c. Mark the job as `[x]` in the queue
   d. Log result (success/failure) to `data/batch_log.md`
3. Report summary: N jobs processed, M succeeded, K failed

## Parallel mode (when available)

If the user wants to run jobs in parallel, use the web UI's 3-slot design:

- Open `python web_ui.py`
- Paste URLs into the 3 slots
- The web UI runs them in parallel subprocesses

This is faster than sequential CLI processing.

## After batch

- Run `python serve_tracker.py` to review results
- Check scores — only apply to STRONG (80+) and GOOD (60+) jobs
- Skip WEAK (40-59) unless scarce
