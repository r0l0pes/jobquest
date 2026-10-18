"""Parsers for extracting structured content from LLM text responses.

Each parser uses multiple fallback strategies because LLM output
formatting is unpredictable even with explicit instructions.
"""

import re
import json
from collections.abc import Sequence


def fix_markdown_lists(tex: str) -> str:
    """Fix bare '- item' lines under \\section* headings into proper LaTeX itemize.

    The LLM sometimes forgets to wrap Certifications / Languages / Education
    in \\begin{itemize}...\\end{itemize} and uses markdown-style '- item' instead.
    Those dashes render as inline text in LaTeX, causing all items to merge into
    one paragraph. This function converts them to proper LaTeX bullet lists.
    """

    def convert_block(match):
        pre = match.group(1)       # \\section*{...} + optional \\vspace line
        items_raw = match.group(2)  # the "- item" lines
        items = re.sub(r"^- ", r"\\item ", items_raw.strip(), flags=re.MULTILINE)
        return (
            pre + "\n"
            r"\begin{itemize}[leftmargin=*, label=$\bullet$, itemsep=2pt, parsep=0pt]"
            "\n" + items + "\n"
            r"\end{itemize}"
        )

    pattern = re.compile(
        r"(\\section\*\{[^}]+\}(?:\s*\n\\vspace\{[^}]+\})?)"  # section + optional vspace
        r"\s*\n"                                                  # newline
        r"((?:^- .+$\n?)+)",                                     # one or more "- item" lines
        re.MULTILINE,
    )
    return pattern.sub(convert_block, tex)


def extract_latex(text: str) -> str | None:
    """Extract LaTeX content from LLM response.

    Strategies (in order):
    0. Strip <think>...</think> blocks (DeepSeek reasoning models)
    1. ```latex ... ``` code block
    2. ```tex ... ``` code block
    3. Any ``` ... ``` block containing \\documentclass
    4. Raw \\documentclass ... \\end{document} substring
    """
    # Strategy 0: Strip DeepSeek thinking tokens before parsing
    # These can contain partial code/LaTeX that confuses later patterns
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Strategy 1 & 2: language-tagged code blocks
    # Flexible: allow optional whitespace/newline after language tag
    for lang in ["latex", "tex"]:
        pattern = rf"```{lang}\s*(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            content = match.group(1).strip()
            if "\\documentclass" in content:
                return content

    # Strategy 3: untagged code block with LaTeX content
    pattern = r"```\s*(.*?)```"
    for match in re.finditer(pattern, text, re.DOTALL):
        content = match.group(1).strip()
        if "\\documentclass" in content:
            return content

    # Strategy 4: raw LaTeX markers
    start = text.find("\\documentclass")
    end = text.rfind("\\end{document}")
    if start != -1 and end != -1:
        return text[start : end + len("\\end{document}")].strip()

    # Strategy 5: truncated response — model was cut off mid-generation.
    # If we find an opening ```latex or \documentclass but no closing marker,
    # return what we have. pdflatex will catch structural errors; this avoids
    # a silent failure that discards a mostly-complete resume.
    for lang in ["latex", "tex"]:
        match = re.search(rf"```{lang}\s*(.*)", text, re.DOTALL)
        if match:
            fragment = match.group(1).strip()
            if "\\documentclass" in fragment:
                # Append \end{document} if missing so pdflatex can attempt compilation
                if "\\end{document}" not in fragment:
                    fragment += "\n\\end{document}"
                return fragment

    if "\\documentclass" in text:
        start = text.find("\\documentclass")
        fragment = text[start:].strip()
        if "\\end{document}" not in fragment:
            fragment += "\n\\end{document}"
        return fragment

    return None


def parse_ats_report(text: str) -> dict:
    """Extract ATS report (JSON + Markdown) from LLM response.

    Returns dict with keys: "json" (dict|None), "markdown" (str|None)
    """
    result = {"json": None, "markdown": None}

    # Strip DeepSeek thinking tokens before parsing
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # --- Extract JSON ---
    json_match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if json_match:
        raw = json_match.group(1).strip()
        result["json"] = _safe_parse_json(raw)

    # Fallback: try entire response as JSON
    if result["json"] is None:
        result["json"] = _safe_parse_json(text.strip())

    # --- Extract Markdown ---
    md_match = re.search(r"```markdown\s*(.*?)```", text, re.DOTALL)
    if md_match:
        result["markdown"] = md_match.group(1).strip()
    else:
        # Look for # ATS Check header
        ats_header = re.search(r"(# ATS Check.*)", text, re.DOTALL)
        if ats_header:
            # Stop at a JSON block if present
            md_text = ats_header.group(1)
            json_start = md_text.find("```json")
            if json_start > 0:
                md_text = md_text[:json_start]
            result["markdown"] = md_text.strip()

    # Construct minimal markdown from JSON if needed
    if result["json"] and not result["markdown"]:
        j = result["json"]
        score = j.get("coverage_score", {})
        result["markdown"] = (
            f"# ATS Check: {j.get('company', '?')} - "
            f"{j.get('job_title', '?')}\n\n"
            f"Coverage: {score.get('coverage_pct', '?')}%\n"
            f"Verdict: {score.get('verdict', '?')}\n"
        )

    return result


