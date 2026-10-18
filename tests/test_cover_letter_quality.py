"""Cover-letter writing-quality contract tests (no-ai-slop adaptation).

Pins the narrow integration:

* ``prompts/cover_letter_writing_quality.md`` is a compact, attributed adaptation
  of Peter Yang's no-ai-slop skill (MIT);
* the contract is appended to the synthetic COVER-LETTER question only, so
  application answers keep their existing style;
* the factual boundary outranks style;
* the existing ``<cover_letter_body>`` marker and body-only contract survive;
* the cover letter still costs exactly one writing call (no extra LLM stage),
  and Q&A routing is untouched.

No test here makes a model call.

Run with: pytest tests/test_cover_letter_quality.py -v
"""

import inspect
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

REAL_QUESTION = "Why do you want this role?"
CL_BODY = (
    "Click&Boat's marketplace has a supply problem before it has a demand problem, "
    "and the Traffic & Acquisition role sits on it.\n\n"
    "At Natura & Co I rebuilt the checkout funnel around the links that actually "
    "converted, which raised conversion 45%.\n\n"
    "I want to work on the owner-side listing decision at Click&Boat."
)


class _StubLLM:
    """Records prompts; returns a compliant delimited cover-letter body."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str, float]] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> str:
        self.calls.append((system_prompt, user_prompt, temperature))
        return self.response

    def model_name(self) -> str:
        return "stub/model"


def _console() -> Console:
    return Console(file=io.StringIO())


@pytest.fixture
def qa_env(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "research_company", lambda *a, **k: "")
    monkeypatch.setattr(pipeline, "_load_qa_templates", lambda console: "")
    monkeypatch.setattr(pipeline, "_load_behavioral_profile", lambda: "")
    return tmp_path


def _run_qa(
    run_dir: Path,
    monkeypatch,
    response: str,
    *,
    questions: tuple[str, ...] = (),
    cover_letter: bool = True,
) -> tuple[dict, _StubLLM]:
    run_dir.mkdir(parents=True, exist_ok=True)
    stub = _StubLLM(response)
    monkeypatch.setattr(pipeline, "create_qa_client", lambda: cast(Any, stub))
    ctx: dict = {
        "job": {
            "title": "Senior Product Manager",
            "company": "Clickboat",
            "description": "We are hiring a senior product manager. " * 20,
        },
        "job_url": "https://example.com/job",
        "questions": list(questions),
        "all_questions": list(questions),
        "generate_cover_letter": cover_letter,
        "cover_letter_instructions": "",
        "master_resume": "# Master Resume\n\nPostscript, Senior Product Manager\n",
        "run_dir": str(run_dir),
        "company_safe": "Clickboat",
    }
    pipeline.step_generate_qa(ctx, cast(Any, _StubLLM("unused")), _console())
    return ctx, stub


DELIMITED = f"<cover_letter_body>\n{CL_BODY}\n</cover_letter_body>"


# ── 1. The fragment exists and carries the contract ───────────────


class TestQualityFragment:
    @pytest.fixture(autouse=True)
    def fragment(self):
        assert FRAGMENT_PATH.exists(), f"missing {FRAGMENT_PATH}"
        return FRAGMENT_PATH.read_text()

    def test_attribution_preserved(self, fragment):
        assert "no-ai-slop" in fragment
        assert "petergyang/no-ai-slop" in fragment
        assert "MIT" in fragment

    def test_scoped_to_the_cover_letter(self, fragment):
        assert "cover letter body only" in fragment.lower()
        assert "never apply these rules to other" in fragment.lower()

    def test_explicit_factual_preservation_requirement(self, fragment):
        lowered = fragment.lower()
        assert "never creates evidence" in lowered
        assert "do not add or change" in lowered
        for category in ("achievements", "metrics", "employer names", "tools", "examples"):
            assert category in lowered, category
        # JQuest factual rules must be stated as the higher priority.
        assert "outranks style" in lowered

    def test_requires_one_internal_edit_pass_without_leaking_it(self, fragment):
        lowered = " ".join(fragment.lower().split())  # line wrapping must not break assertions
        assert "internal editorial pass" in lowered
        assert "do not return the draft" in lowered
        assert 'do not add a "what changed" section' in lowered
        assert "do not explain what you changed" in lowered
        # the upstream workflow returns a What-changed section; here it is forbidden
        assert "return the edited draft" not in lowered
        assert "output the full edited draft" not in lowered

    def test_preserves_the_body_only_tag_contract(self, fragment):
        assert "final body paragraphs" in fragment.lower()
        assert "required tags" in fragment.lower()

    def test_carries_the_editorial_rules(self, fragment):
        lowered = fragment.lower()
        for rule in (
            "portability test",
            "lead with the point",
            "active voice",
            "human cadence",
            "leave strong sentences alone",
            "existing level of confidence",
        ):
            assert rule in lowered, rule

    def test_carries_the_slop_patterns_to_remove(self, fragment):
        lowered = fragment.lower()
        for pattern in (
            "throat-clearing",
            "faux-insight",
            "binary",
            "colon reveals",
            "superficial analysis",
            "importance puffery",
            "weasel attribution",
            "metadiscourse",
            "self-praise",
            "fake-profound",
            "summary or recap",
            "robotic symmetry",
            "not a banned-word filter",
        ):
            assert pattern in lowered, pattern


# ── 2-6. Integration, scope, contract, single call ───────────────


class TestCoverLetterQualityIntegration:
    def test_cover_letter_prompt_carries_the_quality_contract(self, qa_env, monkeypatch):
        run_dir = qa_env / "cl_only"
        ctx, stub = _run_qa(run_dir, monkeypatch, DELIMITED)
        assert len(stub.calls) == 2, "draft + one mandatory prune pass"
        _system, user_prompt, _temp = stub.calls[0]
        assert "Factual contract (highest priority)" in user_prompt
        assert "portability test" in user_prompt.lower()
        # the fragment is part of the cover-letter question itself
        assert user_prompt.index("Write a cover letter body for this application.") < user_prompt.index(
            "Factual contract (highest priority)"
        )

    def test_existing_body_marker_and_body_only_contract_survive(self, qa_env, monkeypatch):
        run_dir = qa_env / "cl_marker"
        ctx, stub = _run_qa(run_dir, monkeypatch, DELIMITED)
        _system, user_prompt, _temp = stub.calls[0]
        assert pipeline.COVER_LETTER_BODY_TAG_OPEN in user_prompt
        assert pipeline.COVER_LETTER_BODY_TAG_CLOSE in user_prompt
        assert "Output ONLY the body paragraphs" in user_prompt
        body = ctx["cover_letter_body"] or ""
        assert body.strip() == CL_BODY.strip(), "delimited extraction must still work"
        assert "<cover_letter_body>" not in body

    def test_quality_contract_is_not_applied_to_application_questions(self, qa_env, monkeypatch):
        run_dir = qa_env / "qa_only"
        ctx, stub = _run_qa(
            run_dir, monkeypatch, f"### Q: {REAL_QUESTION}\n### A: short answer\n", questions=(REAL_QUESTION,), cover_letter=False
        )
        assert len(stub.calls) == 1
        _system, user_prompt, _temp = stub.calls[0]
        assert "Factual contract (highest priority)" not in user_prompt
        assert "portability test" not in user_prompt.lower()
        assert ctx["cover_letter_body"] is None

    def test_cover_letter_and_question_still_share_one_call(self, qa_env, monkeypatch):
        run_dir = qa_env / "mixed"
        response = (
            f"### Q: {REAL_QUESTION}\n### A: because the problem is specific\n\n"
            f"<cover_letter_body>\n{CL_BODY}\n</cover_letter_body>\n"
        )
        ctx, stub = _run_qa(run_dir, monkeypatch, response, questions=(REAL_QUESTION,))
        assert len(stub.calls) == 2, "draft + one mandatory prune; no third call"
        assert (ctx["cover_letter_body"] or "").strip() == CL_BODY.strip()

    def test_no_extra_writing_client_in_the_step(self):
        source = inspect.getsource(pipeline.step_generate_qa)
        assert source.count("create_qa_client()") == 1, "exactly one writing client"

    def test_missing_fragment_loader_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "PROMPTS_DIR", tmp_path)  # no fragment on disk
        assert pipeline._load_cover_letter_quality_rules() == ""

    def test_missing_fragment_degrades_to_previous_behaviour(self, qa_env, monkeypatch):
        monkeypatch.setattr(pipeline, "_load_cover_letter_quality_rules", lambda: "")
        run_dir = qa_env / "cl_degraded"
        ctx, stub = _run_qa(run_dir, monkeypatch, DELIMITED)
        assert len(stub.calls) == 2, "draft + one mandatory prune pass"
        _system, user_prompt, _temp = stub.calls[0]
        assert "Write a cover letter body for this application." in user_prompt
        assert "Factual contract (highest priority)" not in user_prompt
        assert (ctx["cover_letter_body"] or "").strip() == CL_BODY.strip()


class TestQaRoutingUnchanged:
    def test_qa_stage_route_is_unchanged(self):
        route = llm_client.STAGE_ROUTES["qa"]
        assert route["provider"] == "openrouter"
        assert route["model"] == "deepseek/deepseek-v4.1-flash"
        assert route["fallback_provider"] == "openrouter"
        assert route["fallback_model"] == "openai/gpt-6-luna"

    def test_cover_letter_uses_the_qa_stage_client(self):
        source = inspect.getsource(pipeline.step_generate_qa)
        assert "create_qa_client" in source
        # no interview/prep or other stage client may be pulled into this step
        for other in ("create_interview_client", "create_tailor_client", "create_reviewer_client_v2"):
            assert other not in source, other

    def test_fragment_does_not_mention_models_or_routing(self):
        fragment = FRAGMENT_PATH.read_text().lower()
        for token in ("openrouter", "deepseek", "gpt-", "reasoning_effort", "temperature"):
            assert token not in fragment, token
        # an "operating model" may be quoted as a slop example, but no LLM-model talk
        assert "language model" not in fragment
        assert "llm" not in fragment
