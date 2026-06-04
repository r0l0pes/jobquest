"""Skill gap analysis and learning plan generator.

Analyzes tracked job applications against the candidate profile to identify
skill gaps, build a priority-graded heatmap, and generate a learning plan.

Modes:
- Aggregate: Analyze all tracked applications from data/applications.json
- Targeted: Analyze a single job posting by URL

Usage:
    from modules.upskill import run_upskill
    report = run_upskill()  # aggregate mode
"""

import json
import re
import os
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
APPLICATIONS_PATH = PROJECT_ROOT / "data" / "applications.json"
UPSKILL_DIR = PROJECT_ROOT / "upskill"


def _load_applications() -> list[dict]:
    """Load tracked applications from data/applications.json."""
    if not APPLICATIONS_PATH.exists():
        return []
    try:
        with open(APPLICATIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("applications", data.get("entries", []))
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _load_profile_text() -> str:
    """Load candidate profile text from prompts/ or master resume cache.

    Reads available profile/prompt files to build a corpus of known skills.
    """
    texts = []

    # Try prompts directory
    prompts_dir = PROJECT_ROOT / "prompts"
    for fname in ["behavioral_profile.md", "rodrigo-voice-lite.md"]:
        fpath = prompts_dir / fname
        if fpath.exists():
            texts.append(fpath.read_text())

    # Try master resume cache files
    for fpath in PROJECT_ROOT.glob(".master_resume_cache_*.txt"):
        texts.append(fpath.read_text())

    return "\n\n".join(texts)


def _extract_skills_from_text(text: str) -> set[str]:
    """Extract skill-like terms from text using heuristics.

    Captures: bullet-pointed items, capitalized technical terms,
    tool names, and domain keywords.
    """
    skills = set()

    # Lines starting with - or * (bullet points)
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            item = line.lstrip("-* ").strip()
            # Filter for meaningful skill-like terms
            if len(item) > 2 and not item.startswith(("[", "(")):
                skills.add(item.lower())

    # Known skill patterns (camelCase, tool names, technologies)
    tech_patterns = re.findall(
        r'\b(?:Python|JavaScript|TypeScript|React|Vue|Angular|Node\.js|Django|Flask|'
        r'SQL|NoSQL|MongoDB|PostgreSQL|Redis|Docker|Kubernetes|AWS|GCP|Azure|'
        r'TensorFlow|PyTorch|LLM|NLP|ML|AI|CI/CD|Git|Agile|Scrum|Jira|Figma|'
        r'REST|GraphQL|API|SaaS|B2B|B2C|PLG|A/B|SQL|ETL|Growth|Product|'
        r'Experimentation|Analytics|Data|Leadership|Strategy|Roadmap)\b',
        text,
        re.IGNORECASE,
    )
    skills.update(t.lower() for t in tech_patterns)

    return skills


def _extract_skills_from_job(job: dict) -> dict:
    """Extract skills mentioned in a job entry.

    Returns dict with: all_skills (set), required_skills (set), preferred_skills (set).
    """
    all_skills = set()
    required = set()

    # Extract from notes field
    notes = job.get("notes", "") or ""
    all_skills.update(_extract_skills_from_text(notes))

    # Extract from role title
    role = job.get("role", "") or ""
    role_skills = _extract_skills_from_text(role)
    required.update(role_skills)
    all_skills.update(role_skills)

    # Extract from sector/company description
    sector = job.get("sector", "") or ""
    all_skills.update(_extract_skills_from_text(sector))

    # Company name
    company = job.get("company", "") or ""
    all_skills.update(_extract_skills_from_text(company))

    return {
        "all_skills": all_skills,
        "required_skills": required,
    }


def _hard_skill_diff(applications: list[dict], profile_text: str) -> list[dict]:
    """Pass 1: Hard skill diff — compare required skills against profile.

    Builds a weighted frequency map of skills mentioned across all tracked
    applications, weighted by fit score (lower fit = higher gap weight
    because the role exposed more gaps).

    Returns list of {skill, score, count, type} sorted descending by score.
    """
    profile_skills = _extract_skills_from_text(profile_text)
    skill_freq: dict[str, dict] = {}

    for app in applications:
        fit_score = app.get("fit_score", app.get("score", 50))
        if isinstance(fit_score, str):
            try:
                fit_score = int(fit_score)
            except (ValueError, TypeError):
                fit_score = 50
        if fit_score is None or fit_score == 0:
            fit_score = 50

        job_skills = _extract_skills_from_job(app)
        gap_weight = max(0.1, (100 - fit_score) / 100)

        for skill in job_skills["all_skills"]:
            if skill in profile_skills:
                continue  # Already have this skill

            if skill not in skill_freq:
                skill_freq[skill] = {"skill": skill, "score": 0.0, "count": 0, "type": "Hard"}
            skill_freq[skill]["score"] += gap_weight
            skill_freq[skill]["count"] += 1

    # Sort by score descending
    gaps = sorted(skill_freq.values(), key=lambda x: x["score"], reverse=True)
    return gaps


def _llm_synthesize_gaps(hard_gaps: list[dict], applications: list[dict]) -> list[dict]:
    """Pass 2: LLM synthesis for gaps not caught by hard skill diff.

    Uses Gemini Flash-Lite to identify domain knowledge, soft skills,
    tooling/process gaps that keyword matching misses.

    Falls back to a rule-based approach if LLM is unavailable.
    """
    # Try using LLM for synthesis
    try:
        from modules.llm_client import create_client

        apps_summary = f"Analyzed {len(applications)} job applications, {len(hard_gaps)} hard skill gaps found."
        hard_gap_names = ", ".join(g["skill"] for g in hard_gaps[:10])

        client = create_client("gemini", "gemini-3.1-flash-lite")
        system = "You are a career gap analysis tool. Identify skill gaps from job application data that keyword matching would miss."
        user = (
            f"{apps_summary}\n\n"
            f"Hard skill gaps found: {hard_gap_names}\n\n"
            f"Based on these {len(applications)} tracked applications, what domain knowledge, "
            f"soft skills, or tooling/process gaps might exist? "
            f"Return your answer as a JSON array of objects with keys: skill, type (Domain/Soft/Tooling), reason."
        )

        response = client.generate(system, user, temperature=0.2)
        try:
            # Try to parse JSON from response
            match = re.search(r"\[.*?\]", response, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except (json.JSONDecodeError, AttributeError):
            pass
    except Exception:
        pass

    # Fallback: rule-based synthesis from applications
    synthesized = []
    all_sectors = set()
    for app in applications:
        sector = app.get("sector", "") or ""
        if sector:
            all_sectors.add(sector.lower())

    domain_keywords = {
        "fintech": "Financial services / fintech domain knowledge",
        "healthcare": "Healthcare / health-tech domain knowledge",
        "saas": "SaaS business model knowledge",
        "marketplace": "Multi-sided marketplace dynamics",
        "enterprise": "Enterprise sales / B2B sales cycles",
    }

    for sector in all_sectors:
        for keyword, description in domain_keywords.items():
            if keyword in sector:
                exists = any(g["skill"] == description for g in hard_gaps)
                if not exists:
                    synthesized.append({
                        "skill": description,
                        "type": "Domain",
                        "reason": f"Jobs in {sector} sector suggest need for {description}",
                    })

    return synthesized


def _build_heatmap(all_gaps: list[dict]) -> list[dict]:
    """Pass 3: Build priority heatmap from combined gaps.

    Priority tiers:
    - Critical: score >= 5 or 3+ job mentions
    - High: score >= 2 or 2+ job mentions
    - Medium: everything else
    """
    heatmap = []
    for gap in all_gaps:
        score = gap.get("score", 1)
        count = gap.get("count", 0)
        skill = gap.get("skill", "")
        gtype = gap.get("type", "Hard")

        if score >= 5 or count >= 3:
            priority = "Critical"
        elif score >= 2 or count >= 2:
            priority = "High"
        else:
            priority = "Medium"

        heatmap.append({
            "priority": priority,
            "skill": skill,
            "type": gtype,
            "score": round(score, 1),
            "count": count,
            "source": f"{count} jobs, score {score:.1f}" if count > 0 else "LLM synthesis",
        })

    # Sort by priority then score
    priority_order = {"Critical": 0, "High": 1, "Medium": 2}
    heatmap.sort(key=lambda x: (priority_order.get(x["priority"], 99), -x["score"]))
    return heatmap


def _generate_learning_plan(heatmap: list[dict]) -> list[dict]:
    """Pass 4-5: Generate learning plan with study direction and estimated time.

    For Critical + High gaps, provides study direction and time estimate.
    Returns dependency-ordered sequence.
    """
    plan = []
    for item in heatmap:
        if item["priority"] not in ("Critical", "High"):
            continue

        skill = item["skill"]
        gtype = item["type"]

        if gtype == "Hard":
            time_est = "15-20h"
            direction = f"Focus on hands-on practice with {skill}. Look for project-based tutorials and real-world applications."
        elif gtype == "Domain":
            time_est = "5-10h"
            direction = f"Read industry reports and case studies on {skill}. Focus on key concepts and terminology."
        elif gtype == "Soft":
            time_est = "3-5h"
            direction = f"Practice through mock interviews and peer review. Focus on articulating {skill} with concrete examples."
        elif gtype == "Tooling":
            time_est = "10-15h"
            direction = f"Set up a practice environment and work through common workflows for {skill}."
        else:
            time_est = "8-12h"
            direction = f"Research {skill} fundamentals and apply through a small project."

        plan.append({
            "skill": skill,
            "priority": item["priority"],
            "type": gtype,
            "estimated_time": time_est,
            "study_direction": direction,
        })

    return plan


def _save_report(heatmap: list[dict], plan: list[dict], targeted: bool = False) -> Path:
    """Save the upskill report to upskill/report-YYYY-MM-DD.md.

    Returns the path to the saved report.
    """
    UPSKILL_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    report_path = UPSKILL_DIR / f"report-{today}.md"

    # Check for previous report
    previous_reports = sorted(UPSKILL_DIR.glob("report-*.md"))
    previous_text = ""
    if previous_reports:
        prev = previous_reports[-1]
        if prev != report_path:
            previous_text = prev.read_text()

    lines = []
    lines.append(f"# Upskill Report — {today}")
    lines.append("")

    if targeted:
        lines.append("**Mode:** Targeted (single job analysis)")
    else:
        apps_count = len(_load_applications())
        lines.append(f"**Mode:** Aggregate ({apps_count} jobs analyzed)")
    lines.append("")

    # Diff section
    if previous_text:
        # Extract gap names from previous report
        prev_gaps = set()
        for line in previous_text.split("\n"):
            m = re.match(r"^\|\s*\|?\s*(Critical|High|Medium)", line)
            if m:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    prev_gaps.add(parts[1].lower())

        current_gaps = set(item["skill"].lower() for item in heatmap)
        closed_gaps = prev_gaps - current_gaps
        new_gaps = current_gaps - prev_gaps

        lines.append("## Since Last Report")
        if closed_gaps:
            for g in sorted(closed_gaps):
                lines.append(f"- **Closed:** {g.title()}")
        else:
            lines.append("- **Gaps closed:** (none)")
        if new_gaps:
            for g in sorted(new_gaps):
                lines.append(f"- **New:** {g.title()}")
        else:
            lines.append("- **New gaps:** (none)")
        lines.append("")
    else:
        lines.append("## Since Last Report")
        lines.append("- **Gaps closed:** (none — first run)")
        lines.append("- **New gaps:** (all identified gaps)")
        lines.append("")

    # Heatmap
    lines.append("## Gap Heatmap")
    lines.append("")
    lines.append("| Priority | Skill / Area | Type | Source |")
    lines.append("|----------|-------------|------|--------|")
    for item in heatmap:
        lines.append(f"| {item['priority']} | {item['skill'].title()} | {item['type']} | {item['source']} |")
    lines.append("")

    # Learning plan
    if plan:
        lines.append("## Learning Plan")
        lines.append("")
        for item in plan:
            lines.append(f"### {item['skill'].title()} `[{item['type']}]`")
            lines.append(f"- **Priority:** {item['priority']}")
            lines.append(f"- **Estimated time:** {item['estimated_time']}")
            lines.append(f"- **Study direction:** {item['study_direction']}")
            lines.append("")

        # Study order
        lines.append("## Suggested Study Order")
        lines.append("")
        lines.append("| # | Topic | Type | Est. Time |")
        lines.append("|---|-------|------|-----------|")
        for i, item in enumerate(plan, 1):
            lines.append(f"| {i} | {item['skill'].title()} | {item['type']} | {item['estimated_time']} |")

        total_time = sum(
            int(re.search(r"(\d+)", item["estimated_time"]).group(1))
            for item in plan
            if re.search(r"(\d+)", item["estimated_time"])
        )
        lines.append("")
        lines.append(f"**Total estimated time: ~{total_time}h**")
        lines.append("")

    # Save
    report_path.write_text("\n".join(lines))
    return report_path


def run_upskill(target_url: str | None = None) -> dict:
    """Main entry point for upskill analysis.

    Args:
        target_url: Optional URL for targeted mode. If None, runs aggregate mode.

    Returns:
        Dict with: ok, report_path, heatmap (list), plan (list), message (str)
    """
    applications = _load_applications()

    if not applications:
        return {
            "ok": True,
            "report_path": None,
            "heatmap": [],
            "plan": [],
            "message": "No applications tracked yet. Run the pipeline on some jobs first.",
        }

    if target_url:
        applications = [a for a in applications if target_url in str(a.get("url", ""))]
        if not applications:
            return {
                "ok": True,
                "report_path": None,
                "heatmap": [],
                "plan": [],
                "message": f"No tracked application matching URL: {target_url}",
            }

    profile_text = _load_profile_text()

    # Pass 1: Hard skill diff
    hard_gaps = _hard_skill_diff(applications, profile_text)

    # Pass 2: LLM synthesis
    soft_gaps = _llm_synthesize_gaps(hard_gaps, applications)

    # Combine
    all_gaps = []
    for g in hard_gaps:
        all_gaps.append({"skill": g["skill"], "score": g["score"], "count": g.get("count", 1), "type": "Hard"})
    for g in soft_gaps:
        # Deduplicate by skill name
        if not any(existing["skill"].lower() == g.get("skill", "").lower() for existing in all_gaps):
            all_gaps.append({
                "skill": g.get("skill", ""),
                "score": 1.0,
                "count": 1,
                "type": g.get("type", "Domain"),
            })

    # Pass 3: Build heatmap
    heatmap = _build_heatmap(all_gaps)

    # Pass 4: Learning plan
    plan = _generate_learning_plan(heatmap)

    # Pass 5: Save report
    report_path = _save_report(heatmap, plan, targeted=bool(target_url))

    return {
        "ok": True,
        "report_path": str(report_path),
        "heatmap": heatmap,
        "plan": plan,
        "message": f"Report saved to {report_path}",
    }
