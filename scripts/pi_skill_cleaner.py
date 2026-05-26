#!/usr/bin/env python3
"""Pi Skill Cleaner — audit Pi skills for duplicates, unused skills, and prompt cost.

Adapted from steipete/agent-scripts skill-cleaner for OpenClaw/Codex.
Usage: python scripts/pi_skill_cleaner.py [OPTIONS]
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()
PI_AGENT_DIR = HOME / ".pi" / "agent"
PI_SETTINGS = PI_AGENT_DIR / "settings.json"
PI_MODELS = PI_AGENT_DIR / "models.json"
PI_RUN_HISTORY = PI_AGENT_DIR / "run-history.jsonl"
PI_GLOBAL_SKILLS = PI_AGENT_DIR / "skills"
AGENTS_GLOBAL_SKILLS = HOME / ".agents" / "skills"
PI_PROJECT_SKILLS = Path.cwd() / ".pi" / "skills"
AGENTS_PROJECT_SKILLS = Path.cwd() / ".agents" / "skills"

FALLBACK_CONTEXT_TOKENS = 262_144  # kimi-k2.6
DEFAULT_BUDGET_PERCENT = 2
CHARS_PER_TOKEN = 4


@dataclass
class Skill:
    name: str
    base_name: str
    description: str
    path: Path
    real_path: Path
    root: Path
    real_root: Path
    scope: str
    enabled: bool
    desc_chars: int = field(init=False)
    line_chars: int = field(init=False)
    line_bytes: int = field(init=False)
    body_hash: str = field(init=False)
    body_key: str = field(init=False)
    desc_key: str = field(init=False)

    def __post_init__(self) -> None:
        self.desc_chars = len(self.description)
        rendered = self.rendered_line(self.description)
        self.line_chars = len(rendered) + 1  # + newline
        self.line_bytes = len(rendered.encode("utf-8")) + 1
        body_text = self._read_body()
        self.body_key = self._normalize_words(body_text)
        self.body_hash = hashlib.sha1(self.body_key.encode()).hexdigest()[:16]
        self.desc_key = self._normalize_words(self.description)

    def _read_body(self) -> str:
        try:
            text = self.path.read_text(encoding="utf-8")
            lines = text.splitlines()
            if lines and lines[0].strip() == "---":
                for i in range(1, len(lines)):
                    if lines[i].strip() == "---":
                        return "\n".join(lines[i + 1 :])
            return text
        except Exception:
            return ""

    @staticmethod
    def _normalize_words(text: str) -> str:
        return " ".join(
            re.sub(r"[`\"'’().,;:!?/\\\[\]{}_-]+", " ", text.lower()).split()
        )

    def rendered_line(self, description: str) -> str:
        if description:
            return f"- {self.name}: {description} (file: {self.path})"
        return f"- {self.name}: (file: {self.path})"


@dataclass
class Budget:
    model: str
    context_tokens: int
    context_source: str
    budget_percent: float
    budget_tokens: int
    rendered_line_chars: int
    unbudgeted_full_tokens: int
    minimum_tokens: int
    budgeted_tokens: int
    included_skills: int
    omitted_skills: int
    truncated_description_chars: int
    truncated_description_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Pi skills")
    parser.add_argument("--months", type=int, default=3, help="Usage lookback (default 3)")
    parser.add_argument("--no-logs", action="store_true", help="Skip usage scanning")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--root", action="append", default=[], help="Extra skill root")
    parser.add_argument("--model", default="", help="Override model for context window")
    parser.add_argument("--budget-percent", type=float, default=DEFAULT_BUDGET_PERCENT)
    parser.add_argument("--context-tokens", type=int, default=0, help="Override context window size")
    parser.add_argument("--chars-per-token", type=int, default=CHARS_PER_TOKEN)
    parser.add_argument("--max-log-mb", type=int, default=300)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_default_model() -> str:
    settings = load_json(PI_SETTINGS)
    if settings:
        provider = settings.get("defaultProvider", "")
        model = settings.get("defaultModel", "")
        if provider and model:
            return f"{provider}/{model}"
    return "opencode-go/kimi-k2.6"


def get_model_context(model_id: str, override: int = 0) -> tuple[int, str]:
    if override > 0:
        return override, "--context-tokens"

    models = load_json(PI_MODELS)
    if models and "providers" in models:
        for provider, pdata in models["providers"].items():
            for m in pdata.get("models", []):
                mid = m.get("id", "")
                full_id = f"{provider}/{mid}"
                if full_id.lower() == model_id.lower() or mid.lower() == model_id.lower():
                    ctx = m.get("contextWindow")
                    if isinstance(ctx, int) and ctx > 0:
                        return ctx, str(PI_MODELS)

    return FALLBACK_CONTEXT_TOKENS, "fallback:kimi-k2.6"


def discover_roots(extra_roots: list[str]) -> list[Path]:
    roots: list[Path] = [
        PI_GLOBAL_SKILLS,
        AGENTS_GLOBAL_SKILLS,
        PI_PROJECT_SKILLS,
        AGENTS_PROJECT_SKILLS,
    ]

    # From settings.json "skills" array
    settings = load_json(PI_SETTINGS)
    if settings:
        for skill_path in settings.get("skills", []):
            expanded = Path(os.path.expanduser(skill_path))
            if expanded.exists():
                roots.append(expanded)

    for extra in extra_roots:
        expanded = Path(os.path.expanduser(extra))
        if expanded.exists():
            roots.append(expanded)

    # Deduplicate by realpath, prefer shorter paths
    seen: dict[str, Path] = {}
    result: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        real = str(root.resolve())
        if real in seen:
            if len(str(root)) < len(str(seen[real])):
                seen[real] = root
        else:
            seen[real] = root
            result.append(root)
    return result


def scope_for(root: Path) -> str:
    parts = root.parts
    if ".pi" in parts and "agent" in parts and "skills" in parts:
        return "pi-global"
    if ".agents" in parts and "skills" in parts:
        return "agents-global"
    if ".pi" in parts and "skills" in parts:
        return "pi-project"
    if ".agents" in parts and "skills" in parts:
        return "agents-project"
    if "node_modules" in parts:
        return "package"
    return "extra"


def parse_frontmatter(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm: dict[str, str] = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            break
        match = re.match(r'^([A-Za-z0-9_-]+):\s*(.*)$', lines[i])
        if match:
            key, raw = match.group(1), match.group(2).strip()
            if raw in ('|', '>'):
                block: list[str] = []
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() == "---":
                        break
                    if re.match(r'^[A-Za-z0-9_-]+:\s*', lines[j]):
                        break
                    block.append(re.sub(r'^  ', '', lines[j]))
                fm[key] = ' '.join(block).strip()
            else:
                fm[key] = raw.strip().strip('"\'')
    return fm if fm else None


def walk_skills(root: Path, max_depth: int = 10) -> list[Path]:
    results: list[Path] = []
    seen: set[str] = set()

    def walk(current: Path, depth: int):
        if depth > max_depth:
            return
        try:
            real = str(current.resolve())
        except Exception:
            return
        if real in seen:
            return
        seen.add(real)
        try:
            entries = list(current.iterdir())
        except Exception:
            return
        for entry in entries:
            name = entry.name
            if name in ("node_modules", ".git", "__pycache__"):
                continue
            try:
                if entry.is_dir() or entry.is_symlink():
                    stat = entry.stat()
                    if stat.st_mode & 0o40000:  # is dir
                        walk(entry, depth + 1)
                elif entry.is_file() and name == "SKILL.md":
                    results.append(entry)
            except Exception:
                continue

    walk(root, 0)
    return results


def discover_skills(roots: list[Path]) -> list[Skill]:
    skills_by_realpath: dict[str, Skill] = {}
    for root in roots:
        for file in walk_skills(root):
            text = file.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if not fm:
                continue
            base_name = fm.get("name", file.parent.name)
            description = fm.get("description", "")
            scope = scope_for(root)
            skill = Skill(
                name=base_name,
                base_name=base_name,
                description=description,
                path=file,
                real_path=file.resolve(),
                root=root,
                real_root=root.resolve(),
                scope=scope,
                enabled=True,
            )
            existing = skills_by_realpath.get(str(skill.real_path))
            if existing:
                # Keep shorter path
                if len(str(file)) < len(str(existing.path)):
                    skills_by_realpath[str(skill.real_path)] = skill
            else:
                skills_by_realpath[str(skill.real_path)] = skill
    return list(skills_by_realpath.values())


def word_set(text: str) -> set[str]:
    words = re.sub(r"[`\"'’().,;:!?/\\\[\]{}_-]+", " ", text.lower()).split()
    return {w for w in words if len(w) >= 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def similarity(a: Skill, b: Skill) -> dict[str, float]:
    desc_sim = jaccard(word_set(a.description), word_set(b.description))
    body_sim = 1.0 if a.body_hash == b.body_hash else jaccard(word_set(a.body_key), word_set(b.body_key))
    return {
        "description": desc_sim,
        "body": body_sim,
        "overall": body_sim * 0.8 + desc_sim * 0.2,
    }


def delete_priority(skill: Skill) -> int:
    order = ["pi-project", "pi-global", "agents-project", "agents-global", "extra", "package"]
    try:
        return order.index(skill.scope)
    except ValueError:
        return 99


def preferred_keep(skills: list[Skill]) -> Skill:
    return sorted(skills, key=lambda s: (delete_priority(s), len(str(s.real_path)), str(s.real_path)))[0]


def is_likely_copy(score: dict[str, float]) -> bool:
    return score["body"] >= 0.95 or (score["body"] >= 0.85 and score["description"] >= 0.85)


def scan_usage(skills: list[Skill], months: int, no_logs: bool, max_log_mb: int) -> dict[str, dict[str, int]]:
    usage: dict[str, dict[str, int]] = {s.name: {"dollar": 0, "file_read": 0, "text": 0} for s in skills}
    if no_logs:
        return usage

    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 31)
    cutoff_ts = cutoff.timestamp()
    max_bytes = max_log_mb * 1024 * 1024
    consumed = 0

    log_files: list[Path] = []
    if PI_RUN_HISTORY.exists():
        log_files.append(PI_RUN_HISTORY)

    # Simple session scan: look for .jsonl files in ~/.pi/agent/ subdirs
    for subdir in PI_AGENT_DIR.iterdir():
        if subdir.is_dir():
            for f in subdir.rglob("*.jsonl"):
                try:
                    stat = f.stat()
                    if stat.st_mtime >= cutoff_ts and stat.st_size <= 150 * 1024 * 1024:
                        log_files.append(f)
                except Exception:
                    continue

    # Build aliases for matching
    aliases: dict[str, list[str]] = {}
    for skill in skills:
        names = {skill.name, skill.base_name, skill.name.split(":")[-1]}
        aliases[skill.name] = [n.lower() for n in names]

    for log_file in log_files:
        try:
            size = log_file.stat().st_size
            if consumed + size > max_bytes:
                break
            consumed += size
            text = log_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Count $skill mentions
        dollar_counts = Counter(
            m.group(1).lower()
            for m in re.finditer(r'\$([A-Za-z][A-Za-z0-9_.:-]{1,80})', text)
        )
        # Count skill file reads
        path_counts = Counter(
            m.group(1).lower()
            for m in re.finditer(r'(?:^|[/"\'`\\])(?:\.agents/)?skills/([^/"\'`\\\s]+)/SKILL\.md', text)
        )
        # Count use/read/load mentions
        text_counts = Counter(
            m.group(1).lower()
            for m in re.finditer(r'\b(?:use|using|load|read)\s+`?\$?([A-Za-z][A-Za-z0-9_.:-]{1,80})`?', text, re.IGNORECASE)
        )

        for name, names in aliases.items():
            for candidate in names:
                usage[name]["dollar"] += dollar_counts.get(candidate, 0)
                usage[name]["file_read"] += path_counts.get(candidate, 0)
                usage[name]["text"] += text_counts.get(candidate, 0)

    return usage


def token_cost(text: str) -> int:
    return (len(text.encode("utf-8")) + 3) // 4  # ceil(utf8_bytes / 4)


def line_token_cost(skill: Skill, description: str = "") -> int:
    line = skill.rendered_line(description)
    return token_cost(line + "\n")


def extra_description_costs(skill: Skill) -> list[int]:
    min_line = skill.rendered_line("")
    min_bytes = len((min_line + "\n").encode("utf-8"))
    min_cost = (min_bytes + 3) // 4
    costs = [0]
    prefix_bytes = 0
    for char in skill.description:
        prefix_bytes += len(char.encode("utf-8"))
        rendered_bytes = min_bytes + prefix_bytes + 1
        costs.append((rendered_bytes + 3) // 4 - min_cost)
    return costs


def skill_order_rank(skill: Skill) -> int:
    if skill.scope in ("pi-project", "agents-project"):
        return 0
    if skill.scope in ("pi-global", "agents-global"):
        return 1
    if skill.scope == "extra":
        return 2
    return 3


def ordered_skills(skills: list[Skill]) -> list[Skill]:
    return sorted(skills, key=lambda s: (skill_order_rank(s), s.name, str(s.path)))


def compute_budget(skills: list[Skill], model: str, context_tokens: int, budget_percent: float) -> Budget:
    budget_tokens = int(context_tokens * budget_percent / 100)
    ordered = ordered_skills(skills)

    full_tokens = sum(line_token_cost(s, s.description) for s in ordered)
    min_tokens = sum(line_token_cost(s, "") for s in ordered)

    if full_tokens <= budget_tokens:
        return Budget(
            model=model,
            context_tokens=context_tokens,
            context_source="models.json",
            budget_percent=budget_percent,
            budget_tokens=budget_tokens,
            rendered_line_chars=sum(s.line_chars for s in skills),
            unbudgeted_full_tokens=full_tokens,
            minimum_tokens=min_tokens,
            budgeted_tokens=full_tokens,
            included_skills=len(ordered),
            omitted_skills=0,
            truncated_description_chars=0,
            truncated_description_count=0,
        )

    if min_tokens <= budget_tokens:
        remaining = budget_tokens - min_tokens
        allocated = [0] * len(ordered)
        current_extra = [0] * len(ordered)
        extra_costs = [extra_description_costs(s) for s in ordered]
        desc_lens = [len(s.description) for s in ordered]

        while True:
            changed = False
            for i in range(len(ordered)):
                if allocated[i] >= desc_lens[i]:
                    continue
                next_chars = allocated[i] + 1
                next_cost = extra_costs[i][next_chars] if next_chars < len(extra_costs[i]) else current_extra[i]
                delta = next_cost - current_extra[i]
                if delta <= remaining:
                    allocated[i] = next_chars
                    current_extra[i] = next_cost
                    remaining -= delta
                    changed = True
            if not changed:
                break

        rendered = [
            ordered[i].rendered_line(ordered[i].description[:allocated[i]])
            for i in range(len(ordered))
        ]
        budgeted_tokens = sum(token_cost(line + "\n") for line in rendered)
        truncated_chars = sum(max(0, desc_lens[i] - allocated[i]) for i in range(len(ordered)))
        truncated_count = sum(1 for i in range(len(ordered)) if allocated[i] < desc_lens[i])
        return Budget(
            model=model,
            context_tokens=context_tokens,
            context_source="models.json",
            budget_percent=budget_percent,
            budget_tokens=budget_tokens,
            rendered_line_chars=sum(s.line_chars for s in skills),
            unbudgeted_full_tokens=full_tokens,
            minimum_tokens=min_tokens,
            budgeted_tokens=budgeted_tokens,
            included_skills=len(ordered),
            omitted_skills=0,
            truncated_description_chars=truncated_chars,
            truncated_description_count=truncated_count,
        )

    # Must omit skills
    budgeted = 0
    included = 0
    omitted = 0
    for s in ordered:
        cost = line_token_cost(s, "")
        if budgeted + cost <= budget_tokens:
            budgeted += cost
            included += 1
        else:
            omitted += 1

    return Budget(
        model=model,
        context_tokens=context_tokens,
        context_source="models.json",
        budget_percent=budget_percent,
        budget_tokens=budget_tokens,
        rendered_line_chars=sum(s.line_chars for s in skills),
        unbudgeted_full_tokens=full_tokens,
        minimum_tokens=min_tokens,
        budgeted_tokens=budgeted,
        included_skills=included,
        omitted_skills=omitted,
        truncated_description_chars=sum(len(s.description) for s in ordered[included:]),
        truncated_description_count=sum(1 for s in ordered[included:] if s.description),
    )


def suggest_description(skill: Skill) -> str:
    source = skill.base_name.replace("-", " ") + " " + skill.description
    source = source.lower()
    cues: list[str] = []
    cues_map = {
        "OpenClaw": r"\bopenclaw|claw|clawd\b",
        "GitHub": r"\b(github|issue|pr|ci)\b|pull request",
        "Slack": r"\bslack\b",
        "Discord": r"\bdiscord\b",
        "Gmail": r"\bgmail|email\b",
        "Google": r"\b(google|drive|calendar|docs|sheets|slides)\b",
        "Cloudflare": r"\b(cloudflare|worker|wrangler)\b|durable object",
        "release": r"\b(release|publish|ship|notar)\b",
        "debug": r"\b(debug|trace|inspect|profile|diagnos)\b",
        "search": r"\b(search|archive|crawl|sync|history)\b",
        "deploy": r"\b(deploy|ops|server|ssh|vm)\b",
        "docs": r"\b(doc|docs|markdown|write|review)\b",
        "frontend": r"\b(ui|frontend|interface|design|css|html|react|vue)\b",
        "test": r"\b(test|spec|jest|pytest|tdd)\b",
        "Notion": r"\bnotion\b",
    }
    for label, pattern in cues_map.items():
        if re.search(pattern, source) and label not in cues:
            cues.append(label)
    verbs = ", ".join(cues[:5]) if cues else skill.base_name.replace("-", " ")
    if re.search(r"\btriage|review\b", source):
        action = "triage, review, proof"
    elif re.search(r"\bdebug|diagnos|inspect\b", source):
        action = "debug, inspect, fix"
    elif re.search(r"\bsearch|sync|archive\b", source):
        action = "search, sync, summarize"
    elif re.search(r"\bdeploy|release|publish|ship\b", source):
        action = "deploy, release, verify"
    elif re.search(r"\bcreate|scaffold|build\b", source):
        action = "create, build, validate"
    elif re.search(r"\btest|spec|jest|pytest\b", source):
        action = "test, validate, verify"
    else:
        action = "audit, clean, verify"
    return f"{verbs}: {action}."


def format_pct(value: float) -> str:
    return f"{round(value * 100)}%"


def format_one_pct(value: float) -> str:
    return f"{(value * 100):.1f}%"


def format_num(value: int) -> str:
    return f"{value:,}"


def render_report(
    skills: list[Skill],
    usage: dict[str, dict[str, int]],
    budget: Budget,
    months: int,
) -> str:
    enabled = [s for s in skills if s.enabled]
    by_name: dict[str, list[Skill]] = {}
    for s in enabled:
        by_name.setdefault(s.base_name.lower(), []).append(s)
    by_name = {k: v for k, v in by_name.items() if len(v) > 1}

    by_body: dict[str, list[Skill]] = {}
    for s in enabled:
        by_body.setdefault(s.body_hash, []).append(s)
    by_body = {k: v for k, v in by_body.items() if len(v) > 1 and k != "0" * 16}

    long_descs = sorted(
        [s for s in enabled if s.desc_chars >= 110 or s.line_chars >= 180],
        key=lambda s: s.desc_chars,
        reverse=True,
    )[:30]

    unused = sorted(
        [s for s in enabled if not any(usage.get(s.name, {}).values()) and s.scope not in ("package",)],
        key=lambda s: (s.scope, s.name),
    )[:80]

    roots: dict[Path, list[Skill]] = {}
    for s in skills:
        roots.setdefault(s.root, []).append(s)

    lines: list[str] = [
        "# Pi Skill Cleaner Report",
        "",
        f"generated: {datetime.now(timezone.utc).isoformat()}",
        f"months: {months}",
        f"skills: {len(skills)} discovered, {len(enabled)} considered",
        f"description_chars: {sum(s.desc_chars for s in enabled)}",
        f"rendered_line_chars: {sum(s.line_chars for s in enabled)}",
        "",
        "## Skill Budget",
        "",
        f"model: {budget.model}",
        f"context_tokens: {format_num(budget.context_tokens)}",
        f"context_source: {budget.context_source}",
        f"{budget.budget_percent:g}%_budget_tokens: {format_num(budget.budget_tokens)}",
        f"cost_rule: ceil(utf8_bytes / {CHARS_PER_TOKEN})",
        f"unbudgeted_full_tokens: {format_num(budget.unbudgeted_full_tokens)}",
        f"minimum_no_description_tokens: {format_num(budget.minimum_tokens)}",
        f"budgeted_tokens_used: {format_num(budget.budgeted_tokens)}",
        f"used_of_{budget.budget_percent:g}%_budget: {format_one_pct(budget.budgeted_tokens / budget.budget_tokens)}",
        f"unbudgeted_used_of_{budget.budget_percent:g}%_budget: {format_one_pct(budget.unbudgeted_full_tokens / budget.budget_tokens)}",
        f"used_of_context: {format_one_pct(budget.budgeted_tokens / budget.context_tokens)}",
        f"remaining_{budget.budget_percent:g}%_budget_tokens: {format_num(budget.budget_tokens - budget.budgeted_tokens)}",
        f"included_skills_after_budget: {budget.included_skills}",
        f"omitted_skills_after_budget: {budget.omitted_skills}",
        f"truncated_description_chars: {format_num(budget.truncated_description_chars)}",
        "",
        "## Description Candidates",
        "",
    ]

    for s in long_descs:
        lines.extend([
            f"- {s.name}",
            f"  path: {s.path}",
            f"  chars: description={s.desc_chars}, rendered_line={s.line_chars}",
            f"  current: {s.description}",
            f"  suggested: {suggest_description(s)}",
        ])
    if not long_descs:
        lines.append("- none")
    lines.append("")

    lines.extend(["## Duplicates By Name", ""])
    for name, group in list(by_name.items())[:40]:
        lines.append(f"- {name}")
        keep = preferred_keep(group)
        lines.append(f"  keep-default: {keep.scope}: {keep.path}")
        for s in group:
            if s.real_path == keep.real_path:
                score = {"body": 1.0, "description": 1.0}
            else:
                score = similarity(keep, s)
            lines.append(f"  - {s.scope}: {s.path} (body={format_pct(score['body'])}, description={format_pct(score['description'])})")
    if not by_name:
        lines.append("- none")
    lines.append("")

    lines.extend(["## Duplicate Delete Suggestions", ""])
    suggestions: list[str] = []
    for name, group in list(by_name.items())[:80]:
        keep = preferred_keep(group)
        candidates = [
            (s, similarity(keep, s)) for s in group
            if s.real_path != keep.real_path
        ]
        candidates = [(s, sc) for s, sc in candidates if is_likely_copy(sc)]
        candidates.sort(key=lambda x: (-x[1]["body"], -x[1]["description"]))
        if not candidates:
            continue
        suggestions.append(f"- {name}")
        suggestions.append(f"  keep: {keep.scope}: {keep.path}")
        for s, sc in candidates:
            suggestions.append(f"  delete: {s.scope}: {s.path} (similarity body={format_pct(sc['body'])}, description={format_pct(sc['description'])})")
    if suggestions:
        lines.extend(suggestions)
    else:
        lines.append("- none")
    lines.append("")

    lines.extend(["## Duplicates By Body Hash", ""])
    for h, group in list(by_body.items())[:30]:
        names = ", ".join(s.name for s in group)
        lines.append(f"- {names}")
        for s in group:
            lines.append(f"  - {s.scope}: {s.path}")
    if not by_body:
        lines.append("- none")
    lines.append("")

    lines.extend(["## Unused Candidates", ""])
    for s in unused:
        u = usage.get(s.name, {"dollar": 0, "file_read": 0, "text": 0})
        lines.append(f"- {s.name}: {s.scope}; usage=${u['dollar']}, reads={u['file_read']}, text={u['text']}; {s.path}")
    if not unused:
        lines.append("- none")
    lines.append("")

    lines.extend(["## Root Summary", ""])
    for root, group in sorted(roots.items(), key=lambda x: -len(x[1])):
        disabled = sum(1 for s in group if not s.enabled)
        lines.append(f"- {root}: {len(group)} skills{f', {disabled} disabled' if disabled else ''}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    model = args.model or get_default_model()
    context_tokens, context_source = get_model_context(model, args.context_tokens)

    roots = discover_roots(args.root)
    skills = discover_skills(roots)
    usage = scan_usage(skills, args.months, args.no_logs, args.max_log_mb)
    enabled = [s for s in skills if s.enabled]
    budget = compute_budget(enabled, model, context_tokens, args.budget_percent)
    budget.context_source = context_source

    if args.json:
        output = {
            "skills": [
                {
                    "name": s.name,
                    "base_name": s.base_name,
                    "description": s.description,
                    "path": str(s.path),
                    "real_path": str(s.real_path),
                    "root": str(s.root),
                    "scope": s.scope,
                    "enabled": s.enabled,
                    "desc_chars": s.desc_chars,
                    "line_chars": s.line_chars,
                    "body_hash": s.body_hash,
                }
                for s in skills
            ],
            "usage": usage,
            "budget": {
                "model": budget.model,
                "context_tokens": budget.context_tokens,
                "context_source": budget.context_source,
                "budget_percent": budget.budget_percent,
                "budget_tokens": budget.budget_tokens,
                "unbudgeted_full_tokens": budget.unbudgeted_full_tokens,
                "minimum_tokens": budget.minimum_tokens,
                "budgeted_tokens": budget.budgeted_tokens,
                "included_skills": budget.included_skills,
                "omitted_skills": budget.omitted_skills,
                "truncated_description_chars": budget.truncated_description_chars,
                "truncated_description_count": budget.truncated_description_count,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(render_report(skills, usage, budget, args.months))

    return 0


if __name__ == "__main__":
    sys.exit(main())
