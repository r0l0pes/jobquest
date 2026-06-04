#!/usr/bin/env python3
"""Compile a .tex file to PDF using pdflatex + inspect-and-fix loop."""

import sys
import os
import json
import subprocess
from pathlib import Path


def compile_tex(tex_path):
    """Run pdflatex twice on the given .tex file and return the PDF path."""
    tex_path = os.path.abspath(tex_path)
    if not os.path.exists(tex_path):
        return {"success": False, "error": f"File not found: {tex_path}"}

    output_dir = os.path.dirname(tex_path)
    basename = os.path.splitext(os.path.basename(tex_path))[0]
    pdf_path = os.path.join(output_dir, f"{basename}.pdf")

    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
        tex_path,
    ]

    # Run twice for cross-references
    for run in (1, 2):
        print(f"pdflatex pass {run}...", file=sys.stderr)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            # Extract relevant error lines from pdflatex output
            error_lines = []
            for line in result.stdout.split("\n"):
                if line.startswith("!") or "Error" in line or "Fatal" in line:
                    error_lines.append(line)
            return {
                "success": False,
                "error": "pdflatex failed",
                "details": error_lines[:10],
                "returncode": result.returncode,
            }

    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"PDF not generated at {pdf_path}"}

    print(f"PDF generated: {pdf_path}", file=sys.stderr)
    return {"success": True, "pdf_path": pdf_path, "tex_path": tex_path}


# ─── PDF Inspection Utilities ────────────────────────────────────