def parse_qa_answers(text: str) -> list[dict]:
    """Extract question/answer pairs from LLM response.

    Strategies:
    1. ### Q: / ### A: header pattern
    2. Simpler Q: / A: prefix pattern
    3. Numbered sections split by ---
    """
    # Strip DeepSeek thinking tokens before parsing
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Strategy 1: markdown headers
    pattern = re.compile(
        r"###?\s*Q(?:uestion)?[:\s]+(.+?)(?:\n+)"
        r"###?\s*A(?:nswer)?[:\s]+(.+?)(?=\n---|\n###?\s*Q|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    pairs = _extract_pairs(pattern, text)
    if pairs:
        return pairs

    # Strategy 2: simple prefixes
    pattern = re.compile(
        r"(?:^|\n)Q[:\s]+(.+?)(?:\n+)A[:\s]+(.+?)(?=\nQ[:\s]|\n---|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    pairs = _extract_pairs(pattern, text)
    if pairs:
        return pairs

    # Strategy 3: split on --- separators
    pairs = []
    sections = text.split("---")
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.split("\n", 1)
        if len(lines) == 2:
            q = re.sub(r"^[\d#.*]+\s*", "", lines[0]).strip()
            a = lines[1].strip()
            if q and a and len(a) > 20:
                pairs.append({"question": q, "answer": a})

    return pairs


# --- Helpers ---


def _safe_parse_json(raw: str) -> dict | None:
    """Try to parse JSON with common LLM-error fixups."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    # Fix trailing commas before } or ]
    fixed = re.sub(r",\s*([}\]])", r"\1", raw)
    try:
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_pairs(pattern: re.Pattern, text: str) -> list[dict]:
    """Extract Q/A pairs using a compiled regex pattern."""
    matches = pattern.findall(text)
    if not matches:
        return []
    return [
        {"question": q.strip(), "answer": a.strip()}
        for q, a in matches
    ]


# ─── Targeted resume edit helpers ────────────────────────────────────────────

def parse_resume_edits(text: str) -> dict | None:
    """Extract targeted edits JSON from LLM response.

    Returns dict with keys: tagline, summary_bullet, postscript_bullets, skills.
    Returns None if no valid JSON found.
    """
    # Strip think tokens
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
        if "postscript_bullets" in data or "summary_bullet" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting first JSON object from mixed response
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if "postscript_bullets" in data or "summary_bullet" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    # Order matters: backslash first
    text = text.replace("\\", r"\textbackslash{}")
    for char, repl in [
        ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
        ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
        ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
    ]:
        text = text.replace(char, repl)
    return text


def escape_latex_text(text: str) -> str:
    """Escape plain text for safe inclusion in LaTeX.

    Public wrapper used by the cover-letter template substitution, where a job
    title such as "Senior Product Manager - Traffic & Acquisition" previously
    injected a raw ``&`` and made pdflatex fail with "Misplaced alignment tab
    character".
    """
    return _escape_latex(text)


def _normalise_fact_text(text: str) -> str:
    """Normalise plain text or LaTeX fragments for factual checks."""
    return text.replace("\\", "").lower().replace("–", "-")


# ── Novel-claim grounding (Live Pilot Hotfix H1) ──────────────────
#
# Candidate truth comes from candidate-controlled canonical evidence. The job
# description is a statement of what the EMPLOYER wants, not proof of what the
# candidate did, and no model stage (brief, reviewer, ATS) may certify its own
# inserted claim. The Clickboat pilot produced a resume asserting Postscript
# work on "technical optimization of LLM-driven search discovery" and "site
# architecture" while the canonical master resume contained no occurrence of
# ``search``, ``seo``, ``architecture`` or ``index``; the tailoring brief
# invented the phrase, the writer inserted it, the reviewer extended it, and the
# ATS stage then reported it as covered - a circular certification.
#
# These helpers ground the FINAL accepted resume against the evidence corpus.
# They are deliberately high-signal rather than all-token equality: only
# *named* capabilities, disciplines and technologies are checked, plus numeric
# metrics, so grammatical rewrites, reordering, shortening, punctuation and
# synonymous connective prose are never flagged.

# Inclusion rule for the lexicon: a term names a specific capability,
# discipline, channel, methodology or technology that a hiring manager would
# read as a distinct skill claim. Generic umbrella words that are already the
# candidate's own vocabulary ("growth", "acquisition", "traffic", "product")
# are deliberately absent: re-framing existing evidence is not a novel claim.
CLAIM_DOMAIN_TERMS: tuple[str, ...] = (
    # Acquisition / search / site disciplines
    "technical seo",
    "seo",
    "sea",
    "sem",
    "search discovery",
    "search marketing",
    "organic search",
    "organic traffic",
    "paid search",
    "paid social",
    "paid acquisition",
    "site architecture",
    "information architecture",
    "page performance",
    "core web vitals",
    "indexing",
    "crawlability",
    "keyword research",
    "link building",
    "backlinks",
    "technical audit",
    "technical seo audit",
    "media buying",
    "programmatic advertising",
    "demand generation",
    "growth hacking",
    "lifecycle marketing",
    "email marketing",
    "retention marketing",
    "affiliate marketing",
    "referral programme",
    "referral program",
    "conversion rate optimisation",
    "conversion rate optimization",
    "cro",
    "attribution modelling",
    "attribution modeling",
    "marketing attribution",
    "multi-touch attribution",
    "channel mix",
    "marketing automation",
    "abm",
    "account-based marketing",
    # Product / delivery methodologies
    "product-led growth",
    "plg",
    "jobs to be done",
    "design thinking",
    "lean startup",
    "scrum",
    "kanban",
    "okrs",
    "north star metric",
    "pricing strategy",
    "monetisation strategy",
    "monetization strategy",
    "roadmapping",
    "a/b testing",
    "multivariate testing",
    # Data / AI technologies and platforms
    "machine learning",
    "deep learning",
    "nlp",
    "natural language processing",
    "computer vision",
    "recommender system",
    "recommendation engine",
    "personalisation engine",
    "personalization engine",
    "vector database",
    "embeddings",
    "retrieval augmented generation",
    "fine-tuning",
    "prompt engineering",
    "llm evaluation",
    "ai governance",
    "data warehousing",
    "data pipeline",
    "etl",
    "dbt",
    "snowflake",
    "databricks",
    "looker",
    "tableau",
    "amplitude",
    "mixpanel",
    "segment",
    "braze",
    "klaviyo",
    "iterable",
    "hubspot",
    "salesforce marketing cloud",
    "optimizely",
    "launchdarkly",
    # Search / site family variants: the Clickboat defect re-phrased is still the
    # same invented capability, so the family is enumerated rather than the one
    # spelling the pilot happened to produce.
    "search engine optimisation",
    "search engine optimization",
    "search engine marketing",
    "search visibility",
    "search-led acquisition",
    "search and discovery",
    "site search",
    "internal search",
    "index coverage",
    "crawl budget",
    "crawl strategy",
    "schema markup",
    "serp",
    "canonicalisation",
    "canonicalization",
    "content discoverability",
    "query understanding",
    "site speed",
    "page speed",
    "information hierarchy",
)

# Numeric metrics carry a marker so plain counts, dates and version numbers are
# not treated as outcome claims. A metric is grounded only when the same
# number+marker appears in the evidence corpus.
_CLAIM_METRIC_RE = re.compile(
    r"(?P<metric>"
    r"(?:[$€£¥]|r\$|usd\s?|eur\s?|brl\s?)\s?\d{1,15}(?:[.,]\d{1,3})*\s?(?:k|m|bn|b|million|billion)?\+?"
    r"|\d{1,15}(?:[.,]\d{1,3})*\s?(?:%|percent)"
    r"|\d{1,15}(?:[.,]\d{1,3})*\s?(?:points?|pts)\b"
    r"|\d{1,15}(?:[.,]\d{1,3})*\s?(?:million|billion|bn)\b"
    r")",
    re.IGNORECASE,
)

# Claim-shaped numbers and quantity words that carry no metric marker. These are
# the load-bearing resume claims (experience length, headcount, growth
# multiples) and are grounded on the same exact-phrase basis as metrics.
_UNMARKED_CLAIM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("experience", r"\d{1,2}\s*\+?\s*years?"),
    ("team_size", r"(?:a\s+)?team\s+of\s+\d{1,4}"),
    ("headcount", r"\d{1,3}\s+(?:direct\s+)?reports"),
    ("multiplier", r"\d{1,3}(?:\.\d)?\s*x"),
    ("growth", r"(?:doubled|tripled|quadrupled|halved)"),
    ("scale_word", r"(?:hundreds|thousands|millions|billions)\s+of"),
    # Thousands-separated counts ("8,000+", "18,000+ merchants") are scale claims
    # that carry no metric marker. Grounded on the exact digit run, so a
    # fabricated count cannot be satisfied by a larger evidenced one.
    ("count_scale", r"\d{1,3}(?:,\d{3})+\+?"),
)


def _compact_claim_text(text: str) -> str:
    """Lowercase, drop LaTeX escapes/braces and collapse whitespace.

    Makes ``45\\%`` and ``45 %`` compare equal to ``45%``, and ``€400M`` to
    ``€ 400 m``, so formatting churn never produces a false claim.
    """
    text = text.replace("\\", "")
    text = re.sub(r"[{}]", " ", text)
    text = text.lower().replace("\u2013", "-")
    # Dotted acronyms ("S.E.O." -> "seo", "A.I." -> "ai") so an acronym cannot
    # hide a claim from the lexicon, and control characters (including ESC) are
    # dropped so nothing from a scraped posting can reach a terminal escape.
    text = re.sub(r"\b([a-z])\.([a-z])\.([a-z])\.", r"\1\2\3", text)
    text = re.sub(r"\b([a-z])\.([a-z])\.", r"\1\2", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return re.sub(r"\s+", " ", text)


def _metric_signature(raw: str) -> tuple[str, str] | None:
    """Canonical ``(digits, unit-class)`` signature for a metric, or None.

    Normalises notation so an evidenced number keeps passing when the writer
    changes its form (``28%`` vs ``28 percent``, ``22 points`` vs ``22 pts.``),
    while keeping the digit run exact so a fabricated number can never be
    satisfied by a longer evidenced one (``5%`` is not ``45%``).
    """
    text = re.sub(r"\s+", "", _compact_claim_text(raw)).rstrip(".")
    digits_match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not digits_match:
        return None
    digits = digits_match.group(0).replace(",", "")
    if "%" in text or "percent" in text:
        unit = "pct"
    elif "pts" in text or "points" in text:
        unit = "pts"
    else:
        unit = "num"
    return (digits, unit)


def _claim_term_pattern(term: str) -> str:
    """Word-boundary regex for a claim term, tolerant of spaces vs hyphens."""
    body = re.escape(term).replace(r"\ ", r"[\s-]+")
    return r"(?<![\w-])" + body + r"(?![\w-])"


def _morphological_variant_grounded(word: str, compact_evidence: str) -> bool:
    """True when an inflected form of ``word`` appears in the evidence corpus.

    Only explicit English suffixes are stripped, the remaining base must still be
    at least four characters, and a doubled trailing consonant is collapsed, so
    legitimate variants are grounded (``testing``/``tests``,
    ``roadmapping``/``roadmap``) without grounding unrelated proper nouns:
    ``braze`` keeps no usable base and never matches ``brazil``, and
    ``optimizely``/``iterable`` stay ungrounded. This is the symmetric form of
    the rule; the previous prefix-truncation both missed real variants and
    invented false groundings.
    """
    for suffix in ("ings", "ing", "ions", "ion", "ers", "er", "es", "ed", "s"):
        if not word.endswith(suffix):
            continue
        base = word[: -len(suffix)]
        if len(base) < 4:
            continue
        if len(base) > 4 and base[-1] == base[-2] and base[-1] not in "aeiou":
            base = base[:-1]
        tail = r"(?:s|es|ed|ing|ings|er|ers|ion|ions)?"
        pattern = r"(?<![\w-])" + re.escape(base) + tail + r"(?![\w-])"
        if re.search(pattern, compact_evidence):
            return True
    return False


def _term_is_grounded(term: str, compact_evidence: str) -> bool:
    """True when the evidence corpus supports the claim term.

    Exact word-boundary match first, then a suffix-based morphological variant of
    the final word. For a multi-word term the leading words must still appear
    contiguously, so a phrase is not grounded merely because its parts appear
    separately elsewhere: "lifecycle marketing" is not evidenced by a master
    resume that mentions "lifecycle messaging" and "market" independently.
    """
    if re.search(_claim_term_pattern(term), compact_evidence):
        return True

    words = term.split()
    if not words:
        return False
    if len(words) == 1:
        return _morphological_variant_grounded(words[0], compact_evidence)

    head = r"[\s-]+".join(re.escape(word) for word in words[:-1])
    last = words[-1]
    for suffix in ("ings", "ing", "ions", "ion", "ers", "er", "es", "ed", "s", ""):
        base = last[: -len(suffix)] if suffix else last
        if len(base) < 4:
            continue
        if len(base) > 4 and base[-1] == base[-2] and base[-1] not in "aeiou":
            base = base[:-1]
        tail = r"(?:s|es|ed|ing|ings|er|ers|ion|ions)?"
        body = f"{head}[\\s-]+{re.escape(base)}{tail}"
        if re.search(r"(?<![\w-])" + body + r"(?![\w-])", compact_evidence):
            return True
    return False


def _metric_key(raw: str) -> str:
    """Normalise a metric to a comparable key, e.g. ``45%`` / ``€400m``."""
    return re.sub(r"\s+", "", _compact_claim_text(raw))


def _first_present(*values: object) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value)
    return None


def build_evidence_corpus(
    *,
    master_resume: str | None,
    canonical_template: str | None = None,
    skills_inventory: str | None = None,
    career_config: str | None = None,
    story_bank: str | None = None,
) -> str:
    """Assemble the candidate-controlled evidence corpus.

    Only sources the project already treats as canonical candidate evidence are
    included: the master resume, the hand-maintained canonical LaTeX template
    (which holds facts that are not in the rendered master text), the Notion
    skills inventory, the career config, and the candidate's own story bank.

    Never included: the job description, the tailoring brief, reviewer output,
    ATS output, the generated resume, generated Q&A, or company research.
    """
    parts = [
        _first_present(master_resume) or "",
        _first_present(canonical_template) or "",
        _first_present(skills_inventory) or "",
        _first_present(career_config) or "",
        _first_present(story_bank) or "",
    ]
    return "\n".join(part for part in parts if part)


def _resume_context(text: str, index: int, before: int = 45, width: int = 120) -> str:
    """Return a short, non-sensitive window of the artifact around a match.

    Callers pass the compacted claim text (single logical line), so a window is
    used rather than line extraction.
    """
    start = max(0, index - before)
    snippet = text[start : start + width].strip()
    return re.sub(r"\s+", " ", snippet)


def find_unsupported_claims(
    latex: str,
    evidence_text: str,
    jd_skill_terms: Sequence[str] = (),
) -> list[dict[str, object]]:
    """Return novel factual claims in ``latex`` unsupported by the evidence.

    Deterministic and offline: no LLM, no embeddings, no external service.

    Three high-signal checks, all evaluated on the FINAL accepted artifact:

    1. **Named capability / discipline / technology** from
       :data:`CLAIM_DOMAIN_TERMS` that appears in the resume but nowhere in the
       evidence corpus.
    2. **Numeric metric** (percentage, currency, points, scale word) whose exact
       number+marker does not appear in the evidence corpus.
    3. **Job-description skill term** that the pipeline itself extracted from the
       posting and that appears in the resume but not in the evidence. The JD is
       explicitly not evidence, so this closes the circular-certification hole.

    Only *added* claims matter, and the canonical template is part of the
    evidence, so pre-existing canonical content is never flagged.

    Returns a list of ``{"blocking", "kind", "term", "context"}`` dicts, empty
    when the artifact is fully grounded. ``blocking`` distinguishes a real
    invented-capability finding from an advisory one.
    """
    findings: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    if not latex.strip() or not evidence_text.strip():
        return findings

    compact_resume = _compact_claim_text(latex)
    compact_evidence = _compact_claim_text(evidence_text)

    for term in CLAIM_DOMAIN_TERMS:
        pattern = _claim_term_pattern(term)
        match = re.search(pattern, compact_resume)
        if not match:
            continue
        if _term_is_grounded(term, compact_evidence):
            continue
        key = ("domain", term)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "blocking": True,
                "kind": "domain",
                "term": term,
                "context": _resume_context(compact_resume, match.start()),
            }
        )

    # Metrics are compared as canonical (digits, unit) signatures, never as
    # substrings: "5%" must not be satisfied by an evidenced "45%".
    evidence_metrics = {
        signature
        for metric in _CLAIM_METRIC_RE.finditer(compact_evidence)
        if (signature := _metric_signature(metric.group("metric")))
    }
    for match in _CLAIM_METRIC_RE.finditer(compact_resume):
        signature = _metric_signature(match.group("metric"))
        if signature is None or signature in evidence_metrics:
            continue
        term = re.sub(r"\s+", "", _compact_claim_text(match.group("metric")))
        key = ("metric", term)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "blocking": True,
                "kind": "metric",
                "term": term,
                "context": _resume_context(compact_resume, match.start()),
            }
        )

    # Claim-shaped numbers and quantity words that carry no metric marker:
    # experience length, headcount and growth multiples are load-bearing resume
    # claims, so they are grounded on the same exact-phrase basis.
    for kind, pattern in _UNMARKED_CLAIM_PATTERNS:
        for match in re.finditer(pattern, compact_resume):
            phrase = re.sub(r"\s+", " ", match.group(0)).strip()
            if not phrase:
                continue
            # Boundary-aware: a fabricated "8,000+" must not be grounded by an
            # evidenced "18,000+" (the digit run must match exactly).
            grounded = re.search(
                r"(?<![\d,])" + re.escape(phrase) + r"(?![\d,])", compact_evidence
            )
            if grounded:
                continue
            key = (kind, phrase)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "blocking": True,
                    "kind": kind,
                    "term": phrase,
                    "context": _resume_context(compact_resume, match.start()),
                }
            )

    for raw_term in jd_skill_terms or ():
        term = _compact_claim_text(str(raw_term)).strip()
        if len(term) < 3:
            continue
        pattern = _claim_term_pattern(term)
        match = re.search(pattern, compact_resume)
        if not match or _term_is_grounded(term, compact_evidence):
            continue
        key = ("jd_skill", term)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                # Advisory, not blocking: mirroring the employer's own wording is
                # what tailoring is for. A JD-derived term cannot be *evidence*,
                # but on its own it is too weak a signal to hold a run - the real
                # Clickboat fabrications are all caught by the domain lexicon
                # above. Demoting this keeps the signal visible without turning
                # normal keyword mirroring into a false HOLD.
                "blocking": False,
                "kind": "jd_skill",
                "term": term,
                "context": _resume_context(compact_resume, match.start()),
            }
        )

    return findings


def format_unsupported_claims(
    findings: list[dict[str, object]], limit: int = 5
) -> str:
    """Render findings as a stable, non-sensitive diagnostic string.

    Duplicate terms (the same phrase can be reached through more than one check)
    are collapsed so a blocker detail never spends its budget restating itself.
    """
    unique: list[dict[str, object]] = []
    seen_terms: set[str] = set()
    for item in findings:
        term = str(item.get("term", ""))
        if term in seen_terms:
            continue
        seen_terms.add(term)
        unique.append(item)

    rendered = [
        f"{'blocking' if item.get('blocking', True) else 'advisory'} "
        f"{item.get('kind')} '{item.get('term')}' (evidence lacks it) in: "
        f"\"{item.get('context')}\""
        for item in unique[:limit]
    ]
    if len(unique) > limit:
        rendered.append(f"(+{len(unique) - limit} more)")
    return "; ".join(rendered)


def _master_skill_inventory(master_resume: str) -> set[str]:
    """Return the comma-separated skills declared in Technical Proficiency."""
    section = master_resume.split("## Technical Proficiency", 1)
    if len(section) != 2:
        return set()

    inventory: set[str] = set()
    for line in section[1].splitlines():
        if ":" not in line:
            continue
        _, values = line.split(":", 1)
        for value in values.split(","):
            skill = value.strip().lower()
            if not skill:
                continue
            inventory.add(skill)
            alias = re.sub(r"\s*\([^)]*\)", "", skill).strip()
            inventory.add(alias)
            for parenthetical in re.findall(r"\(([^)]+)\)", skill):
                inventory.add(parenthetical.strip().lower())
    return inventory


def _skill_is_allowed(skill: str, inventory: set[str]) -> bool:
    normalised = re.sub(r"\s+", " ", skill.strip().lower())
    if normalised in inventory:
        return True
    return any(
        normalised == candidate
        or (len(normalised) > 8 and normalised in candidate)
        for candidate in inventory
    )


def _validate_claim_text(text: str) -> list[str]:
    """Detect unsupported JD contamination and protected-fact regressions."""
    normalised = _normalise_fact_text(text)
    errors: list[str] = []

    forbidden = {
        "PLS": r"\bpls\b",
        "usage-based pricing": r"usage[- ]based pricing",
        "agentic terminology": r"\bagentic (?:workflows?|systems?)\b",
        "Voice AI": r"\bvoice ai\b",
        "IVR": r"\bivr\b",
        "RAG": r"\brag\b",
        "ReAct": r"\breact\b",
        "partial sign-up": r"partial sign[- ]up",
        "first value": r"\bfirst value\b",
        "habit formation": r"\bhabit formation\b",
        "WFP": r"world food programme",
        "Mollis": r"\bmollis\b",
        "promotion timing": r"promoted to senior pm after 18 months",
        "C&A absolute baselines": r"(?:~?2\.8%|~?3\.6%|~?72%|~?59%)",
    }
    for label, pattern in forbidden.items():
        if re.search(pattern, normalised):
            errors.append(f"Unsupported or stale claim: {label}")

    if "18,000+" in text:
        scale_context = ("analytics", "instrumentation", "platform scale", "merchant accounts")
        if not any(term in normalised for term in scale_context):
            errors.append("18,000+ must remain analytics/platform scale")

    if re.search(r"28\s*%", normalised):
        if "infinity testing campaigns" not in normalised:
            errors.append("28% EPM must be scoped to Infinity Testing campaigns")

    if "€12m" in normalised or "eur 12m" in normalised:
        if not re.search(r"unified catalog(?:ue)?", normalised):
            errors.append("FORVIA €12M+ must be attributed to the unified catalog")

    if re.search(r"r\$1\.17b", normalised) and "whatsapp" in normalised:
        errors.append("R$1.17B must not be attributed as WhatsApp GMV")

    return errors


def validate_resume_edits(edits: dict, master_resume: str) -> list[str]:
    """Validate targeted edit fields against the selected master and fact locks."""
    errors: list[str] = []
    for key in ("summary_bullet",):
        value = edits.get(key)
        if value:
            errors.extend(_validate_claim_text(value))

    bullets = edits.get("postscript_bullets") or []
    if bullets:
        errors.extend(_validate_claim_text(" ".join(bullets)))

    for skill_group in edits.get("skills") or []:
        content = skill_group.get("content", "") if isinstance(skill_group, dict) else str(skill_group)
        for skill in content.split(","):
            if skill.strip() and not _skill_is_allowed(skill, _master_skill_inventory(master_resume)):
                errors.append(f"Skill not present in master resume: {skill.strip()}")

    return list(dict.fromkeys(errors))


def validate_resume_draft(latex: str, master_resume: str) -> list[str]:
    """Validate a complete generated draft before it reaches LaTeX compilation."""
    errors = _validate_claim_text(latex)

    safety_text = re.sub(r"(?m)^\s*%.*$", "", latex)
    safety_text = re.sub(r"\\href\{[^{}]*\}\{[^{}]*\}", "", safety_text)
    safety_text = re.sub(r"\\url\{[^{}]*\}", "", safety_text)
    for char, label in (("%", "%"), ("&", "&"), ("#", "#"), ("_", "_")):
        if re.search(rf"(?<!\\){re.escape(char)}", safety_text):
            errors.append(f"Unescaped LaTeX character: {label}")

    if "### Postscript" in master_resume and "Infinity Testing" in master_resume:
        required = {
            "post-launch": "Postscript post-launch ownership",
            "infinity testing": "Infinity Testing ownership",
            "brand center": "Brand Center control layer",
            "merchant review": "merchant review/control",
            "quality criteria": "product-specific quality criteria",
        }
        normalised = _normalise_fact_text(latex)
        for phrase, label in required.items():
            if phrase not in normalised:
                errors.append(f"Missing protected Postscript anchor: {label}")

    canonical_headers = (
        ("Postscript", "Senior Product Manager", "Dec 2024 -- Aug 2026"),
        ("FORVIA HELLA", "Senior Product Manager", "Feb 2023 -- Oct 2024"),
        ("Accenture Brasil", "Senior Product Manager / Digital Commerce", "Sep 2020 -- Nov 2022"),
        ("C&A Brasil", "Product Manager", "Nov 2018 -- Aug 2020"),
    )
    for company, title, dates in canonical_headers:
        if company in latex and (title not in latex or dates not in latex):
            errors.append(f"Canonical header mismatch: {company}")

    return list(dict.fromkeys(errors))


# Experience sections that come from the canonical factual template. In
# targeted-edit mode these must stay byte-for-byte unchanged through the
# reviewer and ATS stages.
LOCKED_EXPERIENCE_COMPANIES: dict[str, str] = {
    "FORVIA HELLA": "FORVIA HELLA",
    "Accenture Brasil": "Accenture Brasil",
    "C&A Brasil": r"C\&A Brasil",
}


def extract_locked_experience_blocks(latex: str) -> dict[str, str]:
    """Return the byte-exact experience block for each locked company."""
    blocks: dict[str, str] = {}
    for company, latex_name in LOCKED_EXPERIENCE_COMPANIES.items():
        pattern = (
            rf"(\\noindent\\textbf\{{{re.escape(latex_name)}\}}.*?\\end\{{itemize\}})"
        )
        match = re.search(pattern, latex, re.DOTALL)
        if match:
            blocks[company] = match.group(1)
    return blocks


def locked_experience_drift(before: str, after: str) -> list[str]:
    """Return locked companies whose canonical experience block changed."""
    before_blocks = extract_locked_experience_blocks(before)
    after_blocks = extract_locked_experience_blocks(after)
    return [
        company
        for company, block in before_blocks.items()
        if after_blocks.get(company) != block
    ]


def _escape_latex_fragment(text: str) -> str:
    """Escape inserted text while preserving existing LaTeX commands."""
    protected: dict[str, str] = {}

    def protect(match: re.Match) -> str:
        key = f"LATEXFRAGMENT{len(protected)}TOKEN"
        protected[key] = match.group(0)
        return key

    pattern = re.compile(r"\\[A-Za-z]+\*?(?:\{[^{}]*\})?|\\[%$&#_{}~^]")
    escaped = _escape_latex(pattern.sub(protect, text))
    for key, value in protected.items():
        escaped = escaped.replace(key, value)
    return escaped


def apply_safe_latex_replacement(latex: str, old: str, new: str) -> str:
    """Replace reviewer/ATS content after safely escaping inserted LaTeX text."""
    return latex.replace(old, _escape_latex_fragment(new), 1)


def apply_grounded_ats_edits(
    latex: str, edits: list[dict], master_resume: str, targeted: bool = True
) -> tuple[str, int, int]:
    """Apply only exact, master-grounded ATS replacements."""
    result = latex
    applied = 0
    skipped = 0
    master_lower = master_resume.lower()

    for edit in edits:
        keyword = str(edit.get("keyword", "")).strip()
        old = str(edit.get("current_text", "")).strip().strip('"')
        new = str(edit.get("suggested_text", "")).strip()

        if keyword and keyword.lower() not in master_lower:
            skipped += 1
            continue
        if not old or not new or old not in result:
            skipped += 1
            continue

        candidate = apply_safe_latex_replacement(result, old, new)
        if validate_resume_draft(candidate, master_resume):
            skipped += 1
            continue
        if targeted and locked_experience_drift(result, candidate):
            skipped += 1
            continue

        result = candidate
        applied += 1

    return result, applied, skipped


def apply_resume_edits(base_latex: str, edits: dict, master_resume: str | None = None) -> str:
    """Apply targeted edits while rejecting unsupported fields."""
    result = base_latex
    safe_edits = dict(edits)

    if master_resume:
        if safe_edits.get("summary_bullet") and _validate_claim_text(safe_edits["summary_bullet"]):
            safe_edits.pop("summary_bullet", None)
        if safe_edits.get("postscript_bullets") and _validate_claim_text(" ".join(safe_edits["postscript_bullets"])):
            safe_edits.pop("postscript_bullets", None)
        if safe_edits.get("skills") and validate_resume_edits({"skills": safe_edits["skills"]}, master_resume):
            safe_edits.pop("skills", None)

    if safe_edits.get("tagline"):
        tagline_replacement = "{\\small " + _escape_latex(safe_edits["tagline"]) + "}"
        result = re.sub(
            r"\{\\small [^}]+\}",
            lambda m: tagline_replacement,
            result, count=1,
        )

    if safe_edits.get("summary_bullet"):
        result = _replace_itemize_block(
            result,
            r"\\section\*\{Summary\}",
            [safe_edits["summary_bullet"]],
        )

    if safe_edits.get("postscript_bullets"):
        result = _replace_company_bullets(
            result, "Postscript", safe_edits["postscript_bullets"]
        )

    if safe_edits.get("skills"):
        result = _replace_skills(result, safe_edits["skills"])

    return result


def _replace_itemize_block(latex: str, section_pattern: str, bullets: list) -> str:
    """Find the first itemize block after section_pattern and replace its items."""
    pattern = (
        rf"({section_pattern}.*?\\begin{{itemize}}[^\n]*\n)"
        rf"(.*?)"
        rf"(\\end{{itemize}})"
    )
    items = "\n".join(f"\\item {_escape_latex(b)}" for b in bullets)

    def replacer(m):
        return m.group(1) + items + "\n" + m.group(3)

    return re.sub(pattern, replacer, latex, flags=re.DOTALL, count=1)


def _replace_company_bullets(latex: str, company: str, bullets: list) -> str:
    """Replace bullet points for a specific company entry."""
    esc = re.escape(company)
    pattern = (
        rf"(\\noindent\\textbf\{{{esc}\}}.*?\\begin{{itemize}}[^\n]*\n)"
        rf"(.*?)"
        rf"(\\end{{itemize}})"
    )
    items = "\n".join(f"\\item {_escape_latex(b)}" for b in bullets)

    def replacer(m):
        return m.group(1) + items + "\n" + m.group(3)

    return re.sub(pattern, replacer, latex, flags=re.DOTALL, count=1)


def _replace_skills(latex: str, skills: list) -> str:
    """Replace the Skills & Tools itemize block."""
    pattern = (
        r"(\\section\*\{Skills.*?\}.*?\\begin\{itemize\}[^\n]*\n)"
        r"(.*?)"
        r"(\\end\{itemize\})"
    )

    def make_item(s):
        if isinstance(s, dict):
            cat = _escape_latex(s.get("category", ""))
            content = _escape_latex(s.get("content", ""))
            return f"\\item \\textbf{{{cat}:}} {content}"
        # Fallback: plain string
        if ":" in s:
            cat, _, rest = s.partition(":")
            return f"\\item \\textbf{{{_escape_latex(cat.strip())}:}} {_escape_latex(rest.strip())}"
        return f"\\item {_escape_latex(s)}"

    items = "\n".join(make_item(s) for s in skills)

    def replacer(m):
        return m.group(1) + items + "\n" + m.group(3)

    return re.sub(pattern, replacer, latex, flags=re.DOTALL, count=1)
