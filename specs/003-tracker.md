# P3: Application Tracker

**Status:** Implemented
**Date:** 2026-05-08

## What

A standalone HTML file (`data/tracker.html`) that reads `data/applications.json`
and renders a sortable, filterable, editable table of all applications.

Zero tokens, zero server, zero API calls.

## Why

Notion's UI is clunky for browsing applications. The pipeline already writes to
`data/applications.json`. This gives you an instant visual dashboard.

## Features

- Sortable by company, role, score, date, status
- Filterable by status (dropdown)
- Color-coded score badges (STRONG=green, GOOD=yellow, WEAK=orange, SKIP=red)
- Inline-editable status (select dropdown) and notes (text field)
- Save button writes changes back to applications.json
- Search by company or role name
- Shows days since application

## How

Open `data/tracker.html` in any browser. The JavaScript reads
`data/applications.json` via a tiny Python HTTP server.
