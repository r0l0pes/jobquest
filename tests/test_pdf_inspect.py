"""Tests for PDF compile-and-inspect loop — Spec 003.

Verifies inspection logic, fix application, and compile_and_inspect orchestration.
"""

import os
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


class TestPdfInspection:
    """Verify PDF inspection detects layout issues."""

    def test_inspect_cv_two_pages_clean(self):
        """CV with exactly 2 pages, no orphans — no issues."""
        from scripts.render_pdf import _inspect_pdf

        with (
            patch("scripts.render_pdf.get_pdf_pages", return_value=2),
            patch("scripts.render_pdf.get_pdf_text", return_value=(
                "Summary\n"
                "Senior Product Manager...\n"
                "\f"
                "Skills & Tools\n"
                "Product: Strategy...\n"
            )),
        ):
            issues = _inspect_pdf("/fake/resume.pdf", "cv")
            assert issues == [], f"Expected no issues for clean CV, got {issues}"

    def test_inspect_cv_wrong_page_count(self):
        """CV with 3 pages — should detect page count issue."""
        from scripts.render_pdf import _inspect_pdf

        with (
            patch("scripts.render_pdf.get_pdf_pages", return_value=3),
            patch("scripts.render_pdf.get_pdf_text", return_value="Content"),
        ):
            issues = _inspect_pdf("/fake/resume.pdf", "cv")
            assert len(issues) >= 1
            assert issues[0]["type"] == "page_count"
            assert issues[0]["expected"] == 2
            assert issues[0]["actual"] == 3

    def test_inspect_cv_one_page(self):
        """CV with 1 page — should detect page count issue."""
        from scripts.render_pdf import _inspect_pdf

        with (
            patch("scripts.render_pdf.get_pdf_pages", return_value=1),
            patch("scripts.render_pdf.get_pdf_text", return_value="Content"),
        ):
            issues = _inspect_pdf("/fake/resume.pdf", "cv")
            assert len(issues) >= 1
            assert issues[0]["type"] == "page_count"
            assert issues[0]["expected"] == 2
            assert issues[0]["actual"] == 1

    def test_inspect_cv_orphaned_entry(self):
        """CV where last line is a job title and next page starts with bullets."""
        from scripts.render_pdf import _inspect_pdf

        # Page 1 ends with title (non-bullet), page 2 starts with bullets — orphan
        text = (
            "   Senior Product Manager with 8+ years...\n"
            "   Postscript, Senior Product Manager\n"
            "\f"
            "   • Built analytics instrumentation...\n"
            "   • Redesigned subscriber acquisition...\n"
        )
        with (
            patch("scripts.render_pdf.get_pdf_pages", return_value=2),
            patch("scripts.render_pdf.get_pdf_text", return_value=text),
        ):
            issues = _inspect_pdf("/fake/resume.pdf", "cv")
            # Last non-bullet line is "Postscript, Senior Product Manager"
            # First line of next page starts with "•" — orphan detection
            assert len(issues) >= 1
            orphan_issues = [i for i in issues if i["type"] == "orphaned_entry"]
            assert len(orphan_issues) == 1

    def test_inspect_cover_letter_one_page_clean(self):
        """Cover letter with 1 page — no issues."""
        from scripts.render_pdf import _inspect_pdf

        text = (
            "Sehr geehrtes ACME-Team,\n\n"
            "I am writing to apply...\n\n"
            "Mit freundlichen Grüßen,\n"
            "Rodrigo Lopes\n"
        )
        with (
            patch("scripts.render_pdf.get_pdf_pages", return_value=1),
            patch("scripts.render_pdf.get_pdf_text", return_value=text),
        ):
            issues = _inspect_pdf("/fake/cover_letter.pdf", "cover_letter")
            assert issues == [], f"Expected no issues, got {issues}"

    def test_inspect_cover_letter_two_pages(self):
        """Cover letter with 2 pages — should detect."""
        from scripts.render_pdf import _inspect_pdf

        with (
            patch("scripts.render_pdf.get_pdf_pages", return_value=2),
            patch("scripts.render_pdf.get_pdf_text", return_value="Content"),
        ):
            issues = _inspect_pdf("/fake/cover_letter.pdf", "cover_letter")
            assert len(issues) >= 1
            assert issues[0]["type"] == "page_count"
            assert issues[0]["expected"] == 1

    def test_inspect_cover_letter_missing_closing(self):
        """Cover letter without closing — cutoff detected."""
        from scripts.render_pdf import _inspect_pdf

        text = (
            "I am writing to apply for the role...\n\n"
            "Thank you for your consideration.\n"
            # No closing signature
        )
        with (
            patch("scripts.render_pdf.get_pdf_pages", return_value=1),
            patch("scripts.render_pdf.get_pdf_text", return_value=text),
        ):
            issues = _inspect_pdf("/fake/cover_letter.pdf", "cover_letter")
            closing_issues = [i for i in issues if i["type"] == "closing_cutoff"]
            assert len(closing_issues) >= 1

    def test_inspect_pdfinfo_fails(self):
        """When pdfinfo fails, report gracefully."""
        from scripts.render_pdf import _inspect_pdf

        with patch("scripts.render_pdf.get_pdf_pages", return_value=None):
            issues = _inspect_pdf("/fake/resume.pdf", "cv")
            assert len(issues) >= 1
            assert issues[0]["type"] == "pdfinfo_failed"


