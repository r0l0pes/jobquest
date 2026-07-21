# JobQuest — New Laptop Setup Runbook

Pi reads this first on the new laptop. Execute the steps below so Rodrigo can start working immediately.

**You are on laptop #2 (fresh clone). Laptop #1 had everything committed and pushed before cloning.**

---

## Context

- Repo: `https://github.com/r0l0pes/jobquest.git` (owner: `r0l0pes`)
- Active branch: `feat/pipeline-quality-gates` (current work)
- Other branches exist on origin: `main`, `feat/webwright-fallback`, `feat/discovery-live-log`, `feat/german-language-support`
- Stack: Python 3.14, Gradio 6, Playwright, Notion API, multi-provider LLM, LaTeX PDF compile
- Test suite: `pytest tests/ -v` (186+ tests, ~1.4s)

What is deliberately NOT in git (must set up fresh here):

| Item | Reason | Action |
|------|--------|--------|
| `.env` | Secrets | Copy from `.env.example`, fill in real keys |
| `venv/` | Machine-specific | Create with python3.14 |
| `node_modules/` | Standard | `npm install` |
| `.master_resume_cache_*.txt` | Runtime cache | Auto-rebuilds from Notion on first run |
| `salary_data.json`, `.usage_stats.json` | Runtime | Regenerate by running pipeline |
| `output/*/`, `templates/*.pdf` | Build outputs | Regenerate by running pipeline |
| `data/applications.json`, `data/job_queue.html` | Tracker state | Start fresh on this laptop (intentional) |
| `.pi-lens/cache/`, `.pi-lens/sessions/`, `.pi-subagents/` | Runtime caches | Auto-regenerate; gitignored |

---

## Step 1 — System prerequisites (install once, before cloning)

| Tool | Why | Install |
|------|-----|---------|
| Python 3.14 | Project targets 3.14 | `brew install python@3.14` (verify `python3.14 --version`) |
| Node.js + npm | `package.json` dep (pi-agent-goal) | `brew install node` |
| LaTeX engine | `pdflatex` for PDF compile | `brew install --cask mactex` OR `brew install tectonic` (lighter) |
| Git | Clone | `brew install git` |
| Pi (this agent harness) | Run agent + skills | `npm install -g @earendil-works/pi-coding-agent` |
| GitHub auth | Push/pull |PAT or SSH key for `github.com/r0l0pes/jobquest` |

On macOS, also install Xcode Command Line Tools first: `xcode-select --install`.

`.mcp.json` references `context7` via `npx`, so Node is required even for MCP.

---

## Step 2 — Clone and checkout

```bash
git clone https://github.com/r0l0pes/jobquest.git
cd jobquest
git checkout feat/pipeline-quality-gates
```

Verify branch is clean:

```bash
git status               # should be clean
git log --oneline -5     # tip should be "feat: add scraper source modules, schemas, tests..."
```

---

## Step 3 — Create `.env` from template

```bash
cp .env.example .env
```

Then **open `.env` and fill in real values**. Required keys come from laptop #1's `.env` (Rodrigo has them). Do NOT commit `.env`, it is gitignored.

Required fields:

| Key | Source |
|-----|--------|
| `GEMINI_API_KEY` | <https://aistudio.google.com/apikey> |
| `GROQ_API_KEY` | <https://console.groq.com> (optional but in fallback chain) |
| `SAMBANOVA_API_KEY` | <https://cloud.sambanova.ai> (optional) |
| `OPENCODE_API_KEY` | <https://opencode.go> (Kimi K2.6, optional) |
| `OPENROUTER_API_KEY` | <https://openrouter.ai/keys> (optional) |
| `NOTION_TOKEN` | Notion integration secret |
| `NOTION_MASTER_RESUME_ID` | Notion page ID of master resume |
| `NOTION_APPLICATIONS_DB_ID` | Notion applications database ID |
| `NOTION_QA_TEMPLATES_DB_ID` | Notion QA templates database ID |
| `NOTION_SKILLS_KEYWORDS_DB_ID` | Notion skills/keywords database ID |
| `APPLICANT_NAME`, `APPLICANT_EMAIL`, `APPLICANT_PHONE`, `APPLICANT_LINKEDIN`, `APPLICANT_LOCATION` | Rodrigo's contact info |

Optional: `GEMINI_WRITING_MODEL`, `LLM_PROVIDER` (defaults are fine).

**Rodrigo must provide the actual secret values.** Ask him if not supplied.

---

## Step 4 — Python environment

```bash
python3.14 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install        # downloads browser binaries
```

