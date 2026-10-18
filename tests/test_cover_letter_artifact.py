"""Live Pilot Hotfix H2: a requested cover letter must actually be delivered.

Reproduces the Clickboat failure and pins the fix.

In the failed pilot (run ``Clickboat_2026-10-06T214324_f61820``) ``--cover-letter``
was requested and the writing call DID return a correct cover-letter body, but the
artifact was discarded and the stage reported FAILED:

  * the synthetic question instructs the model to emit body paragraphs only
    ("Do NOT include a date line, greeting, sign-off, or any other metadata"), so
    a compliant response never echoes the question;
  * ``_find_cover_letter_body`` locates the body by question identity, which can
    therefore never match in a cover-letter-only run;
  * ``ctx["cover_letter_body"]`` became ``None`` and no ``Cover-Letter*`` artifact
    was written, even though the body sat on disk in ``qa_*.md``.

These tests prove the requested artifact is now delivered, that status is
truthful (never OK without a real artifact containing the real body), that
write/compile failures degrade to FAILED instead of aborting the run, and that
the Q&A-only and shared-call paths are unchanged.
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
from modules import sendability  # noqa: E402

RUN_ID = "Clickboat_2026-10-06T214324_f61820"
MASTER = (PROJECT_ROOT / ".master_resume_cache_2f40fd98.txt").read_text()

# Distinctive phrases with no LaTeX-special characters, so assertions can match
# the escaped artifact text verbatim.
CL_OPENING = "closing the inventory-discovery gap"
CL_MIDDLE = "four-country LatAm rollout"

# Shaped exactly like the failed pilot's response: body paragraphs only, no
# question echo, because the synthetic question forbids wrapper text.
CL_BODY = (
    f"Marketplace growth in the recreational boating sector depends on {CL_OPENING} "
    "across highly seasonal markets. At Postscript I owned post-launch iteration of "
    "an AI message optimisation engine used by 18,000+ merchants.\n\n"
    f"At Accenture I led a {CL_MIDDLE} for Natura & Co, scaling e-commerce "
    "operations across Mexico, Colombia, Chile and Argentina.\n\n"
    "I would bring the same rigour to Click&Boat's acquisition funnel.\n"
)

REAL_QUESTION = "Why do you want this role?"
REAL_ANSWER = "Because I have shipped growth products in marketplaces."
QA_ONLY_RESPONSE = f"### Q: {REAL_QUESTION}\n### A: {REAL_ANSWER}\n"

CL_QUESTION_TEXT = (
    "Write a cover letter body for this application. Output ONLY the body "
    "paragraphs (2-4 paragraphs). Do NOT include a date line, greeting, "
    "sign-off, or any other metadata, only the paragraphs themselves. The LaTeX "
    "template supplies the greeting and sign-off."
)
SHARED_RESPONSE = (
    f"### Q: {REAL_QUESTION}\n### A: {REAL_ANSWER}\n\n"
    f"### Q: {CL_QUESTION_TEXT}\n### A: {CL_BODY}\n"
)

COVER_LETTER_TEX = "Cover-Letter_RodrigoLopes.tex"
COVER_LETTER_PDF = "Cover-Letter_RodrigoLopes.pdf"


class _StubLLM:
    """LLM stand-in: returns canned text and counts invocations."""

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


def _llm() -> pipeline.LLMClient:
    return cast(pipeline.LLMClient, _StubLLM("unused"))


@pytest.fixture
def qa_env(tmp_path, monkeypatch):
    """Isolate the Q&A/cover-letter path from network, Notion and prompts."""
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
        "master_resume": MASTER,
        "run_dir": str(run_dir),
        "company_safe": "Clickboat",
    }
    pipeline.step_generate_qa(ctx, _llm(), _console())
    return ctx, stub


def _compile(ctx: dict, monkeypatch, fake: Any = None) -> None:
    if fake is not None:
        monkeypatch.setattr(pipeline, "compile_and_inspect", fake)
    pipeline.step_compile_cover_letter(ctx, _llm(), _console())


# ── 15-17, 26: the happy path for a cover-letter-only request ──────────────


class TestCoverLetterOnlyDelivery:
    def test_cover_letter_only_request_produces_final_artifact(
        self, qa_env, monkeypatch
    ):
        """Required behaviours 15, 16 and 26."""
        run_dir = qa_env / RUN_ID
        ctx, stub = _run_qa(run_dir, monkeypatch, CL_BODY)

        # Gate A.4 identity is preserved: only the synthetic question was asked.
        assert ctx["cover_letter_required"] is True
        assert len(stub.calls) == 2, "draft + one mandatory prune pass"
        assert ctx["cover_letter_body"], "the generated body must be kept"

        _compile(ctx, monkeypatch)

        assert ctx["cover_letter_status"] == pipeline.STAGE_OK
        tex_path = run_dir / COVER_LETTER_TEX
        assert tex_path.exists(), "requested cover letter artifact must exist"
        assert tex_path.stat().st_size > 0
        assert COVER_LETTER_PDF in (ctx.get("cover_letter_pdf_path") or "")

        pdf_path = Path(ctx["cover_letter_pdf_path"])
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_final_artifact_contains_the_generated_body(self, qa_env, monkeypatch):
        """Required behaviour 16."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, CL_BODY)
        _compile(ctx, monkeypatch)

        written = (run_dir / COVER_LETTER_TEX).read_text()
        assert CL_OPENING in written
        assert CL_MIDDLE in written
        # The body, not the synthetic question, is what got compiled.
        assert "Write a cover letter body for this application" not in written

    def test_cover_letter_only_keeps_qa_skipped(self, qa_env, monkeypatch):
        """Required behaviour 17: no application questions were required."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, CL_BODY)

        assert ctx["qa_required"] is False
        assert ctx["qa_status"] == pipeline.STAGE_SKIPPED
        assert ctx["qa_skip_reason"] == pipeline.STAGE_SKIP_NO_APPLICATION_QUESTIONS

    def test_no_fake_artifact_and_no_extra_llm_call_on_repeat(
        self, qa_env, monkeypatch
    ):
        """Required behaviour 26: instrumentation adds no writing call."""
        run_dir = qa_env / RUN_ID
        ctx, stub = _run_qa(run_dir, monkeypatch, CL_BODY)
        assert len(stub.calls) == 2, "draft + one mandatory prune pass"
        assert len(list(run_dir.glob("Cover-Letter*"))) == 0  # not compiled yet


# ── 18-21, 23: truthfulness of failure ─────────────────────────────────────


class TestCoverLetterFailureIsTruthful:
    def test_unrelated_qa_answer_cannot_become_the_cover_letter(
        self, qa_env, monkeypatch
    ):
        """Required behaviour 18: identity matching still governs."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(
            run_dir, monkeypatch, QA_ONLY_RESPONSE, questions=(REAL_QUESTION,)
        )

        # The response answers the real question and never the cover letter, so
        # there is no body to attribute and the stage must fail truthfully.
        assert ctx["cover_letter_body"] is None
        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED
        assert not (run_dir / COVER_LETTER_TEX).exists()

    def test_failed_write_marks_cover_letter_failed_not_aborted(
        self, qa_env, monkeypatch
    ):
        """Required behaviour 19: an OSError on the artifact is a FAILED stage."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, CL_BODY)

        # A directory at the artifact path makes write_text raise IsADirectoryError.
        (run_dir / COVER_LETTER_TEX).mkdir()

        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED

    def test_failed_compile_marks_cover_letter_failed(self, qa_env, monkeypatch):
        """Required behaviour 20."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, CL_BODY)
        _compile(
            ctx,
            monkeypatch,
            fake=lambda *a, **k: {"ok": False, "error": "pdflatex exploded"},
        )
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED

    def test_raising_compile_marks_cover_letter_failed(self, qa_env, monkeypatch):
        """Required behaviour 20: a raised OSError must not abort the run."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, CL_BODY)

        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise OSError("no pdflatex on PATH")

        _compile(ctx, monkeypatch, fake=_boom)
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED

    def test_missing_final_artifact_never_reports_ok(self, qa_env, monkeypatch):
        """Required behaviours 21 and 23."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, CL_BODY)
        missing = run_dir / "not-written.pdf"
        _compile(
            ctx,
            monkeypatch,
            fake=lambda *a, **k: {"ok": True, "pdf_path": str(missing)},
        )
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED
        assert not missing.exists()

    def test_body_missing_from_template_never_reports_ok(self, qa_env, monkeypatch):
        """A template without {body} must not yield a bodiless 'success'."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, CL_BODY)

        bodiless = run_dir / "cover_letter_no_placeholder.tex"
        bodiless.write_text("Dear Hiring Team,\n\n\\end{document}\n")
        monkeypatch.setattr(pipeline, "PROJECT_ROOT", run_dir.parent)
        (run_dir.parent / "templates").mkdir(exist_ok=True)
        (run_dir.parent / "templates" / "cover_letter.tex").write_text(
            bodiless.read_text()
        )

        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED

    def test_cover_letter_failure_produces_warning_semantics(self):
        """Required behaviour 22."""
        verdict = sendability.evaluate_sendability(
            run_id=RUN_ID,
            final_latex="\\documentclass{article}\n\\section*{Experience}\n",
            resume_artifact_present=True,
            resume_artifact_bytes=40,
            pdf_present=True,
            pdf_bytes=1024,
            master_resume=None,
            canonical_template=None,
            tailoring_mode=sendability.TAILORING_TARGETED,
            tailoring_outcome=sendability.TAILORING_OUTCOME_TAILORED,
        )
        assert verdict["status"] == sendability.HOLD  # no master => unverifiable

        ready = dict(verdict)
        ready["status"] = sendability.READY_TO_SEND
        ready["blockers"] = []
        updated = sendability.finalize_optional_stage_warnings(
            ready, {sendability.WARN_COVER_LETTER_FAILED: "requested cover letter could not be produced"}
        )
        assert updated["status"] == sendability.READY_WITH_WARNINGS
        assert [w["code"] for w in updated["warnings"]] == [
            sendability.WARN_COVER_LETTER_FAILED
        ]


# ── 24-25: unchanged Q&A-only and shared-call behaviour ────────────────────


class TestQaPathsUnchanged:
    def test_qa_only_path_creates_no_cover_letter_artifact(self, qa_env, monkeypatch):
        """Required behaviour 24."""
        run_dir = qa_env / RUN_ID
        ctx, stub = _run_qa(
            run_dir, monkeypatch, QA_ONLY_RESPONSE, questions=(REAL_QUESTION,), cover_letter=False
        )
        assert len(stub.calls) == 1
        assert ctx["cover_letter_required"] is False
        assert ctx["cover_letter_body"] is None
        assert ctx["qa_status"] == pipeline.STAGE_OK
        assert ctx["qa_answers"][0]["answer"] == REAL_ANSWER

        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_SKIPPED
        assert not (run_dir / COVER_LETTER_TEX).exists()

    def test_shared_qa_and_cover_letter_call_still_works(self, qa_env, monkeypatch):
        """Required behaviour 25: one shared call, both artifacts."""
        run_dir = qa_env / RUN_ID
        ctx, stub = _run_qa(
            run_dir,
            monkeypatch,
            SHARED_RESPONSE,
            questions=(REAL_QUESTION,),
            cover_letter=True,
        )
        assert len(stub.calls) == 2, "draft + one prune; Q&A shares the stage"
        assert ctx["qa_status"] == pipeline.STAGE_OK
        assert ctx["qa_answers"][0]["answer"] == REAL_ANSWER
        assert CL_OPENING in (ctx["cover_letter_body"] or "")

        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_OK
        written = (run_dir / COVER_LETTER_TEX).read_text()
        assert CL_OPENING in written


# ── Post-review P1 fix: the mixed case must not lose the body ─────────────

# A compliant reply when real questions were ALSO asked: the real answer is
# structured, and the cover-letter prose is returned inside the delimiters the
# synthetic question asks for (a delimiter is content, not document metadata).
MIXED_DELIMITED_RESPONSE = (
    f"### Q: {REAL_QUESTION}\n### A: {REAL_ANSWER}\n\n"
    "<cover_letter_body>\n" + CL_BODY + "\n</cover_letter_body>\n"
)

# Same shape but the model ignored the delimiter instruction. The body cannot be
# attributed without guessing, so this must be a truthful failure.
MIXED_UNDELIMITED_RESPONSE = (
    f"### Q: {REAL_QUESTION}\n### A: {REAL_ANSWER}\n\n" + CL_BODY
)

REFUSAL_RESPONSE = (
    "I can't write a cover letter without more detail about the role and the "
    "company's priorities. Please share the job description and I will draft one."
)


class TestMixedRunStillDeliversTheCoverLetter:
    def test_body_is_recovered_when_real_questions_are_also_asked(
        self, qa_env, monkeypatch
    ):
        """The pilot's cause is the prompt, not the absence of other questions."""
        run_dir = qa_env / RUN_ID
        ctx, stub = _run_qa(
            run_dir,
            monkeypatch,
            MIXED_DELIMITED_RESPONSE,
            questions=(REAL_QUESTION,),
        )
        assert len(stub.calls) == 2, "draft + one mandatory prune pass"
        assert ctx["qa_status"] == pipeline.STAGE_OK
        # The Q/A parser over-captures the trailing prose (pre-existing strategy-1
        # behaviour), so the real answer is asserted by containment; the cover
        # letter is recovered separately through the explicit delimiter.
        assert REAL_ANSWER in ctx["qa_answers"][0]["answer"]

        body = ctx["cover_letter_body"] or ""
        assert CL_OPENING in body and CL_MIDDLE in body
        assert REAL_QUESTION not in body, "another question must not leak in"
        assert "cover_letter_body>" not in body, "delimiters are stripped"

        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_OK
        assert CL_OPENING in (run_dir / COVER_LETTER_TEX).read_text()

    def test_undelimited_mixed_reply_is_a_truthful_failure(
        self, qa_env, monkeypatch
    ):
        """A body that cannot be attributed is never guessed at."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(
            run_dir,
            monkeypatch,
            MIXED_UNDELIMITED_RESPONSE,
            questions=(REAL_QUESTION,),
        )
        assert ctx["cover_letter_body"] is None
        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED
        assert not (run_dir / COVER_LETTER_TEX).exists()

    def test_answering_only_the_real_question_stays_a_truthful_failure(
        self, qa_env, monkeypatch
    ):
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(
            run_dir, monkeypatch, QA_ONLY_RESPONSE, questions=(REAL_QUESTION,)
        )
        assert ctx["cover_letter_body"] is None
        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED

    def test_refusal_is_never_shipped_as_a_cover_letter(self, qa_env, monkeypatch):
        """A non-body must fail rather than become the delivered artifact."""
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, REFUSAL_RESPONSE)
        assert ctx["cover_letter_body"] is None
        _compile(ctx, monkeypatch)
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED
        assert not (run_dir / COVER_LETTER_TEX).exists()

    def test_fenced_body_is_unwrapped(self, qa_env, monkeypatch):
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, f"```\n{CL_BODY}\n```")
        body = ctx["cover_letter_body"] or ""
        assert CL_OPENING in body
        assert "```" not in body

    def test_role_title_special_characters_are_escaped(self, qa_env, monkeypatch):
        """A posting title containing '&' must not break the LaTeX.

        Regression for the rerun: the role title "... Traffic & Acquisition ..."
        was substituted unescaped, so pdflatex failed with "Misplaced alignment
        tab character &" and the requested cover letter PDF was never produced.
        """
        run_dir = qa_env / RUN_ID
        ctx, _ = _run_qa(run_dir, monkeypatch, CL_BODY)
        ctx["job"]["title"] = "Senior Product Manager - Traffic & Acquisition"
        _compile(ctx, monkeypatch)

        written = (run_dir / COVER_LETTER_TEX).read_text()
        assert r"Traffic \& Acquisition" in written
        assert "Traffic & Acquisition" not in written
        assert ctx["cover_letter_status"] == pipeline.STAGE_OK
        pdf = Path(ctx["cover_letter_pdf_path"])
        assert pdf.exists() and pdf.stat().st_size > 0
