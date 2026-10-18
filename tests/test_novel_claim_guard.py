"""Live Pilot Hotfix H1: novel-claim grounding on the final resume.

Reproduces the Clickboat failure and pins the fix.

The failed pilot (run ``Clickboat_2026-10-06T214324_f61820``) shipped a resume
asserting Postscript work on *"technical optimization of LLM-driven search
discovery"* and *"site architecture"* while the canonical master resume
contained no occurrence of ``search``, ``seo``, ``architecture`` or ``index``.
The tailoring brief invented the phrase, the writer inserted it, the reviewer
extended it, and the ATS stage then reported it as covered - circular
certification. Every deterministic guard returned PASS.

These tests prove that:

  * the exact pilot regression now HOLDs;
  * a claim introduced by the reviewer or by the grounded ATS edits cannot
    bypass the guard, because it runs on the FINAL accepted artifact;
  * a term that exists only in the job description is never treated as evidence;
  * harmless rewording, reordering, shortening and punctuation changes are
    never flagged;
  * candidate-supported claims, including skills that live only in the
    canonical skills inventory, still pass;
  * the check is deterministic, consults no LLM, and never promotes to
    ``applied``.
"""

import io
import sys
from pathlib import Path
from typing import cast

import pytest
from rich.console import Console

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import modules.pipeline as pipeline  # noqa: E402
from modules import sendability  # noqa: E402
from modules.parsers import (  # noqa: E402
    apply_grounded_ats_edits,
    apply_safe_latex_replacement,
    build_evidence_corpus,
    find_unsupported_claims,
)

TEMPLATE = (PROJECT_ROOT / "templates" / "resume.tex").read_text()
MASTER = (PROJECT_ROOT / ".master_resume_cache_2f40fd98.txt").read_text()
EVIDENCE = build_evidence_corpus(master_resume=MASTER, canonical_template=TEMPLATE)

RUN_ID = "Clickboat_2026-10-06T214324_f61820"
EVALUATED_AT = "2026-10-06T20:00:00+00:00"

# The exact clause the failed pilot inserted into the Postscript bullet.
POSTSCRIPT_ANCHOR = "predictive analytics tested them against live subscriber segments"
FABRICATED_POSTSCRIPT = (
    "predictive evaluation against live subscriber segments, and technical "
    "optimization of LLM-driven search discovery, and site architecture"
)
CLICKBOAT_FABRICATED_RESUME = TEMPLATE.replace(
    POSTSCRIPT_ANCHOR, FABRICATED_POSTSCRIPT
)


class _ExplodingLLM:
    """Any attribute access proves the guard consulted an LLM."""

    def __getattr__(self, name):  # pragma: no cover - only runs on failure
        raise AssertionError(f"sendability must not touch the LLM (accessed .{name})")


def _console() -> Console:
    return Console(file=io.StringIO())


def evaluate(**overrides) -> dict:
    """Evaluate a fabricated/clean artifact through the real gate."""
    inputs = {
        "run_id": RUN_ID,
        "final_latex": TEMPLATE,
        "resume_artifact_present": True,
        "resume_artifact_bytes": len(TEMPLATE),
        "pdf_present": True,
        "pdf_bytes": 4096,
        "master_resume": MASTER,
        "canonical_template": TEMPLATE,
        "tailoring_mode": sendability.TAILORING_TARGETED,
        "tailoring_outcome": sendability.TAILORING_OUTCOME_TAILORED,
        "evaluated_at": EVALUATED_AT,
    }
    inputs.update(overrides)
    return sendability.evaluate_sendability(**inputs)


def _terms(latex: str, evidence: str = EVIDENCE) -> set[str]:
    return {item["term"] for item in find_unsupported_claims(latex, evidence)}


# ── 1-2: the exact regression ───────────────────────────────────────────────


