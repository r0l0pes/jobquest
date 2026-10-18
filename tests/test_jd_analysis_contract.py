"""Pre-apply fix: the JD-analysis contract must not turn JD requirements into
candidate experience.

The live Clickboat pilot twice produced a tailoring brief that proposed inserting a
JD-required capability the candidate has no evidence for:

  * run 1 (``Clickboat_2026-10-06T214324_f61820``): "technical optimization of
    LLM-driven search discovery" (Postscript bullet), plus "technical SEO audits … page
    performance" (C&A) and "and site architecture" (Accenture). That run **predates the
    novel-claim guard**: its sendability report has no ``unsupported_novel_claim`` check
    and read READY_WITH_WARNINGS, so the fabrication shipped in the PDF.
  * run 2 (``Clickboat_2026-10-06T223436_50e8f4``): "Redesigned subscriber acquisition
    and landing page performance …" (Postscript). The guard HOLDed that one.

The planning stage should never have asked for either. These tests pin the *contract*
(never its byte content), plus the invariants that make it meaningful: the deterministic
guard is unchanged, and the prompt adds no LLM call.
"""

import inspect
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import modules.pipeline as pipeline  # noqa: E402
from modules import sendability  # noqa: E402
from modules.parsers import (  # noqa: E402
    CLAIM_DOMAIN_TERMS,
    build_evidence_corpus,
    find_unsupported_claims,
)

PROMPT = (PROJECT_ROOT / "prompts" / "jd_analysis.md").read_text()
PIPELINE_SOURCE = (PROJECT_ROOT / "modules" / "pipeline.py").read_text()
TEMPLATE = (PROJECT_ROOT / "templates" / "resume.tex").read_text()
MASTER = (PROJECT_ROOT / ".master_resume_cache_2f40fd98.txt").read_text()
EVIDENCE = build_evidence_corpus(master_resume=MASTER, canonical_template=TEMPLATE)

# The guard's lexicon is 112 terms; pin the floor so a silent shrink fails loudly.
LEXICON_FLOOR = 112
DEFECT_FAMILY = ("site architecture", "technical seo", "search discovery", "page performance", "indexing")


def _flatten(text: str) -> str:
    """Whitespace-normalised, lowercased, markdown-emphasis-free prompt text."""
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", text)).lower()


PROMPT_FLAT = _flatten(PROMPT)


def _contains(*phrases: str) -> bool:
    """True when every phrase appears in the flattened prompt."""
    return all(phrase.lower() in PROMPT_FLAT for phrase in phrases)


def _xml_fence_body() -> str:
    """The text inside the ```xml output template."""
    match = re.search(r"```xml(.*?)```", PROMPT, re.DOTALL)
    assert match, "the output template fence must exist"
    return match.group(1)


# ── 1-2: candidate evidence is authoritative; gaps stay gaps ────────────────


class TestEvidenceIsAuthoritative:
    def test_jd_requirements_are_not_candidate_evidence(self):
        """Required behaviour 1."""
        assert "candidate evidence is authoritative" in PROMPT_FLAT
        assert _contains(
            "only source of candidate evidence",
            "never evidence that the candidate has done something",
        )
        # The long-standing rule must survive the rewrite.
        assert "a jd requirement is never evidence by itself" in PROMPT_FLAT

    def test_jd_phrasing_is_not_licensed_for_candidate_claims(self):
        """Line 7 used to authorise JD phrases everywhere."""
        assert "exact phrases from both the jd and the resume" not in PROMPT_FLAT
        assert _contains(
            "exact phrases from the jd when stating what the employer wants",
            "exact phrases from the resume/evidence whenever describing the candidate",
        )

    def test_partial_and_gap_semantics_are_defined(self):
        """Required behaviour 2."""
        for label in ("strong", "partial", "indirect", "gap / not evidenced"):
            assert label in PROMPT_FLAT, label
        assert _contains(
            "forbid asserting the unsupported dimension",
            "make a gap disappear",
        )

    def test_partial_match_cannot_become_an_insertion_target(self):
        assert _contains("must not become a keyword-insertion target")
        assert "the unsupported dimension stays unstated" in PROMPT_FLAT

    def test_indirect_is_not_a_licence_to_assert_the_jd_dimension(self):
        assert _contains(
            "never a licence to assert the jd's dimension",
            'never "emphasise technical seo"',
        )

    def test_gap_priorities_have_a_recorded_slot(self):
        """A gap must be recordable, or it gets laundered into PARTIAL."""
        assert "match: strong / partial / indirect / gap" in PROMPT_FLAT
        assert _contains(
            "every priority gets an entry here",
            "no candidate evidence; do not claim this",
            "never hiding it from the writer",
        )

    def test_skills_inventory_mention_is_not_performed_work(self):
        assert _contains(
            "named only in the skills & tools inventory",
            "is not evidence of performing, owning or leading work in it",
        )

    def test_truncated_resume_context_is_not_a_gap(self):
        """Step 3a receives a structure summary, so 'not visible' != 'not evidenced'."""
        assert _contains(
            "structure summary",
            "a truncated or missing bullet is not a gap",
            "possible — confirm against the full master resume",
        )