class TestFixApplication:
    """Verify automatic fix insertion into .tex content."""

    def test_apply_fix_orphaned_entry_adds_needspace(self):
        """Orphaned entry issue → needspace inserted into .tex."""
        from scripts.render_pdf import _apply_fixes

        tex_content = (
            "\\section*{Experience}\n\n"
            "\\noindent\\textbf{Postscript}, Senior Product Manager\n"
            "\\begin{itemize}\n"
            "\\item Led product development...\n"
            "\\end{itemize}\n"
        )
        test_path = Path("/tmp/test_cv.tex")
        test_path.write_text(tex_content)

        try:
            issues = [{
                "type": "orphaned_entry",
                "detail": "Entry title 'Postscript, Senior Product Manager' may be orphaned at page 1 bottom"
            }]
            fixes = _apply_fixes(str(test_path), issues)
            assert len(fixes) >= 1, f"Expected fixes, got: {fixes}"
            assert "needspace" in fixes[0].lower()

            new_content = test_path.read_text()
            assert "\\needspace{" in new_content
        finally:
            test_path.unlink(missing_ok=True)

    def test_apply_fix_page_count_cv_spill(self):
        """CV spills to 3 pages → enlargethispage added."""
        from scripts.render_pdf import _apply_fixes

        tex_content = (
            "\\begin{document}\n"
            "\\section*{Summary}\n\n"
            "Content here...\n\n"
            "\\section*{Experience}\n\n"
            "More content...\n\n"
            "\\section*{Skills & Tools}\n"
            "\\begin{itemize}\n"
            "\\item Skill A\n"
            "\\end{itemize}\n"
            "\\end{document}\n"
        )
        test_path = Path("/tmp/test_spill.tex")
        test_path.write_text(tex_content)

        try:
            issues = [{
                "type": "page_count",
                "expected": 2,
                "actual": 3,
                "detail": "CV has 3 pages (expected 2)"
            }]
            fixes = _apply_fixes(str(test_path), issues)
            assert len(fixes) >= 1

            new_content = test_path.read_text()
            assert "\\enlargethispage{" in new_content
        finally:
            test_path.unlink(missing_ok=True)

    def test_apply_fix_cover_letter_spill(self):
        """Cover letter spills to 2 pages → enlargethispage added."""
        from scripts.render_pdf import _apply_fixes

        tex_content = (
            "\\begin{document}\n"
            "\\begin{letterbody}\n"
            "Long cover letter content...\n"
            "\\end{letterbody}\n"
            "\\end{document}\n"
        )
        test_path = Path("/tmp/test_cl_spill.tex")
        test_path.write_text(tex_content)

        try:
            issues = [{
                "type": "page_count",
                "expected": 1,
                "actual": 2,
                "detail": "Cover letter has 2 pages (expected 1)"
            }]
            fixes = _apply_fixes(str(test_path), issues)
            assert len(fixes) >= 1

            new_content = test_path.read_text()
            assert "\\enlargethispage{" in new_content
        finally:
            test_path.unlink(missing_ok=True)

    def test_apply_fix_closing_cutoff(self):
        """Closing cutoff → enlargethispage added."""
        from scripts.render_pdf import _apply_fixes

        tex_content = (
            "\\begin{document}\n"
            "\\begin{letterbody}\n"
            "I am writing to apply...\n"
            "\\end{letterbody}\n"
            "\\end{document}\n"
        )
        test_path = Path("/tmp/test_closing.tex")
        test_path.write_text(tex_content)

        try:
            issues = [{
                "type": "closing_cutoff",
                "detail": "Closing/signature may be cut off"
            }]
            fixes = _apply_fixes(str(test_path), issues)
            assert len(fixes) >= 1

            new_content = test_path.read_text()
            assert "\\enlargethispage{" in new_content
        finally:
            test_path.unlink(missing_ok=True)

    def test_apply_fix_already_has_enlargethispage(self):
        """Don't add enlargethispage if already present."""
        from scripts.render_pdf import _apply_fixes

        tex_content = (
            "\\begin{document}\n"
            "\\enlargethispage{2\\baselineskip}\n"
            "\\begin{letterbody}\n"
            "Content...\n"
            "\\end{letterbody}\n"
            "\\end{document}\n"
        )
        test_path = Path("/tmp/test_already.tex")
        test_path.write_text(tex_content)

        try:
            issues = [{
                "type": "page_count",
                "expected": 1,
                "actual": 2,
                "detail": "Cover letter has 2 pages (expected 1)"
            }]
            fixes = _apply_fixes(str(test_path), issues)
            # Should not add a second enlargethispage
            new_content = test_path.read_text()
            assert new_content.count("\\enlargethispage") == 1
        finally:
            test_path.unlink(missing_ok=True)

    def test_apply_fix_isolated_section(self):
        """Isolated section header → needspace added."""
        from scripts.render_pdf import _apply_fixes

        tex_content = (
            "\\section*{Summary}\n"
            "\\begin{itemize}\n"
            "\\item Senior Product Manager...\n"
            "\\end{itemize}\n\n"
            "\\section*{Education}\n"
            "\\begin{itemize}\n"
            "\\item Bachelor's Degree...\n"
            "\\end{itemize}\n"
        )
        test_path = Path("/tmp/test_isolated.tex")
        test_path.write_text(tex_content)

        try:
            issues = [{
                "type": "isolated_section",
                "page": 2,
                "detail": "Section 'Education' near end of page 2 with few following lines"
            }]
            fixes = _apply_fixes(str(test_path), issues)
            assert len(fixes) >= 1

            new_content = test_path.read_text()
            assert "\\needspace{" in new_content
            assert "\\section*{Education}" in new_content
        finally:
            test_path.unlink(missing_ok=True)