class TestClickboatRegression:
    def test_exact_pilot_artifact_holds(self):
        """Required behaviour 1: the shipped Clickboat resume must now HOLD."""
        result = evaluate(
            final_latex=CLICKBOAT_FABRICATED_RESUME,
            resume_artifact_bytes=len(CLICKBOAT_FABRICATED_RESUME),
        )
        assert result["status"] == sendability.HOLD
        assert result["checks"]["unsupported_novel_claim"] == "FAIL"
        assert [b["code"] for b in result["blockers"]] == [
            sendability.BLOCK_UNSUPPORTED_NOVEL_CLAIM
        ]

    def test_both_fabricated_terms_are_named_in_the_blocker(self):
        result = evaluate(
            final_latex=CLICKBOAT_FABRICATED_RESUME,
            resume_artifact_bytes=len(CLICKBOAT_FABRICATED_RESUME),
        )
        detail = result["blockers"][0]["detail"]
        assert "search discovery" in detail
        assert "site architecture" in detail

    def test_the_two_fabrications_are_exactly_what_is_flagged(self):
        """Precision: the real defect and nothing else."""
        assert _terms(CLICKBOAT_FABRICATED_RESUME) == {
            "search discovery",
            "site architecture",
        }

    def test_clean_canonical_resume_is_never_flagged(self):
        """No false positive on the real, fully grounded artifact."""
        assert find_unsupported_claims(TEMPLATE, EVIDENCE) == []
        assert evaluate()["status"] == sendability.READY_TO_SEND

    def test_jd_only_domain_inserted_into_postscript_holds(self):
        """Required behaviour 2: a JD-shaped domain absent from evidence HOLDs."""
        fabricated = TEMPLATE.replace(
            POSTSCRIPT_ANCHOR,
            POSTSCRIPT_ANCHOR + ", owning lifecycle marketing for the platform",
        )
        assert "lifecycle marketing" in _terms(fabricated)
        result = evaluate(
            final_latex=fabricated, resume_artifact_bytes=len(fabricated)
        )
        assert result["status"] == sendability.HOLD


# ── 3-4: no stage may certify its own inserted claim ────────────────────────


class TestLaterStagesCannotBypass:
    def test_reviewer_introduced_claim_holds(self):
        """Required behaviour 3: the applied reviewer edit is caught at the gate."""
        edited = apply_safe_latex_replacement(
            TEMPLATE,
            POSTSCRIPT_ANCHOR,
            POSTSCRIPT_ANCHOR + ", and site architecture",
        )
        assert edited != TEMPLATE, "precondition: the reviewer edit was applied"
        assert "site architecture" in edited

        result = evaluate(final_latex=edited, resume_artifact_bytes=len(edited))
        assert result["status"] == sendability.HOLD
        assert result["checks"]["unsupported_novel_claim"] == "FAIL"

    def test_ats_introduced_claim_holds_despite_grounded_keyword(self):
        """Required behaviour 4: the circular-certification hole is closed.

        ``apply_grounded_ats_edits`` grounds the edit's ``keyword`` against the
        master resume. In the Clickboat pilot the keyword was ``AI`` (present)
        while the inserted text asserted a novel capability, so the edit was
        applied and the ATS report then listed that capability as covered. The
        gate must catch it on the final artifact.
        """
        edits = [
            {
                "keyword": "AI",
                "type": "keyword_promote",
                "current_text": "AI-powered products",
                "suggested_text": "AI-powered products and site architecture",
                "rationale": "JD asks for site architecture",
            }
        ]
        updated, applied, _skipped = apply_grounded_ats_edits(
            TEMPLATE, edits, MASTER, targeted=True
        )
        assert applied == 1, "precondition: the ATS edit is applied by the pipeline"
        assert "site architecture" in updated

        result = evaluate(final_latex=updated, resume_artifact_bytes=len(updated))
        assert result["status"] == sendability.HOLD
        assert "site architecture" in result["blockers"][0]["detail"]

    def test_jd_terms_are_never_evidence(self):
        """A skill the posting demands but the candidate never did is not proof."""
        fabricated = TEMPLATE + "\n\\item Ran demand generation programmes.\n"
        # Not flagged as a domain term when the JD never named it...
        result = evaluate(
            final_latex=fabricated, resume_artifact_bytes=len(fabricated)
        )
        assert result["status"] == sendability.HOLD  # lexicon catches it
        # ...and explicitly flagged when the pipeline extracted it from the JD.
        jd_result = evaluate(
            final_latex=fabricated,
            resume_artifact_bytes=len(fabricated),
            jd_skill_terms=("Demand generation",),
        )
        assert jd_result["status"] == sendability.HOLD
        assert "demand generation" in jd_result["blockers"][0]["detail"]


# ── 5: metrics ─────────────────────────────────────────────────────────────