def get_pdf_pages(pdf_path):
    """Get page count using pdfinfo."""
    try:
        result = subprocess.run(
            ["pdfinfo", pdf_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.split("\n"):
            if line.startswith("Pages:"):
                try:
                    return int(line.split(":")[1].strip())
                except ValueError:
                    return None
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_pdf_text(pdf_path):
    """Extract text from PDF using pdftotext -layout."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _is_bullet_line(text):
    """Check if a line starts with bullet characters."""
    return text.startswith("•") or text.startswith("-") or text.startswith("*")


def _check_orphaned_entries(text):
    """Check for orphaned entry titles at page breaks.
    
    Returns a dict if orphan detected, None otherwise.
    An orphan occurs when an entry title (non-bullet) is the last content on 
    page N and page N+1 starts with bullet items.
    """
    pages = text.split("\f")
    if len(pages) < 2:
        return None

    for i in range(len(pages) - 1):
        page_lines = [l for l in pages[i].strip().split("\n") if l.strip()]
        next_page_lines = [l for l in pages[i + 1].strip().split("\n") if l.strip()]

        if not page_lines or not next_page_lines:
            continue

        last_line = page_lines[-1].strip()
        first_next_line = next_page_lines[0].strip()

        # If last line is not a bullet and next page starts with bullet → orphan
        if not _is_bullet_line(last_line) and _is_bullet_line(first_next_line):
            return {
                "type": "orphaned_entry",
                "detail": f"Entry title '{last_line[:60]}' may be orphaned at page {i + 1} bottom"
            }

    return None


def _check_whitespace(text):
    """Check for awkward whitespace patterns in CV."""
    issues = []
    pages = text.split("\f")

    for i, page in enumerate(pages):
        lines = [l for l in page.strip().split("\n") if l.strip()]

        for j, line in enumerate(lines):
            stripped = line.strip()
            # Section headers near bottom of page with few following lines
            if stripped.isupper() and len(lines) - j < 4 and len(stripped) > 3:
                issues.append({
                    "type": "isolated_section",
                    "page": i + 1,
                    "detail": f"Section '{stripped[:40]}' near end of page {i + 1} with few following lines"
                })
                break  # One issue per page is enough

    return issues


def _check_closing_visible(text):
    """Check if cover letter closing is present in extracted text."""
    closings = ["Mit freundlichen", "Gruessen", "Sincerely", "Yours faithfully",
                "Yours sincerely", "Kind regards", "Best regards"]
    for closing in closings:
        if closing.lower() in text.lower():
            return True
    return False


def _inspect_pdf(pdf_path, doc_type):
    """Inspect a compiled PDF for layout issues.

    Args:
        pdf_path: Path to the PDF file
        doc_type: 'cv' or 'cover_letter'

    Returns:
        List of issue dicts (empty if clean)
    """
    issues = []

    # 1. Page count check
    pages = get_pdf_pages(pdf_path)
    if pages is None:
        issues.append({"type": "pdfinfo_failed", "detail": "Could not read page count"})
        return issues

    if doc_type == "cv":
        if pages != 2:
            issues.append({
                "type": "page_count",
                "expected": 2,
                "actual": pages,
                "detail": f"CV has {pages} pages (expected 2)"
            })
    elif doc_type == "cover_letter":
        if pages != 1:
            issues.append({
                "type": "page_count",
                "expected": 1,
                "actual": pages,
                "detail": f"Cover letter has {pages} pages (expected 1)"
            })

    # 2. Structural checks via pdftotext
    text = get_pdf_text(pdf_path)
    if text is None:
        issues.append({"type": "pdftotext_failed", "detail": "Could not extract PDF text"})
        return issues

    if doc_type == "cv":
        # Orphaned entry detection
        orphaned = _check_orphaned_entries(text)
        if orphaned:
            issues.append(orphaned)

        # Whitespace / isolated sections
        whitespace_issues = _check_whitespace(text)
        issues.extend(whitespace_issues)

    elif doc_type == "cover_letter":
        # Closing/signature cutoff
        if not _check_closing_visible(text):
            issues.append({
                "type": "closing_cutoff",
                "detail": "Closing/signature may be cut off"
            })

    return issues


# ─── Fix Application ────────────────────────────────────────────


def _apply_fixes(tex_path, issues):
    """Apply LaTeX fixes for detected PDF issues.

    Args:
        tex_path: Path to the .tex file to modify
        issues: List of issue dicts from _inspect_pdf

    Returns:
        List of descriptions for fixes applied
    """
    applied = []
    tex_content = Path(tex_path).read_text()
    lines = tex_content.split("\n")
    modified = False

    for issue in issues:
        if issue["type"] == "orphaned_entry":
            detail = issue.get("detail", "")
            # Extract entry title from detail: "Entry title 'TEXT' may be..."
            import re
            title_match = re.search(r"'([^']+)'", detail)
            if title_match:
                title_text = title_match.group(1)[:40]
                # Try exact match first, then partial
                for j, line in enumerate(lines):
                    if title_text in line or any(
                        word for word in title_text.split() if len(word) > 5 and word in line
                    ):
                        if title_text[:30] in line or title_text.split(",")[0].strip()[:20] in line:
                            lines.insert(j, "\\needspace{5\\baselineskip}")
                            applied.append(f"Inserted needspace before orphaned entry '{title_text[:40]}'")
                            modified = True
                            break

        elif issue["type"] == "page_count":
            expected = issue.get("expected", 0)
            actual = issue.get("actual", 0)
            if expected == 2 and actual >= 3:
                # CV spills past 2 pages — add enlargethispage before last section
                if "\\enlargethispage" not in tex_content:
                    last_section_idx = None
                    for j, line in enumerate(lines):
                        if "\\section*{" in line:
                            last_section_idx = j
                    if last_section_idx is not None:
                        lines.insert(last_section_idx, "\\enlargethispage{2\\baselineskip}")
                        applied.append("Added enlargethispage to last CV section")
                        modified = True
                    else:
                        # No section found — add before \end{document}
                        for j, line in enumerate(lines):
                            if "\\end{document}" in line:
                                lines.insert(j, "\\enlargethispage{2\\baselineskip}")
                                applied.append("Added enlargethispage before end of document")
                                modified = True
                                break
            elif expected == 1 and actual >= 2:
                # Cover letter spills — add enlargethispage
                if "\\enlargethispage" not in tex_content:
                    for j, line in enumerate(lines):
                        if "\\begin{document}" in line:
                            lines.insert(j + 1, "\\enlargethispage{2\\baselineskip}")
                            applied.append("Added enlargethispage to cover letter")
                            modified = True
                            break

        elif issue["type"] == "isolated_section":
            detail = issue.get("detail", "")
            import re
            section_match = re.search(r"Section '([^']+)'", detail)
            if section_match:
                section_name = section_match.group(1)
                for j, line in enumerate(lines):
                    if f"\\section*{{{section_name}}}" in line:
                        lines.insert(j, "\\needspace{4\\baselineskip}")
                        applied.append(f"Inserted needspace before isolated section '{section_name}'")
                        modified = True
                        break

        elif issue["type"] == "closing_cutoff":
            if "\\enlargethispage" not in tex_content:
                for j, line in enumerate(lines):
                    if "\\begin{document}" in line:
                        lines.insert(j + 1, "\\enlargethispage{3\\baselineskip}")
                        applied.append("Added enlargethispage to prevent closing cutoff")
                        modified = True
                        break

    if modified:
        Path(tex_path).write_text("\n".join(lines))

    return applied


# ─── Compile-and-Inspect Orchestrator ───────────────────────────


def compile_and_inspect(tex_path, doc_type="cv", max_retries=3):
    """Compile LaTeX, inspect PDF, retry with fixes up to max_retries.

    Args:
        tex_path: Path to the .tex file
        doc_type: 'cv' or 'cover_letter'
        max_retries: Maximum fix-and-recompile attempts

    Returns:
        {"ok": bool, "pdf_path": str, "pages": int | None,
         "issues": list, "fixes": list, "warning": str | None}
    """
    all_issues = []
    all_fixes = []

    for attempt in range(max_retries):
        print(f"Compile attempt {attempt + 1}/{max_retries}...", file=sys.stderr)

        result = compile_tex(tex_path)
        if not result.get("success"):
            return {
                "ok": False,
                "error": result.get("error", "Unknown error"),
                "details": result.get("details", []),
                "issues": all_issues,
                "fixes": all_fixes,
            }

        # Inspect the PDF
        issues = _inspect_pdf(result["pdf_path"], doc_type)

        if not issues:
            # Clean compile — success
            pages = get_pdf_pages(result["pdf_path"])
            return {
                "ok": True,
                "pdf_path": result["pdf_path"],
                "pages": pages,
                "issues": all_issues,
                "fixes": all_fixes,
            }

        # Log issues
        for issue in issues:
            type_name = issue.get("type", "unknown")
            print(f"  Issue [{type_name}]: {issue.get('detail', '')}", file=sys.stderr)

        all_issues.extend(issues)

        # Apply fixes
        fixes = _apply_fixes(tex_path, issues)
        if not fixes:
            # Unfixable issues — stop retrying
            print("  No automatic fixes available for remaining issues", file=sys.stderr)
            break

        for fix in fixes:
            print(f"  Fix: {fix}", file=sys.stderr)
        all_fixes.extend(fixes)

    # After max retries — check final state
    result = compile_tex(tex_path)
    if result.get("success"):
        pages = get_pdf_pages(result["pdf_path"])
        warning = (
            f"Layout issues may persist after {max_retries} attempts"
            if all_issues else None
        )
        return {
            "ok": True,
            "pdf_path": result["pdf_path"],
            "pages": pages,
            "issues": all_issues,
            "fixes": all_fixes,
            "warning": warning,
        }

    return {
        "ok": False,
        "error": f"Layout issues persist after {max_retries} attempts",
        "issues": all_issues,
        "fixes": all_fixes,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: render_pdf.py <path_to_tex_file>", file=sys.stderr)
        sys.exit(1)

    tex_path = sys.argv[1]
    result = compile_tex(tex_path)
    print(json.dumps(result, indent=2))

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