class TestCompileAndInspect:
    """Verify the orchestration loop."""

    def test_compiles_cleanly_no_retries(self):
        """Clean compile, no issues — single attempt, success."""
        from scripts.render_pdf import compile_and_inspect

        with (
            patch("scripts.render_pdf.compile_tex") as mock_compile,
            patch("scripts.render_pdf._inspect_pdf", return_value=[]),
            patch("scripts.render_pdf.get_pdf_pages", return_value=2),
        ):
            mock_compile.return_value = {"success": True, "pdf_path": "/tmp/out.pdf"}

            result = compile_and_inspect("/tmp/resume.tex", "cv")
            assert result["ok"] is True
            assert result["pdf_path"] == "/tmp/out.pdf"
            assert result["pages"] == 2
            assert result["issues"] == []
            assert result["fixes"] == []

            # Should only compile once (no retries)
            assert mock_compile.call_count == 1

    def test_fixable_issue_triggers_retry(self):
        """An issue is found → fix applied → recompile succeeds."""
        from scripts.render_pdf import compile_and_inspect

        # First call: page count issue; second call: clean
        compile_results = [
            {"success": True, "pdf_path": "/tmp/out1.pdf"},
            {"success": True, "pdf_path": "/tmp/out2.pdf"},
        ]
        inspect_results = [
            [{"type": "page_count", "expected": 2, "actual": 3,
              "detail": "CV has 3 pages (expected 2)"}],
            [],
        ]

        with (
            patch("scripts.render_pdf.compile_tex", side_effect=compile_results),
            patch("scripts.render_pdf._inspect_pdf", side_effect=inspect_results),
            patch("scripts.render_pdf.get_pdf_pages", side_effect=[3, 2]),
            patch("scripts.render_pdf._apply_fixes", return_value=["Added enlargethispage"]),
        ):
            result = compile_and_inspect("/tmp/resume.tex", "cv")
            assert result["ok"] is True
            assert result["fixes"] == ["Added enlargethispage"]
            assert result["issues"] is not None

    def test_compile_error_no_inspection(self):
        """pdflatex fails → return error immediately."""
        from scripts.render_pdf import compile_and_inspect

        with (
            patch("scripts.render_pdf.compile_tex") as mock_compile,
            patch("scripts.render_pdf._inspect_pdf") as mock_inspect,
        ):
            mock_compile.return_value = {
                "success": False,
                "error": "pdflatex failed",
                "details": ["! Undefined control sequence."],
            }

            result = compile_and_inspect("/tmp/broken.tex", "cv")
            assert result["ok"] is False
            assert "error" in result
            # Should NOT attempt inspection if compile failed
            mock_inspect.assert_not_called()

    def test_fixable_issues_persist_after_retries(self):
        """Issues persist after max_retries → warn but still return result."""
        from scripts.render_pdf import compile_and_inspect

        # All attempts have issues: 3 loop iterations + 1 post-loop compile = 4
        compile_results = [
            {"success": True, "pdf_path": f"/tmp/out{i}.pdf"}
            for i in range(4)
        ]
        inspect_results = [
            [{"type": "page_count", "expected": 2, "actual": 3,
              "detail": "CV has 3 pages (expected 2)"}]
            for _ in range(4)
        ]

        with (
            patch("scripts.render_pdf.compile_tex", side_effect=compile_results),
            patch("scripts.render_pdf._inspect_pdf", side_effect=inspect_results),
            patch("scripts.render_pdf.get_pdf_pages", side_effect=[3, 3, 3, 3]),
            patch("scripts.render_pdf._apply_fixes", return_value=["Added enlargethispage"]),
        ):
            result = compile_and_inspect("/tmp/resume.tex", "cv", max_retries=3)
            assert result["ok"] is True  # Compiles but with warnings
            assert "warning" in result
            assert len(result["issues"]) >= 1

    def test_unfixable_issues_break_loop_early(self):
        """When _apply_fixes returns empty, break the retry loop."""
        from scripts.render_pdf import compile_and_inspect

        # 1 compile for the loop attempt, 1 for post-loop final recompile = 2
        compile_results = [
            {"success": True, "pdf_path": "/tmp/out1.pdf"},
            {"success": True, "pdf_path": "/tmp/out2.pdf"},
        ]
        inspect_results = [
            [{"type": "closing_cutoff", "detail": "Closing may be cut off"}],
        ]

        with (
            patch("scripts.render_pdf.compile_tex", side_effect=compile_results),
            patch("scripts.render_pdf._inspect_pdf", side_effect=inspect_results),
            patch("scripts.render_pdf.get_pdf_pages", return_value=1),
            patch("scripts.render_pdf._apply_fixes", return_value=[]),  # No fixes
        ):
            result = compile_and_inspect("/tmp/cl.tex", "cover_letter", max_retries=3)
            # Should have the issue logged and returned
            assert len(result.get("issues", [])) >= 1