class TestMetrics:
    def test_unsupported_new_metric_holds(self):
        """Required behaviour 5."""
        assert "123%" not in EVIDENCE.lower()
        fabricated = TEMPLATE + "\n\\item Increased revenue by 123\\%.\n"
        findings = find_unsupported_claims(fabricated, EVIDENCE)
        assert [f["kind"] for f in findings] == ["metric"]
        assert findings[0]["term"] == "123%"
        result = evaluate(
            final_latex=fabricated, resume_artifact_bytes=len(fabricated)
        )
        assert result["status"] == sendability.HOLD

    def test_supported_metric_is_allowed(self):
        """Required behaviour: an evidenced metric is untouched."""
        assert "35%" in MASTER  # canonical evidence
        grounded = TEMPLATE + "\n\\item Reduced order completion time by 35\\%.\n"
        assert find_unsupported_claims(grounded, EVIDENCE) == []
        result = evaluate(final_latex=grounded, resume_artifact_bytes=len(grounded))
        assert result["status"] == sendability.READY_TO_SEND


# ── 6-7: supported claims remain allowed ───────────────────────────────────


class TestSupportedClaimsAllowed:
    def test_supported_term_already_in_canonical_evidence_is_allowed(self):
        """Required behaviour 6."""
        assert "brand center" in MASTER.lower()
        grounded = TEMPLATE + "\n\\item Used Brand Center for voice control.\n"
        assert find_unsupported_claims(grounded, EVIDENCE) == []

    def test_supported_skill_from_skills_inventory_is_allowed(self):
        """Required behaviour 7: the canonical inventory is authoritative."""
        term = "klaviyo"
        assert term not in (MASTER + TEMPLATE).lower(), "precondition"
        resume = TEMPLATE + f"\n\\item Built lifecycle flows in {term}.\n"

        without_inventory = find_unsupported_claims(resume, EVIDENCE)
        assert [f["term"] for f in without_inventory] == [term]

        with_inventory = build_evidence_corpus(
            master_resume=MASTER,
            canonical_template=TEMPLATE,
            skills_inventory=f"{term.title()} | tool | expert | high",
        )
        assert find_unsupported_claims(resume, with_inventory) == []


# ── 8-11: harmless edits must never be flagged ─────────────────────────────


class TestHarmlessEditsAllowed:
    def test_grammatical_rewording_is_allowed(self):
        """Required behaviour 8."""
        reworded = TEMPLATE.replace(
            "Owned post-launch product direction and iteration of Infinity Testing",
            "Led the post-launch product direction and iteration of Infinity Testing",
        )
        assert reworded != TEMPLATE
        assert find_unsupported_claims(reworded, EVIDENCE) == []
        assert evaluate(
            final_latex=reworded, resume_artifact_bytes=len(reworded)
        )["status"] == sendability.READY_TO_SEND

    def test_punctuation_only_change_is_allowed(self):
        """Required behaviour 9."""
        punctuated = TEMPLATE.replace(
            "Brand Center as the brand-voice control layer",
            "Brand Center as the brand voice control layer,",
        )
        assert punctuated != TEMPLATE
        assert find_unsupported_claims(punctuated, EVIDENCE) == []

    def test_sentence_reordering_is_allowed(self):
        """Required behaviour 10: no new facts, only order."""
        original = (
            "Built analytics instrumentation at platform scale across 18,000+ merchants."
        )
        reordered = TEMPLATE.replace(original, "") .replace(
            "\\section*{Skills",
            original + "\n\n\\section*{Skills",
            1,
        )
        assert reordered != TEMPLATE
        assert find_unsupported_claims(reordered, EVIDENCE) == []

    def test_shortening_an_existing_claim_is_allowed(self):
        """Required behaviour 11."""
        shortened = TEMPLATE.replace(
            "across growth, B2C e-commerce, B2B platforms, and AI-powered products",
            "across growth and B2C e-commerce",
        )
        assert shortened != TEMPLATE
        assert find_unsupported_claims(shortened, EVIDENCE) == []

    def test_morphological_variant_of_a_grounded_term_is_allowed(self):
        """Evidence says "A/B tests"; claiming "A/B testing" is not novel."""
        assert "a/b test" in MASTER.lower()
        resume = TEMPLATE + "\n\\item Ran A/B testing programmes.\n"
        assert find_unsupported_claims(resume, EVIDENCE) == []

    def test_multi_word_term_needs_a_contiguous_evidence_phrase(self):
        """Common constituent words elsewhere do not ground a novel phrase."""
        assert "lifecycle" in MASTER.lower()
        assert "market" in MASTER.lower()
        assert "lifecycle marketing" not in MASTER.lower()
        resume = TEMPLATE + "\n\\item Owned lifecycle marketing.\n"
        assert "lifecycle marketing" in _terms(resume)


