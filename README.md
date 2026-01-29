# JobQuest 🚀

An automated system to find, tailor resumes for, and track job applications, specifically designed for Product Manager roles in the European startup ecosystem.

## 🎯 Project Overview
This system automates the tedious parts of the job search (discovery, keyword tailoring, and answer drafting) while keeping a **"Human-in-the-loop"** for final review and submission to avoid risk (e.g., LinkedIn bans). It leverages **Agentic Skills** and **MCP (Model Context Protocol)** to bridge the gap between AI reasoning and personal knowledge stored in Notion.

### 🏠 System Architecture
- **Knowledge Base (Notion)**: Single source of truth for master resume, case studies, and metric-backed Q&A templates.
- **Tracker Board (Notion/Linear)**: Kanban pipeline for application funnel management (To Apply → Ready → Applied → Interview → Offer/Reject).
- **Agentic Skills**: Specialized modules for resume tailoring, ATS verification, and Q&A generation.

## 🛠 Features

- **Direct-to-Source Discovery**: Targets specific startup pools and uses specialized search queries (excluding aggregators like LinkedIn/Glassdoor) to find direct ATS links (Greenhouse, Lever, Personio) on company career pages.
- **Custom MCP Integration**: Connects directly to **Notion API** via MCP (Model Context Protocol) to read project background and track progress in real-time.
- **Resume Tailoring & Verification**: 
  - Generates tailored resumes by compiling LaTeX templates (using `pdflatex`).
  - **ATS-Fixer**: A specialized verification layer that checks keyword coverage, visibility, and consistency (title/seniority/location) before the final render.
- **Form Automation**: Automatically fills out job application forms (ATS) using Playwright while preserving a manual review step.
- **Notion Tracking**: Automatically syncs every application to a Notion database via the Notion API.
- **Agentic Skills**: 
  - `resume-tailor`: Reads job postings and suggests honest keyword updates.
  - `ats-fixer`: Performs semantic matching and visibility audits to minimize avoidable rejections.
  - `qa-generator`: Drafts metric-backed application answers in a direct, builder-oriented tone.

## 📁 Project Structure

- `batch_job_search.py`: Core script for bulk job discovery using targeted DDG queries.
- `scripts/`:
  - `form_filler.py`: Generic ATS form filler using Playwright (PAUSES for review).
  - `notion_tracker.py`: Syncs application progress to Notion using the official API.
  - `render_pdf.py`: Compiles LaTeX resumes into PDFs.
  - `notion_db_setup.py`: Initializes the required Notion database schema.
- `.agent/skills/`: Custom agentic workflows:
  - `resume-tailor/SKILL.md`: Instructions for ATS optimization.
  - `ats-fixer/SKILL.md`: Verification layer for keyword and format compliance.
  - `qa-generator/SKILL.md`: Instructions for drafting authentic answers.
- `templates/`: Contains LaTeX resume templates.

## 🚀 Getting Started

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configuration**:
   - Update `.env` with your `NOTION_TOKEN` and `APPLICATIONS_DB_ID`.
   - Ensure `pdflatex` is installed for resume generation.

3. **Search for Jobs**:
   ```bash
   python batch_job_search.py
   ```

4. **Prepare & Track**:
   Use the `qa-generator`, `resume-tailor`, and `ats-fixer` skills in your agentic IDE to prepare materials, then track them:
   ```bash
   python scripts/notion_tracker.py create --title "Senior PM" --company "StartupX" --url "..."
   ```

5. **Fill Applications**:
   ```bash
   python scripts/form_filler.py --url <JOB_URL> --resume-pdf <PATH_TO_PDF>
   ```

## 🗺 Roadmap
- **Phase 1 (Current)**: Notion/Linear integration, Agentic Skills, and automated form filling.
- **Phase 2**: Email monitoring for rejections (auto-GDPR deletion requests), interview prep briefings, and WhatsApp integration for daily match alerts.

## ⚠️ Safety First
- **Zero Ban Risk**: The system NEVER auto-submits applications. It fills the form and waits for you to review and click "Submit".
- **Authenticity**: Metrics and experience are pulled from pre-validated "Master" documents to ensure honesty.