class TestPageCountIntegration:
    """Verify pdfinfo integration works with real PDF tools."""

    def test_get_pdf_pages_real(self):
        """get_pdf_pages returns page count for a real PDF."""
        from scripts.render_pdf import get_pdf_pages

        # Use the pre-compiled resume.pdf in templates/
        resume_pdf = PROJECT_ROOT / "templates" / "resume.pdf"
        if resume_pdf.exists():
            pages = get_pdf_pages(str(resume_pdf))
            assert pages is not None
            assert isinstance(pages, int)
            assert pages > 0
            print(f"Real resume.pdf has {pages} page(s)")

    def test_get_pdf_text_real(self):
        """get_pdf_text extracts text from a real PDF."""
        from scripts.render_pdf import get_pdf_text

        resume_pdf = PROJECT_ROOT / "templates" / "resume.pdf"
        if resume_pdf.exists():
            text = get_pdf_text(str(resume_pdf))
            assert text is not None
            assert len(text) > 100
            assert "Rodrigo Lopes" in text
            print(f"Extracted {len(text)} chars from resume.pdf")


class TestNeedspaceInTemplate:
    """Verify the LaTeX template has needspace package."""

    def test_needspace_in_resume_template(self):
        """resume.tex should include \\usepackage{needspace}."""
        template_path = PROJECT_ROOT / "templates" / "resume.tex"
        content = template_path.read_text()
        assert "\\usepackage{needspace}" in content, (
            "resume.tex must include \\usepackage{needspace}"
        )
