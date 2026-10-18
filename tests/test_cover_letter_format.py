"""Cover-letter format regression tests (approved deterministic template).

Pins the approved layout:

* title ``Application for <role>, <company>`` (company appended exactly once,
  never the retired ``, at <company>`` duplication),
* city-only date line ``Berlin, DD.MM.YYYY`` (no country),
* explicit paragraph gaps (``\\vspace{10pt}``), because the document sets
  ``\\parskip`` to 0pt so blank lines alone add no visible space.

The body prose is explicitly out of scope: it must reach the artifact verbatim.
No test here makes a model call; the format step is pure rendering.

Run with: pytest tests/test_cover_letter_format.py -v
"""

import io
import re
import sys
from datetime import date as real_date
from pathlib import Path
from typing import Any, cast

import pytest
from rich.console import Console

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import modules.pipeline as pipeline  # noqa: E402
from scripts.render_pdf import get_pdf_pages, get_pdf_text  # noqa: E402

TEMPLATE = PROJECT_ROOT / "templates" / "cover_letter.tex"
TEX_NAME = "Cover-Letter_RodrigoLopes.tex"

# Shaped exactly like the live Click&Boat scrape.
CLICKBOAT_TITLE = "\n      Senior Product Manager – Traffic & Acquisition - Click&Boat\n    "
CLICKBOAT_COMPANY = "Clickboat"
CLICKBOAT_ROLE = "Senior Product Manager – Traffic & Acquisition"

BODY = (
    "Introductory observation about the business and the tension it is navigating.\n\n"
    "First body paragraph with the closest matching experience.\n\n"
    "Second body paragraph with the framework that transfers.\n\n"
    "Closing paragraph naming the challenge the role owns.\n"
)


class _StubLLM:
    """The format step must render only; any model call is a failure."""

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.3, **kwargs: Any) -> str:
        raise AssertionError("cover-letter formatting must not call a model")

    def model_name(self) -> str:
        return "stub/model"


class _FixedDate(real_date):
    @classmethod
    def today(cls) -> "_FixedDate":
        return cls(2026, 10, 13)


# ── Title construction ────────────────────────────────────────────


class TestTitleBuilder:
    @pytest.mark.parametrize(
        "title",
        [
            "Senior Product Manager - Traffic & Acquisition - Click&Boat",
            "Senior Product Manager - Traffic & Acquisition | Click&Boat",
            "Senior Product Manager - Traffic & Acquisition at Click&Boat",
            "Senior Product Manager - Traffic & Acquisition, Click&Boat",
        ],
    )
    def test_trailing_company_is_stripped_from_the_role(self, title):
        role, company = pipeline.split_role_and_company(title, CLICKBOAT_COMPANY)
        assert role == "Senior Product Manager - Traffic & Acquisition"
        assert company == "Click&Boat", "the posting's own spelling must win"

    def test_live_clickboat_title(self):
        role, company = pipeline.split_role_and_company(CLICKBOAT_TITLE, CLICKBOAT_COMPANY)
        assert role == CLICKBOAT_ROLE
        assert company == "Click&Boat"

    def test_role_without_company_suffix_is_untouched(self):
        role, company = pipeline.split_role_and_company(
            "Growth Product Manager - Activation", "ApprovalMax"
        )
        assert role == "Growth Product Manager - Activation"
        assert company == "ApprovalMax"

    def test_company_comparison_ignores_punctuation_and_case(self):
        role, company = pipeline.split_role_and_company(
            "Senior Product Manager - Click Boat", "ClickBoat"
        )
        assert role == "Senior Product Manager"
        assert company == "Click Boat"

    def test_only_one_trailing_segment_is_removed(self):
        role, company = pipeline.split_role_and_company(
            "Click&Boat - Senior PM - Click&Boat", "Clickboat"
        )
        assert role == "Click&Boat - Senior PM"
        assert company == "Click&Boat"


# ── Paragraph block ───────────────────────────────────────────────