# ── 12-14: artifact truthfulness, lifecycle, determinism ───────────────────


class TestGateWiringAndLifecycle:
    def test_final_artifact_is_what_gets_evaluated(self):
        """Required behaviour 12: a clean reference cannot mask a dirty final."""
        result = evaluate(
            final_latex=CLICKBOAT_FABRICATED_RESUME,
            resume_artifact_bytes=len(CLICKBOAT_FABRICATED_RESUME),
            tailoring_noop_reference=TEMPLATE,  # clean run baseline
        )
        assert result["status"] == sendability.HOLD

    def test_hold_maps_to_generated(self):
        """Required behaviour 13."""
        assert sendability.promoted_tracker_status(sendability.HOLD) == "generated"

    def test_no_path_can_produce_applied(self):
        """Required behaviour 14."""
        for status in sendability.SENDBILITY_STATUSES:
            assert sendability.promoted_tracker_status(status) != "applied"
            for existing in (None, "generated", "ready_to_apply", "applied"):
                resolved = sendability.resolve_tracker_status(existing, "ready_to_apply")
                if existing != "applied":
                    assert resolved != "applied"

    def test_guard_is_deterministic(self):
        first = find_unsupported_claims(CLICKBOAT_FABRICATED_RESUME, EVIDENCE)
        second = find_unsupported_claims(CLICKBOAT_FABRICATED_RESUME, EVIDENCE)
        assert first == second

    def test_missing_evidence_skips_rather_than_guesses(self):
        """Without a master resume the integrity check already blocks."""
        result = evaluate(master_resume=None)
        assert result["status"] == sendability.HOLD
        assert [b["code"] for b in result["blockers"]] == [
            sendability.BLOCK_INTEGRITY_UNVERIFIABLE
        ]
        assert result["checks"]["unsupported_novel_claim"] == "SKIPPED"

    def test_production_step_supplies_evidence_and_holds(self, tmp_path, monkeypatch):
        """The guard is wired into the real gate, not opt-in by accident."""
        run_dir = tmp_path / RUN_ID
        run_dir.mkdir()
        tex = run_dir / "Resume_Rodrigo-Lopes.tex"
        tex.write_text(CLICKBOAT_FABRICATED_RESUME)
        pdf = run_dir / "Resume_Rodrigo-Lopes.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path, raising=False)
        ctx = {
            "run_dir": str(run_dir),
            "run_id": run_dir.name,
            "tex_path": str(tex),
            "pdf_path": str(pdf),
            "master_resume": MASTER,
            "tailoring_mode": "targeted",
            "tailoring_outcome": "tailored",
            "job": {
                "company": "Clickboat",
                "title": "Senior Product Manager",
                "required_skills": ["Technical SEO", "Site architecture"],
            },
        }
        pipeline.step_evaluate_sendability(
            ctx, cast(pipeline.LLMClient, _ExplodingLLM()), _console()
        )

        assert ctx["sendability"]["status"] == sendability.HOLD
        codes = [b["code"] for b in ctx["sendability"]["blockers"]]
        assert sendability.BLOCK_UNSUPPORTED_NOVEL_CLAIM in codes
        assert ctx["sendability"]["checks"]["unsupported_novel_claim"] == "FAIL"
        # Tracker mapping stays forward-only and never "applied".
        assert (
            sendability.promoted_tracker_status(ctx["sendability"]["status"])
            == "generated"
        )

    def test_production_step_passes_evidence_parameters(self):
        """Wiring guard: the caller must supply the evidence corpus."""
        source = (PROJECT_ROOT / "modules" / "pipeline.py").read_text()
        for param in (
            "skills_inventory=ctx.get",
            "career_config=_career_config_evidence()",
            "story_bank=_load_story_bank_evidence()",
            "jd_skill_terms=_jd_skill_terms(ctx)",
        ):
            assert param in source, param


@pytest.mark.parametrize(
    "term",
    ["technical seo", "seo", "search discovery", "site architecture", "indexing"],
)
def test_each_clickboat_family_term_is_flagged(term):
    """Every term the brief tried to insert is treated as a claim."""
    resume = TEMPLATE + f"\n\\item Owned {term} for the platform.\n"
    assert term in _terms(resume)


# ── Post-review P1 fixes: precision, recall and advisory semantics ─────────