# ── 3-5: insertion targets, forbidden conversion, Clickboat family ──────────


class TestInsertionTargetsRequireEvidence:
    def test_insertions_must_cite_evidence_that_contains_the_claim(self):
        """Required behaviour 3: citation presence is not enough; it must entail."""
        assert 'evidence: "[verbatim master-resume quote this change is based on]"' in PROMPT_FLAT
        assert _contains(
            "must cite the candidate evidence it is based on",
            "every capability, discipline, tool, channel or domain noun in the new phrase must appear in the cited evidence",
            "a proposal whose evidence does not contain the words it asserts is invalid",
        )

    def test_insertion_trigger_is_evidence_not_jd_keywords(self):
        """The JD-keyword-driven framing — and its reward — are gone."""
        assert "jd keywords are missing or underemphasized" not in PROMPT_FLAT
        assert "what keyword is being added" not in PROMPT_FLAT
        # The measured root cause: keyword coverage was an acceptance criterion.
        assert "improving keyword coverage" not in PROMPT_FLAT
        assert _contains(
            "existing candidate achievement that is underemphasised",
            "the trigger is candidate evidence that deserves more prominence",
            "a proposal justified by keyword coverage rather than by the cited evidence is invalid",
        )

    def test_each_target_is_tagged_with_its_priority_and_match_label(self):
        assert "priority n (match: strong|partial|indirect)" in PROMPT_FLAT

    def test_skip_instructions_are_consolidated_and_unambiguous(self):
        assert "skip — no candidate evidence" not in PROMPT_FLAT
        assert PROMPT_FLAT.count("skip — no natural fit") == 0
        assert _contains("omit the entry entirely", "do not emit a placeholder")

    def test_prompt_prohibits_fabricating_capabilities_to_close_gaps(self):
        """Required behaviour 4."""
        assert "never convert a jd requirement into candidate experience" in PROMPT_FLAT
        assert _contains(
            'wrong: "optimized technical seo and site architecture"',
            'wrong: "improved landing page performance"',
            'wrong: "optimised search and discovery"',
            "being asked for a capability is not evidence of having it",
        )

    def test_clickboat_family_is_the_regression_example(self):
        """Required behaviour 5."""
        assert _contains(
            "technical seo / site architecture",
            "indexing",
            "page performance",
            "search and discovery",
            "landing page performance",
            "technical architecture",
        )

    def test_allowed_alternatives_are_stated(self):
        assert _contains(
            "emphasise the existing analytics, funnel and experimentation work",
            "state plainly that technical seo / site architecture is a gap",
            "omit the unsupported jd terminology from resume-edit proposals entirely",
        )

    def test_the_forbidden_block_lives_outside_the_output_template(self):
        """Run 2's brief echoed in-fence instruction text into its own output, and the
        brief is injected verbatim into the writer's prompt."""
        fence = _xml_fence_body()
        assert "WRONG:" not in fence
        assert "wrong:" not in _flatten(fence)
        assert "landing page performance" not in _flatten(fence)
        # It must still exist, in the Rules section.
        rules = PROMPT[PROMPT.find("## Rules"):]
        assert "Never convert a JD requirement into candidate experience" in rules

    def test_summary_language_must_come_from_evidence(self):
        assert "[exact phrase from jd or resume]" not in PROMPT_FLAT
        assert "[exact phrase from the resume/evidence]" in PROMPT_FLAT
        assert _contains(
            "the language and every capability claim must come from the candidate's evidence",
            "never write a summary sentence that asserts a discipline, tool, channel or domain",
            "theme labels must name an evidence dimension",
        )


# ── 6: useful tailoring is preserved ───────────────────────────────────────


