"""Parsers for extracting structured content from LLM text responses.

Each parser uses multiple fallback strategies because LLM output
formatting is unpredictable even with explicit instructions.
"""

import re
import json


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
