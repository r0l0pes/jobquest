# Spec: Pi Skill Cleaner

**Author:** Rodrigo Lopes  
**Date:** 2026-05-26  
**Status:** Implemented ✅  
**Related:** [steipete/skill-cleaner](https://github.com/steipete/agent-scripts/blob/main/skills/skill-cleaner/SKILL.md) (OpenClaw/Codex)

---

## Problem

Pi skills are scattered across multiple roots (`~/.pi/agent/skills/`, `~/.agents/skills/`, `.pi/skills/`, etc.) and loaded from packages. Over time, this leads to:

1. **Duplicate skills** — same name or identical body across roots (e.g. both `~/.pi/agent/skills/impeccable/` and a package-installed copy).
2. **Unused skills** — skills installed but never triggered in recent sessions, consuming prompt budget.
3. **Overlong descriptions** — Pi warns at >1024 chars; long descriptions inflate the system prompt even when skills are unused.
4. **Unknown prompt cost** — no visibility into how many tokens all skill descriptions consume.

We need a diagnostic script — analogous to steipete's `skill-cleaner` for Codex — that audits all Pi skill roots and produces a human-readable report.

---

## Goals

| Goal | Priority |
|------|----------|
| Discover all skill roots Pi would load | P0 |
| Detect duplicate skills (name + body similarity) | P0 |
| Identify unused skills based on run history | P0 |
| Estimate token cost of all skill descriptions | P0 |
| Flag descriptions >1024 chars (Pi limit) | P1 |
| Suggest trimmed descriptions to save tokens | P1 |
| Output as markdown report + optional JSON | P1 |
| Run in <1s for typical skill sets | P2 |

---

## Non-Goals

- Do **not** edit or delete skills automatically (suggest only).
- Do **not** parse Pi session logs beyond `run-history.jsonl` (deep session log parsing is future work).
- Do **not** access the pi-coding-agent internals (pure filesystem/JSON analysis).

---

## Skill Root Discovery (Pi-specific)

Per [Pi docs](https://github.com/earendil-works/pi-coding-agent/blob/main/docs/skills.md), skills load from:

1. `~/.pi/agent/skills/` — global, direct `.md` files count
2. `~/.agents/skills/` — global alias, `.md` files ignored at root
3. `.pi/skills/` — project-local (cwd and ancestors up to git root)
4. `.agents/skills/` — project-local alias
5. Packages — `skills/` dirs or `pi.skills` in `package.json`
6. Settings — `skills` array in `~/.pi/agent/settings.json` (files or dirs)
7. CLI — `--skill <path>` (not discoverable post-hoc)

For the script, we scan:
- `~/.pi/agent/skills/`
- `~/.agents/skills/`
- `.pi/skills/` (cwd)
- `.agents/skills/` (cwd)
- Paths from `~/.pi/agent/settings.json` `skills` array
- Paths from `~/.pi/agent/settings.json` `packages` (npm packages that may contain skills)

Scope labels: `pi-global`, `pi-project`, `user-settings`, `package`

---

## Duplicate Detection

Two heuristics:

1. **Name collision** — same `name:` frontmatter (case-insensitive), different real path.
2. **Body similarity** — Jaccard similarity on normalized word sets of the full SKILL.md body.

Keep priority: `pi-project` > `pi-global` > `user-settings` > `package`

Similarity threshold for "likely copy": `body >= 0.95` or `(body >= 0.85 AND description >= 0.85)`.

---

## Usage Detection

Scan `~/.pi/agent/run-history.jsonl` for:
- Explicit `read` of `skills/<name>/SKILL.md`
- Mentions of skill name in tool calls or task descriptions

Flag skills with zero usage in last N months (default: 3).

---

## Token Cost Estimation

Pi renders skills in XML format in the system prompt per [Agent Skills spec](https://agentskills.io/integrate-skills). We estimate cost as:

```
tokens = ceil(utf8_bytes_of_rendered_skill_line / 4)
rendered_line = `- name: description (file: path)`
```

This matches steipete's Codex heuristic. Pi's actual rendering may differ, but this gives a useful relative metric.

Budget context: use current default model from `settings.json` → look up `contextWindow` in `models.json`.

---

## Output Sections

1. **Skill Budget** — model, context window, % used, tokens used, remaining
2. **Long Descriptions** — >1024 chars or >180 rendered line chars; suggest shorter alternatives
3. **Duplicates By Name** — groups with similarity scores
4. **Duplicate Delete Suggestions** — which copy to keep, which to delete
5. **Duplicates By Body Hash** — exact body hash matches
6. **Unused Candidates** — zero-usage skills with scope
7. **Root Summary** — skills per root, disabled counts

---

## CLI Interface

```bash
python scripts/pi_skill_cleaner.py [OPTIONS]
```

Options:
- `--months N` — usage lookback (default 3)
- `--no-logs` — skip usage scanning
- `--json` — output JSON instead of markdown
- `--root PATH` — extra skill root to scan
- `--model MODEL` — override model for context window lookup
- `--budget-percent P` — assume P% of context for skills (default 2)
- `--context-tokens N` — override context window size

---

## Testing

- Run on this repo: should discover `.pi/skills/job-discovery/`, `~/.pi/agent/skills/impeccable/`, `~/.pi/agent/skills/mattpocock-skills/*`
- Check that `job-discovery` shows as `pi-project`
- Check that `impeccable` shows as `pi-global`
- Verify no false duplicates between genuinely different skills

---

## Open Questions

1. Should we parse `package.json` `pi.skills` entries from installed npm packages? (Complex; defer to v2)
2. Should we scan `~/.pi/agent/sessions/` for deeper usage? (Defer to v2)
3. How does Pi actually truncate descriptions? (Undocumented; use equal-truncation heuristic like Codex)