class TestMetricGroundingPrecision:
    def test_fabricated_metric_is_not_satisfied_by_a_longer_evidenced_one(self):
        """5% must never be grounded by an evidenced 45%."""
        assert "45%" in MASTER
        resume = TEMPLATE + "\n\\item Lifted conversion by 5\\%.\n"
        assert [f["term"] for f in find_unsupported_claims(resume, EVIDENCE)] == ["5%"]

    def test_fabricated_scale_count_is_not_satisfied_by_a_larger_evidenced_one(self):
        assert "18,000+" in MASTER
        resume = TEMPLATE + "\n\\item Scaled to 8,000+ merchants.\n"
        assert "8,000+" in _terms(resume)

    def test_notation_variants_of_an_evidenced_metric_are_allowed(self):
        """Formatting churn must never be mistaken for a new claim."""
        for old, new in (
            ("28\\%", "28 percent"),
            ("22 points", "22 pts."),
            ("45\\%", "45 %"),
        ):
            assert old in TEMPLATE, old
            assert find_unsupported_claims(TEMPLATE.replace(old, new, 1), EVIDENCE) == [], old


class TestStemToleranceIsSafe:
    @pytest.mark.parametrize("tool", ["Braze", "Optimizely", "Iterable"])
    def test_unrelated_tool_name_is_not_grounded_by_a_similar_word(self, tool):
        """'braze' must not be grounded by 'brazil', nor 'optimizely' by 'optimization'."""
        resume = TEMPLATE + f"\n\\item Built lifecycle flows in {tool}.\n"
        assert tool.lower() in _terms(resume)

    def test_documented_morphological_variant_rule_actually_holds(self):
        """The docstring's own examples must be true."""
        from modules.parsers import _term_is_grounded

        assert _term_is_grounded(
            "roadmapping", "prioritize a re-engagement automation roadmap"
        )
        assert _term_is_grounded(
            "a/b testing", "running iterative a/b tests on payment methods"
        )
        assert not _term_is_grounded("braze", "operations across mexico and brazil")


class TestLexiconFamilyCoverage:
    @pytest.mark.parametrize(
        "phrase",
        [
            "search engine optimisation",
            "search engine optimization",
            "index coverage",
            "crawl budget",
            "search and discovery",
        ],
    )
    def test_rephrased_versions_of_the_defect_family_are_flagged(self, phrase):
        resume = TEMPLATE + f"\n\\item Owned {phrase} for the platform.\n"
        assert find_unsupported_claims(resume, EVIDENCE) != []

    def test_dotted_acronym_is_normalised(self):
        resume = TEMPLATE + "\n\\item Owned S.E.O. for the platform.\n"
        assert "seo" in _terms(resume)


class TestUnmarkedNumericClaims:
    @pytest.mark.parametrize(
        "phrase",
        [
            "12+ years of experience",
            "a team of 25 engineers",
            "Doubled revenue",
            "4x growth",
        ],
    )
    def test_claim_shaped_numbers_are_grounded(self, phrase):
        resume = TEMPLATE + f"\n\\item {phrase} delivered.\n"
        assert find_unsupported_claims(resume, EVIDENCE) != []

    def test_evidenced_canonical_numbers_are_allowed(self):
        assert "8+ years" in TEMPLATE and "hundreds of" in TEMPLATE
        assert find_unsupported_claims(TEMPLATE, EVIDENCE) == []


class TestJdWordingIsAdvisoryNotBlocking:
    def test_supported_jd_wording_never_holds_the_run(self):
        """Mirroring the posting's vocabulary is tailoring, not fabrication."""
        resume = TEMPLATE.replace(
            "and AI-powered products", "and AI/LLM-driven traffic acquisition"
        )
        result = evaluate(
            final_latex=resume,
            resume_artifact_bytes=len(resume),
            jd_skill_terms=(
                "Product Management",
                "Traffic Acquisition",
                "Marketing Strategy",
            ),
        )
        assert result["status"] == sendability.READY_WITH_WARNINGS
        assert result["blockers"] == []
        assert sendability.WARN_JD_ONLY_KEYWORDS in [
            w["code"] for w in result["warnings"]
        ]

    def test_the_actual_fabrication_still_blocks(self):
        """Demoting the advisory path must not weaken H1."""
        result = evaluate(
            final_latex=CLICKBOAT_FABRICATED_RESUME,
            resume_artifact_bytes=len(CLICKBOAT_FABRICATED_RESUME),
            jd_skill_terms=("Traffic Acquisition",),
        )
        assert result["status"] == sendability.HOLD
        assert result["blockers"][0]["code"] == sendability.BLOCK_UNSUPPORTED_NOVEL_CLAIM
