"""Cover-letter no-ai-slop enforcement tests (deterministic checker + retry).

Pins the narrow enforcement added after the first regeneration still shipped the
exact binary-contrast and metadiscourse forms the writing contract bans:

* ``check_cover_letter_style`` catches only high-confidence named patterns and
  never flags clean, human-sounding prose or ordinary grammatical negation;
* a clean first pass is accepted with exactly one cover-letter model call;
* a dirty first pass triggers exactly one correction call on the SAME
  ``create_qa_client()`` route, and the corrected body is re-checked;
* a body that is still dirty after the correction is surfaced for human review,
  never silently accepted, and never retried a third time;
* the correction is strictly editorial (factual-preservation wording);
* the ``<cover_letter_body>`` marker, Q&A routing and the deterministic LaTeX
  format are untouched.

No test here makes a real model call.

Run with: pytest tests/test_cover_letter_slop_enforcement.py -v
"""

import io
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from rich.console import Console

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import modules.pipeline as pipeline  # noqa: E402
from modules import llm_client  # noqa: E402

FRAGMENT_PATH = PROJECT_ROOT / "prompts" / "cover_letter_writing_quality.md"
CORRECTION_PATH = PROJECT_ROOT / "prompts" / "cover_letter_style_correction.md"

# The three constructions the failed Click&Boat regeneration shipped (generic
# names, never the company, so production logic stays company-agnostic).
BAD_OPENER = "Acme's growth problem is not demand. It is that the visitor converts differently."
BAD_LESSON = "The lesson was not that localisation works. It was that the layers must ship as one system."
BAD_PART = "The CMO mindset in your posting is the part I recognise."

CL_DIRTY = (
    "Acme's growth problem is not demand. It is that a marketplace with 55,000 "
    "listings has to convert each visitor differently.\n\n"
    "The lesson was not that localisation works. It was that the acquisition and "
    "conversion layers must ship as one system, which raised conversion 45%.\n\n"
    "The CMO mindset in your posting is the part I recognise, and I want to work "
    "on exactly that surface.\n\n"
    "At Natura & Co I rebuilt the checkout funnel around the links that converted."
)

# A true minimum edit of CL_DIRTY: same claims, same metrics, only the banned
# rhetorical constructions rewritten.
CL_CORRECTED = (
    "Acme's marketplace with 55,000 listings has to convert each visitor "
    "differently, so the acquisition and conversion layers ship as one product "
    "system, which raised conversion 45%.\n\n"
    "The CMO pairing in your posting matches the way I work.\n\n"
    "At Natura & Co I rebuilt the checkout funnel around the links that converted."
)

# Same metrics as CL_DIRTY but a different letter: the replacement guard.
CL_REPLACEMENT = (
    "I am writing to express interest in your opening. My background covers "
    "commerce work across 55,000 accounts where I raised conversion 45% over "
    "four years. I welcome the chance to discuss how I can contribute to your "
    "team and its goals going forward."
)

CL_CLEAN = (
    "Acme's marketplace has 55,000 listings across dozens of markets, and each "
    "market converts a different way, so the booking funnel has to carry that "
    "weight.\n\n"
    "At Natura & Co I rebuilt the checkout funnel around the links that actually "
    "converted, which raised conversion 45%.\n\n"
    "I want to own the traffic-to-booking path at Acme."
)

CL_CLEAN_2 = (
    "Acme runs 55,000 listings across dozens of markets, and conversion differs "
    "by market.\n\n"
    "At Natura & Co I rebuilt the checkout funnel around the links that converted, "
    "which raised conversion 45%.\n\n"
    "I want to own the traffic-to-booking path at Acme."
)


def _wrap(body: str) -> str:
    return (
        f"{pipeline.COVER_LETTER_BODY_TAG_OPEN}\n{body}\n"
        f"{pipeline.COVER_LETTER_BODY_TAG_CLOSE}"
    )