Verify:

```bash
python --version        # 3.14.x
python -c "import gradio, playwright, notion_client, bs4; print('deps ok')"
```

---

## Step 5 — Node dependencies

```bash
npm install
```

Only `pi-agent-goal` is in `package.json`. `node_modules/` is gitignored.

---

## Step 6 — Pi agent harness (if not already on this machine)

```bash
npm install -g @earendil-works/pi-coding-agent
pi --version           # should print a version (laptop #1 had 0.80.3)
```

Pi extensions used by this project (install if Rodrigo wants the agent features AGENTS.md references):

```bash
pi install npm:pi-subagents     # provides `subagent` tool (required by skills)
pi install npm:pi-ask-user      # provides `ask_user` tool (recommended)
```

Pi-specific config that does NOT travel via git (lives in `~/.pi/`):

- `~/.pi/agent/AGENTS.md` — global agent rules (vision/screenshot safety)
- `~/.pi/agent/skills/` — installed skill packs
These must be set up on this laptop independently. Check `pi doctor` or `pi` settings.

---

## Step 7 — Verify the install

```bash
source venv/bin/activate
pytest tests/ -v
```

Expect 186+ tests passing in ~1.4s. If tests fail, do NOT continue, diagnose first (likely missing `.env` keys or a missing system tool).

Smoke check the CLI dry-run:

```bash
python apply.py "https://example.com/job" --dry-run
```

---

## Step 8 — Launch (one-click)

```bash
./JobQuest.command
```

Or start services individually:

```bash
source venv/bin/activate
python serve_tracker.py --port 7880 &    # Tracker + Discovery + API
python web_ui.py &                         # Pipeline UI (Gradio, port 7860)
```

URLs:

- Pipeline  → <http://127.0.0.1:7860>
- Tracker   → <http://127.0.0.1:7880>
- Discovery → <http://127.0.0.1:7880/queue>

---

## Operating rules (from AGENTS.md, must hold on this laptop too)

1. **Never fabricate resume content.** Only keywords from verified skills.
2. **Never auto-submit applications.** Rodrigo submits manually.
3. **Prompts are files.** Never inline prompt text, load from `prompts/*.md`.
4. **No em dashes.** Use commas, colons, or sentence breaks.
5. **Test after every change.** `pytest tests/ -v`, 186+ tests must pass.
6. **Spec before build.** Write spec in `specs/` before touching code.
7. **Vision-only models for screenshots.** See `~/.pi/agent/AGENTS.md` for the vision model allowlist (e.g. `opencode-go/kimi-k2.6`, `google/gemini-2.5-flash`). Non-vision models break screenshots.

---

## Quick start once setup is done

```bash
source venv/bin/activate
python apply.py "JOB_URL"                    # full pipeline
python apply.py "JOB_URL" --skip-reviewer    # skip adversarial review
python apply.py --upskill                     # skill gap analysis
pytest tests/ -v                              # tests
```

Agent modes (Pi): "Read `modes/discover.md` and find jobs", "Read `modes/prep_interview.md` for Company X", "Read `modes/batch.md` and process my queue".

Tracker server API surface is documented in `AGENTS.md`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `pdflatex: command not found` | LaTeX engine missing, install MacTeX or tectonic (Step 1) |
| Notion calls fail / 401 | `NOTION_TOKEN` missing or wrong in `.env` |
| `playwright` import ok but browser launch fails | Rerun `python -m playwright install` |
| Screenshot error "model does not support images" | Switch to a vision model, see `~/.pi/agent/AGENTS.md` |
| `python` resolves to wrong version | `source venv/bin/activate` before every command |
| Tests fail on import | `pip install -r requirements.txt` while venv active |

---

## Checklist for the agent (read this as a TODO)

- [ ] Confirm system tools installed: `python3.14`, `node`, `npm`, `pdflatex` (or `tectonic`), `git`, `pi`
- [ ] Clone + `git checkout feat/pipeline-quality-gates`, verify clean status
- [ ] `cp .env.example .env` and fill real keys (ask Rodrigo for secrets)
- [ ] `python3.14 -m venv venv`, `source venv/bin/activate`, `pip install -r requirements.txt`
- [ ] `python -m playwright install`
- [ ] `npm install`
- [ ] `pi --version`, install `pi-subagents` + `pi-ask-user` extensions if missing
- [ ] `pytest tests/ -v` green (186+ tests)
- [ ] `python apply.py "URL" --dry-run` succeeds
- [ ] Tell Rodrigo setup is complete and he can run `./JobQuest.command`