class TestParagraphBlock:
    def test_gap_is_explicit_between_every_paragraph(self):
        block = pipeline.cover_letter_body_block(["one", "two", "three", "four"])
        assert block.count(pipeline.COVER_LETTER_PARAGRAPH_GAP) == 3
        assert block == (
            "one\n\n\\vspace{10pt}\n\ntwo\n\n\\vspace{10pt}\n\nthree\n\n\\vspace{10pt}\n\nfour"
        )

    def test_paragraph_text_is_preserved_verbatim(self):
        paragraphs = [p for p in BODY.split("\n\n") if p.strip()]
        block = pipeline.cover_letter_body_block(paragraphs)
        for paragraph in paragraphs:
            assert paragraph in block


# ── Approved template structure ───────────────────────────────────


class TestApprovedTemplate:
    @pytest.fixture(autouse=True)
    def template(self):
        return TEMPLATE.read_text()

    def test_title_line_and_no_at_company_duplication(self, template):
        assert "Application for {role_title}, {company}" in template
        assert ", at {company}" not in template

    def test_approved_spacing_values_and_order(self, template):
        for value in (r"\vspace{40pt}", r"\vspace{30pt}", r"\vspace{25pt}", r"\vspace{15pt}", r"\vspace{1pt}"):
            assert value in template, f"missing approved spacing {value}"
        assert r"\vspace{20pt}" not in template, "retired body-to-closing spacing still present"
        header, title, date, greeting = (
            template.index(r"\vspace{40pt}"),
            template.index(r"\vspace{30pt}"),
            template.index(r"\vspace{25pt}"),
            template.index("Dear Hiring Team"),
        )
        assert header < title < date < greeting

    def test_header_keeps_the_canonical_address_and_hyperlink(self, template):
        assert "12435, Berlin \\textbar{} +49 152 0359 3061" in template
        assert "\\href{mailto:contact@rodrigolopes.xyz}{contact@rodrigolopes.xyz}" in template

    def test_paragraph_spacing_is_not_left_to_blank_lines(self, template):
        assert "{company_paragraph}{body}" in template


# ── End to end (real template, real pdflatex, no model call) ──────


class TestClickboatFormatEndToEnd:
    @pytest.fixture
    def ctx(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "date", _FixedDate)
        monkeypatch.setattr("config.APPLICANT_LOCATION", "Berlin, Germany")
        run_dir = tmp_path / "Clickboat_2026-10-13T185130_559fe4"
        run_dir.mkdir()
        return {
            "generate_cover_letter": True,
            "cover_letter_body": BODY,
            "job": {"title": CLICKBOAT_TITLE, "company": CLICKBOAT_COMPANY},
            "run_dir": str(run_dir),
        }

    def _render(self, ctx: dict) -> str:
        pipeline.step_compile_cover_letter(
            ctx, cast(Any, _StubLLM()), Console(file=io.StringIO())
        )
        return (Path(ctx["run_dir"]) / TEX_NAME).read_text()

    def test_tex_has_approved_title_date_and_body(self, ctx):
        tex = self._render(ctx)
        assert "Application for Senior Product Manager – Traffic \\& Acquisition, Click\\&Boat" in tex
        assert "at Click&Boat" not in tex
        assert ", at Clickboat" not in tex
        assert "Berlin, 13.10.2026" in tex
        assert "Germany" not in tex
        # greeting gap + three inter-paragraph gaps
        assert tex.count(pipeline.COVER_LETTER_PARAGRAPH_GAP) == 4
        for paragraph in [p for p in BODY.split("\n\n") if p.strip()]:
            assert paragraph in tex

    def test_pdf_is_one_page_with_the_rendered_title(self, ctx):
        self._render(ctx)
        assert ctx["cover_letter_status"] == pipeline.STAGE_OK
        pdf = Path(ctx["cover_letter_pdf_path"])
        assert pdf.exists() and pdf.stat().st_size > 0
        assert get_pdf_pages(str(pdf)) == 1
        raw_text = get_pdf_text(str(pdf))
        assert raw_text is not None
        text = re.sub(r"\s+", " ", raw_text)
        assert "Application for Senior Product Manager – Traffic & Acquisition, Click&Boat" in text
        assert "Berlin, 13.10.2026" in text
        assert "Germany" not in text
        assert "Kind regards" in text
