# Spec 009: Second-Laptop Portability and Tracker Migration

**Status:** Implemented
**Date:** 2026-08-23

## Problem

JobQuest currently writes absolute local paths into tracker entries. A Git clone does not include generated `output/` files, and the setup documentation is out of sync with the current 363-test codebase, ports, providers, and branch state. A second macOS laptop must be able to reproduce the environment and migrate application history without retaining laptop-specific paths.

## Goals

1. Provide a portable tracker representation using repository-relative paths.
2. Provide an explicit export/import command for application history, queue HTML, and generated output directories.
3. Make future pipeline saves portable and allow the tracker server to recompile relative-path entries.
4. Synchronize setup and operating documentation with the current repository.
5. Document every current environment variable, including per-step model routing.
6. Repair tests whose mocks still target deprecated LLM seams.
7. Verify the Python suite, dry-run, launcher prerequisites, and local HTTP pages.

## Non-goals

- No automatic application submission.
- No migration of secrets or `.env` values.
- No cross-platform launcher rewrite; the supported target here is macOS.
- No change to the LLM model recommendation or Anthropic caching implementation.

## Data contract

Tracker path fields (`run_dir`, `pdf_path`, `resume`, `cover_letter`, and `cover_letter_pdf_path` when present) are stored relative to the repository whenever they point inside the repository. Legacy absolute paths remain readable for backward compatibility. The migration exporter rewrites paths to relative form and copies referenced output directories.

## Migration commands

```bash
python scripts/migrate_tracker.py export --destination /path/to/jobquest-export
python scripts/migrate_tracker.py import --source /path/to/jobquest-export --force
python scripts/migrate_tracker.py normalize
```

Exports never include `.env`. Imports require `--force` before replacing existing tracker data.

## Acceptance criteria

- A newly saved tracker entry contains no repository-specific absolute path for files under the repository.
- Exported application JSON references `output/<run-directory>/...` and the referenced output directory is present in the export bundle.
- Import restores `data/applications.json`, `data/job_queue.html`, and output directories.
- Existing absolute path entries continue to work on the source laptop.
- The full test suite completes without network calls from stale mocks.
- Setup docs agree on ports, test count, current branch, providers, and migration workflow.