class _SequenceLLM:
    """Returns canned responses in order; raising on an unexpected extra call."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, float]] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> str:
        index = len(self.calls)
        self.calls.append((system_prompt, user_prompt, temperature))
        if index >= len(self.responses):
            raise AssertionError("unexpected extra cover-letter model call")
        return self.responses[index]

    def model_name(self) -> str:
        return "stub/model"


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer), buffer


@pytest.fixture
def qa_env(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "research_company", lambda *a, **k: "")
    monkeypatch.setattr(pipeline, "_load_qa_templates", lambda console: "")
    monkeypatch.setattr(pipeline, "_load_behavioral_profile", lambda: "")
    return tmp_path


def _run_qa(
    run_dir: Path, monkeypatch, responses: list[str]
) -> tuple[dict, _SequenceLLM, str, list[int]]:
    run_dir.mkdir(parents=True, exist_ok=True)
    stub = _SequenceLLM(responses)
    created: list[int] = []

    def _factory() -> Any:
        created.append(1)
        return cast(Any, stub)

    monkeypatch.setattr(pipeline, "create_qa_client", _factory)
    console, buffer = _console()
    ctx: dict = {
        "job": {
            "title": "Senior Product Manager",
            "company": "Acme",
            "description": "We are hiring a senior product manager. " * 20,
        },
        "job_url": "https://example.com/job",
        "questions": [],
        "all_questions": [],
        "generate_cover_letter": True,
        "cover_letter_instructions": "",
        "master_resume": "# Master Resume\n\nPostscript, Senior Product Manager\n",
        "run_dir": str(run_dir),
        "company_safe": "Acme",
    }
    pipeline.step_generate_qa(ctx, cast(Any, _SequenceLLM([])), console)
    return ctx, stub, buffer.getvalue(), created


# ── 1. Deterministic checker: high-confidence patterns ────────────


class TestBinaryContrastDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "Acme's growth problem is not demand. It is that the visitor converts differently.",
            "The problem is not demand. It's the funnel.",
            "The lesson was not that localisation works. It was that the layers must ship as one.",
            "The point is not the tool. It is the team.",
            "The question is not the model. It is the eval.",
            "That is not the point. It's the execution.",
        ],
    )
    def test_cross_sentence_binary_contrast_is_flagged(self, text):
        codes = [f.code for f in pipeline.check_cover_letter_style(text)]
        assert "binary_contrast_cross_sentence" in codes, codes

    @pytest.mark.parametrize(
        "text",
        [
            "The role is not a support role, but a growth role.",
            "The role is not the tool, but the team.",
        ],
    )
    def test_is_not_x_but_y_is_flagged(self, text):
        codes = [f.code for f in pipeline.check_cover_letter_style(text)]
        assert "binary_contrast_is_not_but" in codes, codes

    def test_not_just_but_is_flagged(self):
        codes = [
            f.code
            for f in pipeline.check_cover_letter_style(
                "We did not just test the flow, but shipped the winner."
            )
        ]
        assert "binary_contrast_not_just_but" in codes, codes

    def test_not_because_but_is_flagged(self):
        codes = [
            f.code
            for f in pipeline.check_cover_letter_style(
                "I chose it not because of the title, but because of the team."
            )
        ]
        assert "binary_contrast_not_because_but" in codes, codes

    def test_less_about_more_about_is_flagged(self):
        codes = [
            f.code
            for f in pipeline.check_cover_letter_style(
                "The work was less about tooling, more about ownership."
            )
        ]
        assert "binary_contrast_less_more" in codes, codes


class TestMetadiscourseDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "The lesson is to instrument the funnel first.",
            "The takeaway is that the team ships weekly.",
            "The key point is that ownership matters.",
            "What this shows is that testing wins.",
            "Both experiences point to the same operating model.",
            "The CMO mindset in your posting is the part I recognise.",
            "The CMO mindset in your posting is the part I recognize.",
            "This is the part I want to own.",
        ],
    )
    def test_metadiscourse_is_flagged(self, text):
        codes = [f.code for f in pipeline.check_cover_letter_style(text)]
        assert "metadiscourse" in codes, codes


class TestFauxDiagnosisDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "Acme's growth problem is not demand.",
            "Acme's real challenge is retention.",
            "Acme's demand problem is real.",
            "Acme does not have a demand problem.",
        ],
    )
    def test_faux_diagnosis_opener_is_flagged(self, text):
        codes = [f.code for f in pipeline.check_cover_letter_style(text)]
        assert any(code.startswith("faux_diagnosis") for code in codes), codes

    def test_diagnosis_later_in_the_body_is_not_an_opener(self):
        body = (
            "I rebuilt the checkout funnel at Natura & Co, which raised conversion "
            "45%. The team's problem is prioritisation."
        )
        codes = [f.code for f in pipeline.check_cover_letter_style(body)]
        assert "faux_diagnosis" not in codes, codes


class TestCleanProseIsNotFlagged:
    @pytest.mark.parametrize(
        "text",
        [
            CL_CLEAN,
            CL_CLEAN_2,
            "I am not sure the timeline is realistic, but the role is the one I want.",
            "This is not only about reach, but also about conversion.",
            "I did not own the channel's later commercial scale.",
            "At C&A Brasil I owned Checkout & Payments and ran weekly A/B tests.",
            "Three things moved the number: payment ordering, address autocomplete, "
            "and flow simplification.",
            "Click&Boat's marketplace has a supply problem before it has a demand "
            "problem, and the role sits on it.",
        ],
    )
    def test_clean_examples_are_not_flagged(self, text):
        assert pipeline.check_cover_letter_style(text) == []

    def test_empty_and_whitespace_bodies_are_clean(self):
        assert pipeline.check_cover_letter_style("") == []
        assert pipeline.check_cover_letter_style("   \n\n ") == []

    def test_findings_carry_code_and_bounded_snippet(self):
        findings = pipeline.check_cover_letter_style(BAD_OPENER)
        assert findings
        assert findings[0].code == "binary_contrast_cross_sentence"
        assert len(findings[0].snippet) <= 90


# ── 2. Bounded retry integration ─────────────────────────────────


class TestBoundedRetry:
    def test_clean_first_pass_still_runs_one_mandatory_prune(
        self, qa_env, monkeypatch
    ):
        ctx, stub, out, created = _run_qa(
            qa_env / "clean", monkeypatch, [_wrap(CL_CLEAN), _wrap(CL_CLEAN)]
        )
        assert len(stub.calls) == 2, "every cover letter gets exactly one prune call"
        assert len(created) == 1
        # the prune prompt is empty-findings-safe
        _system, prune_prompt, _temp = stub.calls[1]
        assert "none detected" in prune_prompt
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_CLEAN
        assert style["prune_pass"] is True
        assert style["retry_triggered"] is True
        assert style["model_calls"] == 2
        assert style["prune_changed"] is False
        assert style["first_pass_findings"] == []
        assert style["final_findings"] == []
        assert ctx["cover_letter_body"].strip() == CL_CLEAN.strip()
        assert "human review" not in out.lower()

    def test_dirty_first_pass_is_pruned(self, qa_env, monkeypatch):
        ctx, stub, _out, created = _run_qa(
            qa_env / "dirty", monkeypatch, [_wrap(CL_DIRTY), _wrap(CL_CORRECTED)]
        )
        assert len(stub.calls) == 2, "exactly one prune call"
        assert len(created) == 1, "the prune reuses the same qa route client"
        style = ctx["cover_letter_style"]
        assert style["prune_pass"] is True
        assert style["retry_triggered"] is True
        assert style["model_calls"] == 2
        assert style["status"] == pipeline.COVER_LETTER_STYLE_CORRECTED
        assert style["review_required"] is False
        assert style["prune_changed"] is True
        assert style["first_pass_findings"], "the first-pass findings must be recorded"
        assert style["final_findings"] == []
        assert ctx["cover_letter_body"].strip() == CL_CORRECTED.strip()

    def test_correction_prompt_contains_the_original_body(self, qa_env, monkeypatch):
        _ctx, stub, _out, _created = _run_qa(
            qa_env / "prompt_body", monkeypatch, [_wrap(CL_DIRTY), _wrap(CL_CORRECTED)]
        )
        _system, correction_prompt, _temperature = stub.calls[1]
        assert "Acme's growth problem is not demand" in correction_prompt, (
            "the model must edit the supplied body, not invent one"
        )
        assert "Body to prune" in correction_prompt
        assert "Prune this draft" in correction_prompt

    def test_correction_that_changes_a_metric_is_rejected(self, qa_env, monkeypatch):
        changed = CL_CORRECTED.replace("conversion 45%", "conversion 60%")
        ctx, stub, out, _created = _run_qa(
            qa_env / "metric_change", monkeypatch, [_wrap(CL_DIRTY), _wrap(changed)]
        )
        assert len(stub.calls) == 2, "no third call"
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_REVIEW
        assert style["review_required"] is True
        assert style["factual_guard"] == "correction_did_not_preserve_facts"
        assert style["prune_rejected_reason"] == "prune_changed_or_added_facts"
        assert ctx["cover_letter_body"].strip() == CL_DIRTY.strip(), "keep the draft"
        assert "human review" in " ".join(out.lower().split())

    def test_correction_that_replaces_the_letter_is_rejected(self, qa_env, monkeypatch):
        ctx, stub, _out, _created = _run_qa(
            qa_env / "replacement", monkeypatch, [_wrap(CL_DIRTY), _wrap(CL_REPLACEMENT)]
        )
        assert len(stub.calls) == 2, "no third call"
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_REVIEW
        assert style["factual_guard_detail"]["content_overlap"] < 0.5
        assert ctx["cover_letter_body"].strip() == CL_DIRTY.strip(), "keep the draft"

    def test_correction_prompt_is_editorial_and_grounded(self, qa_env, monkeypatch):
        _ctx, stub, _out, _created = _run_qa(
            qa_env / "prompt", monkeypatch, [_wrap(CL_DIRTY), _wrap(CL_CORRECTED)]
        )
        _system, correction_prompt, temperature = stub.calls[1]
        # exact detected pattern names / snippets are passed through
        assert "binary_contrast_cross_sentence" in correction_prompt
        assert "not demand. It is" in correction_prompt
        assert "metadiscourse" in correction_prompt
        # the factual-preservation instruction is explicit
        assert (
            "Preserve the substantive claims and evidence" in correction_prompt
        )
        assert "Do not introduce any new factual content" in correction_prompt
        # the output contract is preserved
        assert pipeline.COVER_LETTER_BODY_TAG_OPEN in correction_prompt
        assert pipeline.COVER_LETTER_BODY_TAG_CLOSE in correction_prompt
        # editorial pass runs cool
        assert temperature == 0.3

    def test_second_pass_still_dirty_surfaces_human_review(self, qa_env, monkeypatch):
        ctx, stub, out, _created = _run_qa(
            qa_env / "still_dirty", monkeypatch, [_wrap(CL_DIRTY), _wrap(CL_DIRTY)]
        )
        assert len(stub.calls) == 2, "no third call"
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_REVIEW
        assert style["review_required"] is True
        assert style["final_findings"], "the residual findings must be surfaced"
        assert style["prune_rejected_reason"] == "still_dirty"
        assert "human review" in " ".join(out.lower().split())
        # the safe first-pass draft is preserved, not the still-dirty prune
        assert ctx["cover_letter_body"].strip() == CL_DIRTY.strip()

    def test_unparseable_correction_surfaces_human_review(self, qa_env, monkeypatch):
        ctx, stub, out, _created = _run_qa(
            qa_env / "unparseable",
            monkeypatch,
            [_wrap(CL_DIRTY), "I have rewritten the body above."],
        )
        assert len(stub.calls) == 2
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_REVIEW
        assert style["review_required"] is True
        assert style["prune_rejected_reason"] == "prune_unparseable"
        assert ctx["cover_letter_body"].strip() == CL_DIRTY.strip(), "keep the draft"
        assert "human review" in " ".join(out.lower().split())

    def test_missing_correction_prompt_degrades_to_review(self, qa_env, monkeypatch):
        monkeypatch.setattr(
            pipeline, "_load_cover_letter_style_correction_template", lambda: ""
        )
        ctx, stub, _out, _created = _run_qa(
            qa_env / "no_prompt", monkeypatch, [_wrap(CL_DIRTY)]
        )
        assert len(stub.calls) == 1, "no prune call without a template"
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_REVIEW
        assert style["review_required"] is True
        assert style["prune_rejected_reason"] == "prune_prompt_missing"

    def test_prune_may_drop_a_number(self, qa_env, monkeypatch):
        # Original numbers are {55,000, 45%}; the prune drops 45%.
        pruned = (
            "Acme's marketplace with 55,000 listings has to convert each visitor "
            "differently, so the acquisition and conversion layers ship as one "
            "product system.\n\n"
            "The CMO pairing in your posting matches the way I work.\n\n"
            "At Natura & Co I rebuilt the checkout funnel around the links that "
            "converted."
        )
        ctx, stub, _out, _created = _run_qa(
            qa_env / "drop_number", monkeypatch, [_wrap(CL_DIRTY), _wrap(pruned)]
        )
        assert len(stub.calls) == 2
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_CORRECTED
        assert style["review_required"] is False
        assert style["final_findings"] == []
        assert "45%" not in ctx["cover_letter_body"]
        assert ctx["cover_letter_body"].strip() == pruned.strip()

    def test_prune_may_not_add_a_number(self, qa_env, monkeypatch):
        added = CL_CORRECTED.replace("45%", "45% and 60%")
        ctx, stub, _out, _created = _run_qa(
            qa_env / "add_number", monkeypatch, [_wrap(CL_DIRTY), _wrap(added)]
        )
        assert len(stub.calls) == 2
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_REVIEW
        assert style["factual_guard"] == "correction_did_not_preserve_facts"
        assert "60%" in style["factual_guard_detail"]["introduced_numbers"]
        assert ctx["cover_letter_body"].strip() == CL_DIRTY.strip(), "keep the draft"

    def test_prune_may_not_materially_expand_the_body(self, qa_env, monkeypatch):
        expanded = (
            CL_CORRECTED
            + "\n\n"
            + "I would bring additional breadth from the wider organisation. " * 3
        )
        ctx, stub, _out, _created = _run_qa(
            qa_env / "expand", monkeypatch, [_wrap(CL_DIRTY), _wrap(expanded)]
        )
        assert len(stub.calls) == 2
        style = ctx["cover_letter_style"]
        assert style["status"] == pipeline.COVER_LETTER_STYLE_REVIEW
        assert style["factual_guard_detail"]["length_grew"] is True
        assert ctx["cover_letter_body"].strip() == CL_DIRTY.strip(), "keep the draft"

    def test_prune_prompt_says_prune_not_enrich(self, qa_env, monkeypatch):
        _ctx, stub, _out, _created = _run_qa(
            qa_env / "prune_prompt", monkeypatch, [_wrap(CL_DIRTY), _wrap(CL_CORRECTED)]
        )
        system_prompt, user_prompt, _temp = stub.calls[1]
        joined = system_prompt + "\n" + user_prompt
        assert "Prune this draft" in joined
        assert "Do not enrich" in joined or "do not enrich" in joined
        assert "Preserve the substantive claims and evidence" in joined
        assert "Do not introduce any new factual content" in joined

    def test_clean_first_pass_still_runs_the_prune_in_a_mixed_run(
        self, qa_env, monkeypatch
    ):
        response = (
            "### Q: Why do you want this role?\n### A: Because the problem is specific\n\n"
            + _wrap(CL_CLEAN)
        )
        run_dir = qa_env / "mixed"
        run_dir.mkdir(parents=True, exist_ok=True)
        stub = _SequenceLLM([response, _wrap(CL_CLEAN)])
        monkeypatch.setattr(pipeline, "create_qa_client", lambda: cast(Any, stub))
        console, _buffer = _console()
        ctx: dict = {
            "job": {
                "title": "Senior Product Manager",
                "company": "Acme",
                "description": "We are hiring a senior product manager. " * 20,
            },
            "job_url": "https://example.com/job",
            "questions": ["Why do you want this role?"],
            "all_questions": ["Why do you want this role?"],
            "generate_cover_letter": True,
            "cover_letter_instructions": "",
            "master_resume": "# Master Resume\n\nPostscript\n",
            "run_dir": str(run_dir),
            "company_safe": "Acme",
        }
        pipeline.step_generate_qa(ctx, cast(Any, stub), console)
        assert len(stub.calls) == 2, "a clean cover letter still gets one prune call"
        assert ctx["qa_status"] == pipeline.STAGE_OK


# ── 3. Preserved contracts ────────────────────────────────────────


class TestPreservedContracts:
    def test_output_marker_survives(self, qa_env, monkeypatch):
        ctx, _stub, _out, _created = _run_qa(
            qa_env / "marker", monkeypatch, [_wrap(CL_DIRTY), _wrap(CL_CORRECTED)]
        )
        body = ctx["cover_letter_body"]
        assert pipeline.COVER_LETTER_BODY_TAG_OPEN not in body
        assert pipeline.COVER_LETTER_BODY_TAG_CLOSE not in body
        assert body.strip() == CL_CORRECTED.strip()

    def test_qa_routing_unchanged(self):
        route = llm_client.STAGE_ROUTES["qa"]
        assert route["provider"] == "openrouter"
        assert route["model"] == "deepseek/deepseek-v4.1-flash"
        assert route["fallback_provider"] == "openrouter"
        assert route["fallback_model"] == "openai/gpt-6-luna"

    def test_fragment_carries_the_hard_bans(self):
        fragment = FRAGMENT_PATH.read_text()
        lowered = fragment.lower()
        assert "hard bans (acceptance-blocking)" in lowered
        for pattern in (
            "binary contrast templates",
            "interpretive metadiscourse",
            "unsupported company diagnosis",
            "sloganized abstractions",
            "colon reveals",
        ):
            assert pattern in lowered, pattern

    def test_correction_prompt_is_factual_preserving(self):
        assert CORRECTION_PATH.exists(), f"missing {CORRECTION_PATH}"
        prompt = CORRECTION_PATH.read_text()
        assert "Preserve the substantive claims and evidence" in prompt
        assert "Do not introduce any new factual content" in prompt
        assert "{body}" in prompt, "the original body must be supplied to the editor"
        assert "<cover_letter_body>" in prompt

    def test_correction_prompt_does_not_mention_provider_routing(self):
        prompt = CORRECTION_PATH.read_text().lower()
        for token in ("openrouter", "deepseek", "gpt-", "reasoning_effort"):
            assert token not in prompt, token

    def test_enforcement_reuses_stage_llm_client(self):
        import inspect

        source = inspect.getsource(pipeline.step_generate_qa)
        assert source.count("create_qa_client()") == 1, "exactly one writing client"
        assert "enforce_cover_letter_style" in source


# ── 4. Voice / content contract (generation prompt, not the checker) ──────


class TestVoiceContract:
    """The voice/content contract lives in the prompt, not in new regex rules."""

    @pytest.fixture(autouse=True)
    def fragment(self):
        # Whitespace-normalised so line wrapping in the prompt cannot break a
        # multi-word assertion.
        return " ".join(FRAGMENT_PATH.read_text().lower().split())

    def test_carries_the_voice_and_evidence_rules(self, fragment):
        for rule in (
            "voice and content contract",
            "do not diagnose the company",
            "do not speculate about its users",
            "prefer the concrete mechanism to the metaphor",
            "do not interpret the job description for the reader",
            "do not diminish the company to elevate the candidate",
            "do not end on generic company praise",
            "evidence-selection discipline",
            "prefer fewer, stronger",
            "structure contract",
            "why this role is relevant",
            "direct motivation",
        ):
            assert rule in fragment, rule

    def test_prohibits_company_diagnosis_without_evidence(self, fragment):
        assert "unsupported company diagnosis" in fragment
        assert "unless the job posting or company evidence states it" in fragment

    def test_prohibits_company_and_user_behaviour_speculation(self, fragment):
        assert "do not claim the company's growth problem" in fragment
        assert "do not speculate about its users" in fragment
        assert "invent user behaviour" in fragment

    def test_prefers_concrete_evidence_over_abstraction(self, fragment):
        assert "prefer the concrete mechanism to the metaphor" in fragment
        assert "users dropped at the payment" in fragment

    def test_discourages_evidence_stuffing(self, fragment):
        assert "does not need every supported fact" in fragment
        assert "prefer fewer, stronger" in fragment
        assert "do not insert an achievement" in fragment

    def test_prohibits_superiority_comparisons(self, fragment):
        for phrase in (
            "messier than",
            "harder than",
            "more complex than",
            "more sophisticated than",
        ):
            assert phrase in fragment, phrase

    def test_prefers_direct_motivation_over_jd_interpretation(self, fragment):
        assert "do not interpret the job description for the reader" in fragment
        assert "direct motivation" in fragment

    def test_existing_no_ai_slop_hard_bans_remain(self, fragment):
        assert "hard bans (acceptance-blocking)" in fragment
        for pattern in (
            "binary contrast templates",
            "interpretive metadiscourse",
            "unsupported company diagnosis",
            "sloganized abstractions",
            "colon reveals",
        ):
            assert pattern in fragment, pattern


class TestCheckerNotExpandedForVoice:
    """Generic words that are only sometimes bad must stay unflagged."""

    @pytest.mark.parametrize(
        "text",
        [
            "I rebuilt the surface of the checkout flow.",
            "The team used a lever to improve conversion.",
            "The layer between the API and the UI caused the delay.",
            "I closed the gap between search and booking.",
            "I chose to ship weekly rather than quarterly.",
            "The engine team owned search.",
            "I spent most of my career on marketplace checkout work.",
        ],
    )
    def test_generic_voice_words_are_not_high_confidence(self, text):
        assert pipeline.check_cover_letter_style(text) == []

    def test_checker_families_are_unchanged(self):
        codes = {f.code for f in pipeline.check_cover_letter_style(CL_DIRTY)}
        assert codes == {
            "binary_contrast_cross_sentence",
            "metadiscourse",
            "slogan_abstraction",
            "faux_diagnosis",
        }


# ── 5. Evidence-selection / two-story budget (prompt, not runtime) ──────


class TestEvidenceSelectionContract:
    """The two-story budget and metric discipline live in the prompt only."""

    @pytest.fixture(autouse=True)
    def fragment(self):
        return " ".join(FRAGMENT_PATH.read_text().lower().split())

    def test_prefers_at_most_two_primary_stories(self, fragment):
        assert "two-story budget" in fragment
        assert "at most two primary candidate evidence stories" in fragment

    def test_leaving_supported_evidence_unused_is_allowed(self, fragment):
        assert "does not need every supported fact" in fragment
        assert "leaving supported evidence unused is correct" in fragment
        assert "selection, not a coverage report" in fragment

    def test_stories_must_be_distinct_and_role_relevant(self, fragment):
        assert "distinct capability relevant to this role" in fragment
        assert "prove something materially different" in fragment

    def test_weaker_and_tangential_evidence_is_omitted(self, fragment):
        assert "leave the example out" in fragment
        assert "omit the story" in fragment
        assert "tangential domain" in fragment
        assert "third employer" in fragment

    def test_metric_inventory_is_discouraged(self, fragment):
        assert "not an inventory" in fragment
        assert "no more than two outcome metrics per primary story" in fragment
        assert "do not add a weaker metric" in fragment
        assert "stacking several percentages" in fragment

    def test_one_employer_story_per_evidence_paragraph(self, fragment):
        assert "one employer story per evidence paragraph" in fragment
        assert "one coherent" in fragment
        assert "if the paragraph already has that chain, stop" in fragment

    def test_maximum_two_employers_as_evidence(self, fragment):
        assert "at most two employers as candidate evidence in the whole body" in fragment
        assert "no third employer in a side sentence" in fragment
        assert "no third project hidden inside a paragraph" in fragment

    def test_secondary_also_initiatives_are_discouraged(self, fragment):
        assert "do not append a second initiative from the same employer" in fragment
        assert 'side projects, secondary launches' in fragment
        assert '"also..." achievements' in fragment

    def test_context_counts_must_not_become_metric_inventory(self, fragment):
        assert "context counts such as number of markets" in fragment
        assert "must not be stacked" in fragment
        assert "metric inventory" in fragment

    def test_stronger_metrics_displace_weaker_metrics(self, fragment):
        assert "choose the best two outcome metrics" in fragment
        assert "not every supported" in fragment

    def test_silent_selection_before_drafting(self, fragment):
        assert "silent selection before drafting" in fragment
        assert "discard every weaker or tangential" in fragment
        assert "do not expose this selection" in fragment

    def test_closing_may_add_logistics_but_no_new_evidence(self, fragment):
        assert "practical logistics if directly relevant" in fragment
        assert "do not introduce new evidence" in fragment
        assert "no new candidate evidence" in fragment

    def test_closing_does_not_explain_the_business_model(self, fragment):
        assert "do not explain the company's own business model" in fragment

    def test_closing_introduces_no_new_evidence(self, fragment):
        assert "do not introduce new evidence" in fragment

    def test_company_facts_are_not_restated_for_show(self, fragment):
        assert "do not explain the company's own marketplace" in fragment
        assert "restate obvious company facts to prove that research was done" in fragment

    def test_structure_contract_has_no_third_story(self, fragment):
        assert "paragraph 2: the second distinct story" in fragment
        assert "do not return to the first employer" in fragment

    def test_checker_stays_subjective_free(self):
        # These are selection issues and must remain prompt-level, not regexes.
        for text in (
            "I used two stories in this letter.",
            "I used three metrics across the letter.",
            "The example was tangential to the role.",
            "My narrative explains the company's marketplace.",
        ):
            assert pipeline.check_cover_letter_style(text) == []