class TestUsefulTailoringPreserved:
    def test_supported_tailoring_is_explicitly_permitted(self):
        """Required behaviour 6."""
        assert _contains(
            "keep tailoring strong where evidence exists",
            "not a request for a generic resume",
            "safe factual reframing is expected and encouraged",
            "literal wording equality with the evidence is not required",
        )
        for supported in ("experimentation", "analytics", "acquisition", "lifecycle", "payments"):
            assert supported in PROMPT_FLAT, supported

    def test_the_foreground_list_is_bounded_by_evidence(self):
        """The old list named domains with zero evidence hits (marketplace, CRM)."""
        assert "the evidence decides which dimensions exist, not this list" in PROMPT_FLAT
        for unevidenced in ("marketplace", "crm"):
            assert unevidenced not in _flatten(
                PROMPT[PROMPT.find("6. **Keep tailoring strong"):]
            ), unevidenced

    def test_reframing_within_source_vocabulary_is_allowed(self):
        assert "reframing within the source experience's own vocabulary" in PROMPT_FLAT

    def test_rule_one_example_is_annotated_as_employer_side(self):
        """Rule 1's positive example named the very family run 2 fabricated."""
        rules = PROMPT[PROMPT.find("## Rules"):]
        assert "never what the candidate has done" in rules


# ── 7: the deterministic guard is untouched ────────────────────────────────


class TestGuardUnchanged:
    def test_blocker_code_is_intact(self):
        """Required behaviour 7: the guard was not demoted or renamed."""
        assert sendability.BLOCK_UNSUPPORTED_NOVEL_CLAIM == "UNSUPPORTED_NOVEL_CLAIM"

    def test_lexicon_was_not_shrunk_and_covers_the_defect_family(self):
        assert len(CLAIM_DOMAIN_TERMS) >= LEXICON_FLOOR, (
            f"lexicon shrank to {len(CLAIM_DOMAIN_TERMS)} (floor {LEXICON_FLOOR})"
        )
        for term in DEFECT_FAMILY:
            assert term in CLAIM_DOMAIN_TERMS, term

    def test_no_job_specific_whitelist_was_added(self):
        """The guard must stay job-agnostic: no company in the lexicon, no job input."""
        assert "clickboat" not in " ".join(CLAIM_DOMAIN_TERMS).lower()
        params = inspect.signature(find_unsupported_claims).parameters
        assert set(params) == {"latex", "evidence_text", "jd_skill_terms"}

    def test_the_clickboat_fabrication_still_holds(self):
        """Behavioural proof: the prompt fix did not weaken the guard."""
        fabricated = TEMPLATE.replace(
            "predictive analytics tested them against live subscriber segments",
            "predictive evaluation against live subscriber segments, and technical "
            "optimization of LLM-driven search discovery, and site architecture",
        )
        assert fabricated != TEMPLATE, "fixture anchor missing from the template"
        findings = find_unsupported_claims(fabricated, EVIDENCE)
        # Subset, not equality: strengthening the lexicon must not break this.
        assert {"search discovery", "site architecture"} <= {
            str(f["term"]) for f in findings if f.get("blocking")
        }
        verdict = sendability.evaluate_sendability(
            run_id="regression",
            final_latex=fabricated,
            resume_artifact_present=True,
            resume_artifact_bytes=len(fabricated),
            pdf_present=True,
            pdf_bytes=1024,
            master_resume=MASTER,
            canonical_template=TEMPLATE,
            tailoring_mode=sendability.TAILORING_TARGETED,
            tailoring_outcome=sendability.TAILORING_OUTCOME_TAILORED,
        )
        assert verdict["status"] == sendability.HOLD
        assert sendability.BLOCK_UNSUPPORTED_NOVEL_CLAIM in [
            b["code"] for b in verdict["blockers"]
        ]

    def test_pristine_artifact_is_still_clean(self):
        assert find_unsupported_claims(TEMPLATE, EVIDENCE) == []


# ── 8: no additional LLM call ──────────────────────────────────────────────


class TestNoAdditionalLlmCall:
    def test_prompt_is_loaded_once_and_reuses_the_existing_client(self):
        """The change is prompt text only; the tailoring path is unchanged."""
        assert PIPELINE_SOURCE.count('_load_prompt("jd_analysis")') == 1
        step_source = inspect.getsource(pipeline.step_tailor_resume)
        assert step_source.count("create_tailor_client()") == 1
        # The prompt is data, not code: it can add no call of its own.
        assert not re.search(r"httpx|requests|api_key|create_client|openai|genai", PROMPT, re.I)

    def test_the_test_file_reads_the_same_prompt_the_pipeline_loads(self):
        """Guard against the tests pinning a different file than production uses."""
        assert pipeline.PROMPTS_DIR / "jd_analysis.md" == PROJECT_ROOT / "prompts" / "jd_analysis.md"
        assert pipeline._load_prompt("jd_analysis") == PROMPT

    def test_prompt_is_pure_text_and_still_structured(self):
        """The analysis structure was preserved, not replaced."""
        for section in (
            "<brief>",
            "<role_diagnosis>",
            "<top_priorities>",
            "<candidate_matches>",
            "<bullet_insertion_targets>",
            "<summary_strategy>",
            "<do_not_change>",
            "<de_emphasize>",
        ):
            assert section in PROMPT, section
