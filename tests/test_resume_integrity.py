"""Regression tests for resume tailoring factual integrity."""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.parsers import (  # noqa: E402
    apply_grounded_ats_edits,
    apply_safe_latex_replacement,
    extract_locked_experience_blocks,
    locked_experience_drift,
    validate_resume_draft,
    validate_resume_edits,
)

MASTER = (PROJECT_ROOT / ".master_resume_cache_2f40fd98.txt").read_text()
TEMPLATE = (PROJECT_ROOT / "templates" / "resume.tex").read_text()


def errors_for_edits(edits: dict) -> list[str]:
    return validate_resume_edits(edits, MASTER)


def test_rejects_pls_fabrication():
    errors = errors_for_edits({"summary_bullet": "Led PLG and PLS motions for B2B workflow products."})
    assert any("PLS" in error for error in errors)


def test_rejects_usage_based_pricing_fabrication():
    errors = errors_for_edits({"summary_bullet": "Owned usage-based pricing expansion."})
    assert any("pricing" in error.lower() for error in errors)


def test_rejects_broad_18000_scope():
    errors = errors_for_edits({"summary_bullet": "Scaled tools for 18,000+ merchants."})
    assert any("18,000" in error for error in errors)


def test_rejects_28_percent_without_campaign_scope():
    errors = errors_for_edits({"summary_bullet": "Delivered a 28% earnings-per-message lift."})
    assert any("Infinity Testing campaigns" in error for error in errors)


def test_rejects_forvia_personal_attribution():
    draft = TEMPLATE.replace(
        "The unified catalog delivered €12M+ in first-year cross-sell revenue.",
        "delivering €12M+ in first-year cross-sell revenue.",
    )
    errors = validate_resume_draft(draft, MASTER)
    assert any("unified catalog" in error.lower() for error in errors)


def test_rejects_agentic_workflows_skill():
    errors = errors_for_edits({
        "skills": [{"category": "AI & ML", "content": "LLM Evaluation, Agentic Workflows"}]
    })
    assert any("Agentic Workflows" in error for error in errors)


def test_rejects_jd_partial_signup_contamination():
    errors = errors_for_edits({
        "postscript_bullets": [
            "Redesigned the acquisition journey from partial sign-up to first value."
        ]
    })
    assert any("partial sign-up" in error for error in errors)


def test_rejects_postscript_anchor_loss():
    draft = TEMPLATE.replace(
        "Used Brand Center as the brand-voice control layer and preserved merchant review before activation",
        "Optimized message variants",
    )
    errors = validate_resume_draft(draft, MASTER)
    assert any("Brand Center" in error or "merchant review" in error for error in errors)


def test_safe_reviewer_replacement_escapes_percent():
    result = apply_safe_latex_replacement(
        "\\item Old bullet.",
        "Old bullet.",
        "Increased conversion by 32% and reduced cost by 18%.",
    )
    assert "32\\%" in result
    assert "18\\%" in result
    assert "32%" not in result


def test_rejects_unescaped_percent_before_pdf():
    draft = TEMPLATE.replace("32\\%", "32%", 1)
    errors = validate_resume_draft(draft, MASTER)
    assert any("unescaped" in error.lower() and "%" in error for error in errors)


def test_locked_experience_blocks_cover_forvia_accenture_ca():
    blocks = extract_locked_experience_blocks(TEMPLATE)
    assert set(blocks) == {"FORVIA HELLA", "Accenture Brasil", "C&A Brasil"}
    assert locked_experience_drift(TEMPLATE, TEMPLATE) == []


def test_reviewer_edit_to_accenture_rejected_in_targeted_mode(monkeypatch):
    monkeypatch.setenv("TARGETED_EDITS", "1")

    from modules.pipeline import step_apply_review
    from rich.console import Console

    original_accenture = extract_locked_experience_blocks(TEMPLATE)["Accenture Brasil"]
    ctx = {
        "run_dir": str(PROJECT_ROOT / "output" / "LockTest_2026-09-29"),
        "company_safe": "LockTest",
        "master_resume": MASTER,
        "tailored_latex": TEMPLATE,
        "review_feedback": {
            "part_a": [
                {
                    "old_string": "Managed end-to-end checkout flow redesign (cart \u2192 payment \u2192 order confirmation)",
                    "new_string": "Owned the end-to-end user journey from sign-up to payment confirmation",
                    "reason": "test reframe",
                }
            ],
            "part_b": [],
        },
    }

    result = step_apply_review(ctx, None, Console())
    latex = result["tailored_latex"]

    assert "cart \u2192 payment \u2192 order confirmation" in latex
    assert "sign-up to payment confirmation" not in latex
    assert extract_locked_experience_blocks(latex)["Accenture Brasil"] == original_accenture


def test_ats_edit_to_forvia_rejected_in_targeted_mode():
    before = TEMPLATE
    edits = [
        {
            "keyword": "A/B testing",
            "type": "keyword_add",
            "current_text": "Led product roadmap for FORVIA HELLA's B2B e-commerce platform (60,000+ workshops)",
            "suggested_text": "Led product roadmap for FORVIA HELLA's B2B e-commerce platform (60,000+ workshops), optimizing conversion",
            "location": "FORVIA HELLA bullet 1",
            "rationale": "test reframe",
        }
    ]

    updated, applied, skipped = apply_grounded_ats_edits(before, edits, MASTER, targeted=True)

    assert applied == 0
    assert skipped == 1
    assert updated == before
    assert locked_experience_drift(before, updated) == []


def test_ats_edit_to_ca_rejected_in_targeted_mode():
    edits = [
        {
            "keyword": "A/B testing",
            "type": "keyword_add",
            "current_text": "As Product Manager, expanded ownership to the full Checkout \\& Payments vertical",
            "suggested_text": "As Product Manager, expanded ownership to the full Checkout \\& Payments vertical, driving growth",
            "location": "C&A Brasil bullet 2",
            "rationale": "test reframe",
        }
    ]

    updated, applied, skipped = apply_grounded_ats_edits(TEMPLATE, edits, MASTER, targeted=True)

    assert applied == 0
    assert skipped == 1
    assert updated == TEMPLATE
