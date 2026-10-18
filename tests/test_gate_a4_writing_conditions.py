"""Gate A.4: conditional writing stages, opt-in interview prep, and truthful
optional-stage status.

Guards the outcomes of Gate A.4:

  1. Q&A generation runs only when real application questions exist;
  2. cover-letter generation runs only when it is actually requested;
  3. interview prep is opt-in and never runs on a normal generation;
  4. reviewer / ATS statuses distinguish success, failure and intentional skip;
  5. no optional-stage failure aborts or invalidates the resume package.

Run with: pytest tests/test_gate_a4_writing_conditions.py -v
"""

import io
import json
import re
import sys
from pathlib import Path
from typing import cast

import pytest
from rich.console import Console

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import modules.pipeline as pipeline  # noqa: E402
from modules import sendability  # noqa: E402

QUESTION = "Why do you want this role?"

# Long enough to satisfy the cover-letter body minimum length check.
LONG_ANSWER = "Because the mission fits my experience and I can contribute immediately. " * 3
QA_PAYLOAD = f"### Q: {QUESTION}\n\n### A: {LONG_ANSWER}\n"
CL_ONLY_PAYLOAD = f"### Q: Write a cover letter body\n\n### A: {LONG_ANSWER}\n"

ATS_OK_PAYLOAD = (
    "```json\n"
    + json.dumps(
        {
            "company": "TestCo",
            "job_title": "PM",
            "coverage_score": {"coverage_pct": 82, "verdict": "PASS"},
            "suggested_edits": [],
            "consistency": {},
        }
    )
    + "\n```\n"
)
ATS_PROSE_PAYLOAD = "I was unable to complete the ATS check for this role."

REVIEWER_OK_PAYLOAD = (
    "## Part A\n\n```json\n"
    + json.dumps(
        [
            {
                "old_string": "Senior Product Manager with 8+ years",
                "new_string": "Senior Product Manager with 9 years",
                "reason": "keyword match",
            }
        ]
    )
    + "\n```\n\n## Part B\n\nSUGGESTION: tighten the summary\n"
)
REVIEWER_JUNK_PAYLOAD = "Sorry, I cannot review this draft right now."


def _console():
    return Console(file=io.StringIO())


def _no_llm():
    """These steps take an llm argument that they never use in these paths."""
    return cast(pipeline.LLMClient, None)


def _llm(client):
    """Type-only cast: the fakes implement the LLMClient surface used here."""
    return cast(pipeline.LLMClient, client)


def _ats_client(monkeypatch, client):
    """B.1.5: ``step_ats_check`` owns its route, so inject through its factory."""
    monkeypatch.setattr(
        pipeline, "create_ats_client", lambda: cast(pipeline.LLMClient, client)
    )


class _CountingClient:
    """Fake LLM client that counts calls and optionally fails."""

    def __init__(self, payloads=(), fail=False):
        self.payloads = list(payloads)
        self.calls = 0
        self.fail = fail

    def model_name(self):
        return "fake-model"

    def generate(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        return self.payloads.pop(0) if self.payloads else ""


def _run_dir(tmp_path):
    run_dir = tmp_path / "TestCo_2026-10-05T194512_ab12cd"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _qa_ctx(tmp_path, questions=(), cover_letter=False):
    return {
        "run_dir": str(_run_dir(tmp_path)),
        "company_safe": "TestCo",
        "job": {
            "title": "PM",
            "company": "TestCo",
            "url": "https://example.com/job/1",
            "description": "A product management role.",
        },
        "master_resume": "### Experience\n\n**Acme** — Work.",
        "all_questions": list(questions),
        "generate_cover_letter": cover_letter,
        "company_url": None,
    }


def _stub_prompt_loaders(monkeypatch):
    """Keep the writing stages hermetic: no research, no auxiliary prompt files."""
    monkeypatch.setattr(pipeline, "research_company", lambda *a, **k: "")
    monkeypatch.setattr(pipeline, "_load_qa_templates", lambda *a, **k: "")
    monkeypatch.setattr(pipeline, "_load_behavioral_profile", lambda *a, **k: "")
    monkeypatch.setattr(pipeline, "_load_ai_pm_context", lambda *a, **k: "")
    monkeypatch.setattr(pipeline, "_load_voice_prefix", lambda *a, **k: "")
    monkeypatch.setattr(pipeline, "_is_ai_heavy_jd", lambda *a, **k: False)


def _run_qa(monkeypatch, ctx, payloads=(), fail=False):
    client = _CountingClient(payloads, fail=fail)
    monkeypatch.setattr(pipeline, "create_qa_client", lambda *a, **k: client)
    _stub_prompt_loaders(monkeypatch)
    pipeline.step_generate_qa(ctx, _no_llm(), _console())
    return client


# ─── Q&A conditionality ──────────────────────────────────────────


class TestQaConditionality:
    def test_no_questions_makes_zero_llm_calls(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=())
        client = _run_qa(monkeypatch, ctx)
        assert client.calls == 0

    def test_no_questions_is_intentionally_skipped(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=())
        _run_qa(monkeypatch, ctx)
        assert ctx["qa_required"] is False
        assert ctx["qa_status"] == pipeline.STAGE_SKIPPED
        assert ctx["qa_skip_reason"] == pipeline.STAGE_SKIP_NO_APPLICATION_QUESTIONS

    def test_no_questions_creates_no_artifact(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=())
        _run_qa(monkeypatch, ctx)
        run_dir = Path(ctx["run_dir"])
        assert list(run_dir.glob("qa_*.md")) == []
        assert list(run_dir.glob("form_data_*.json")) == []
        assert ctx["qa_answers"] == []

    def test_blank_questions_are_not_questions(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=["", "   "])
        client = _run_qa(monkeypatch, ctx)
        assert client.calls == 0
        assert ctx["qa_status"] == pipeline.STAGE_SKIPPED

    def test_questions_present_runs_qa(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION])
        client = _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        assert client.calls == 1
        assert ctx["qa_required"] is True
        assert ctx["qa_status"] == pipeline.STAGE_OK
        assert ctx["qa_answers"]

    def test_qa_failure_is_non_fatal_and_recorded(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION])
        client = _run_qa(monkeypatch, ctx, fail=True)
        assert client.calls == 1
        assert ctx["qa_status"] == pipeline.STAGE_FAILED
        assert ctx["qa_status"] != pipeline.STAGE_OK
        assert ctx["qa_answers"] == []


# ─── Cover-letter conditionality ─────────────────────────────────


class TestCoverLetterConditionality:
    def test_not_requested_makes_zero_llm_calls(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=False)
        client = _run_qa(monkeypatch, ctx)
        assert client.calls == 0
        assert ctx["cover_letter_required"] is False

    def test_not_requested_records_skipped(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION], cover_letter=False)
        _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        pipeline.step_compile_cover_letter(ctx, _no_llm(), _console())
        assert ctx["cover_letter_status"] == pipeline.STAGE_SKIPPED
        assert ctx["cover_letter_skip_reason"] == pipeline.STAGE_SKIP_NOT_REQUESTED

    def test_qa_only_never_asks_for_a_cover_letter(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION], cover_letter=False)
        _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        assert ctx["qa_status"] == pipeline.STAGE_OK
        # The synthetic cover-letter question must not have been injected.
        assert all("cover letter" not in q.lower() for q in ctx["all_questions"])

    def test_cover_letter_only_uses_draft_plus_prune_and_skips_qa(
        self, tmp_path, monkeypatch
    ):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=True)
        client = _run_qa(monkeypatch, ctx, payloads=[CL_ONLY_PAYLOAD])
        assert client.calls == 2, "draft + one mandatory prune pass"
        assert ctx["qa_required"] is False
        assert ctx["qa_status"] == pipeline.STAGE_SKIPPED
        assert ctx["cover_letter_required"] is True

    def test_both_requested_uses_one_shared_call(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION], cover_letter=True)
        client = _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        assert client.calls == 1
        assert ctx["qa_status"] == pipeline.STAGE_OK
        assert ctx["cover_letter_required"] is True

    def test_neither_requested_makes_zero_writing_calls(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=False)
        client = _run_qa(monkeypatch, ctx)
        assert client.calls == 0
        pipeline.step_compile_cover_letter(ctx, _no_llm(), _console())
        assert ctx["cover_letter_status"] == pipeline.STAGE_SKIPPED

    def test_requested_without_a_usable_body_is_failed_not_ok(
        self, tmp_path, monkeypatch
    ):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=True)
        _run_qa(monkeypatch, ctx, fail=True)
        pipeline.step_compile_cover_letter(ctx, _no_llm(), _console())
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED

    def test_requested_cover_letter_succeeds(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=True)
        _run_qa(monkeypatch, ctx, payloads=[CL_ONLY_PAYLOAD])
        # Success must be backed by a real, non-empty artifact: a requested cover
        # letter is only OK when the final PDF actually exists.
        pdf = Path(ctx["run_dir"]) / "Cover-Letter.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake cover letter")
        monkeypatch.setattr(
            pipeline,
            "compile_and_inspect",
            lambda *a, **k: {"ok": True, "pdf_path": str(pdf)},
        )
        pipeline.step_compile_cover_letter(ctx, _no_llm(), _console())
        assert ctx["cover_letter_status"] == pipeline.STAGE_OK
        assert ctx["cover_letter_pdf_path"] == str(pdf)

    def test_cover_letter_compile_failure_is_recorded_not_raised(
        self, tmp_path, monkeypatch
    ):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=True)
        _run_qa(monkeypatch, ctx, payloads=[CL_ONLY_PAYLOAD])
        monkeypatch.setattr(
            pipeline,
            "compile_and_inspect",
            lambda *a, **k: {"ok": False, "error": "pdflatex failed", "details": []},
        )
        pipeline.step_compile_cover_letter(ctx, _no_llm(), _console())
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED


# ─── Interview prep opt-in ───────────────────────────────────────


def _interview_ctx(tmp_path, requested):
    run_dir = _run_dir(tmp_path)
    ctx = {
        "run_dir": str(run_dir),
        "company_safe": "TestCo",
        "job": {
            "title": "PM",
            "company": "TestCo",
            "description": "A product management role.",
        },
        "master_resume": "### Experience",
        "qa_answers": [],
    }
    if requested:
        ctx["interview_prep_requested"] = True
    return ctx


class TestInterviewPrepOptIn:
    def test_not_requested_makes_zero_llm_calls(self, tmp_path, monkeypatch):
        ctx = _interview_ctx(tmp_path, requested=False)
        client = _CountingClient()
        monkeypatch.setattr(pipeline, "create_interview_client", lambda *a, **k: client)
        pipeline.step_generate_interview_prep(ctx, _no_llm(), _console())
        assert client.calls == 0

    def test_not_requested_records_skipped_and_writes_no_artifact(
        self, tmp_path, monkeypatch
    ):
        ctx = _interview_ctx(tmp_path, requested=False)
        client = _CountingClient()
        monkeypatch.setattr(pipeline, "create_interview_client", lambda *a, **k: client)
        pipeline.step_generate_interview_prep(ctx, _no_llm(), _console())
        assert ctx["interview_prep_status"] == pipeline.STAGE_SKIPPED
        assert ctx["interview_prep_skip_reason"] == pipeline.STAGE_SKIP_NOT_REQUESTED
        assert "interview_prep_path" not in ctx
        assert list(Path(ctx["run_dir"]).glob("interview_prep_*.md")) == []

    def test_explicit_opt_in_runs(self, tmp_path, monkeypatch):
        ctx = _interview_ctx(tmp_path, requested=True)
        client = _CountingClient(["# Interview Preparation\n\n## Company Context\n"])
        monkeypatch.setattr(pipeline, "create_interview_client", lambda *a, **k: client)
        monkeypatch.setattr(pipeline, "_load_prompt", lambda *a, **k: "prompt")
        pipeline.step_generate_interview_prep(ctx, _no_llm(), _console())
        assert client.calls == 1
        assert ctx["interview_prep_status"] == pipeline.STAGE_OK
        assert Path(ctx["interview_prep_path"]).exists()

    def test_opt_in_failure_is_non_fatal_and_recorded(self, tmp_path, monkeypatch):
        ctx = _interview_ctx(tmp_path, requested=True)
        client = _CountingClient(fail=True)
        monkeypatch.setattr(pipeline, "create_interview_client", lambda *a, **k: client)
        monkeypatch.setattr(pipeline, "_load_prompt", lambda *a, **k: "prompt")
        pipeline.step_generate_interview_prep(ctx, _no_llm(), _console())
        assert ctx["interview_prep_status"] == pipeline.STAGE_FAILED
        assert ctx["interview_prep_status"] != pipeline.STAGE_OK


# ─── F2: ATS status fidelity ─────────────────────────────────────


def _ats_ctx(tmp_path):
    return {
        "run_dir": str(_run_dir(tmp_path)),
        "company_safe": "TestCo",
        "job": {
            "title": "PM",
            "company": "TestCo",
            "description": "A product management role.",
        },
        "tailored_latex": "\\section*{Experience}",
        "skills_inventory": "",
    }


class TestAtsStatusFidelity:
    def test_usable_report_is_ok(self, tmp_path, monkeypatch):
        ctx = _ats_ctx(tmp_path)
        client = _CountingClient([ATS_OK_PAYLOAD])
        _ats_client(monkeypatch, client)
        pipeline.step_ats_check(ctx, _llm(client), _console())
        assert ctx["ats_status"] == pipeline.STAGE_OK
        assert (ctx.get("ats_report") or {}).get("json")
        assert client.calls == 1, "the ATS stage must route through its own factory"

    def test_unparseable_report_is_not_ok(self, tmp_path, monkeypatch):
        ctx = _ats_ctx(tmp_path)
        _ats_client(monkeypatch, _CountingClient([ATS_PROSE_PAYLOAD]))
        pipeline.step_ats_check(
            ctx, _llm(_CountingClient([ATS_PROSE_PAYLOAD])), _console()
        )
        assert ctx["ats_status"] == pipeline.STAGE_FAILED
        assert ctx["ats_status"] != pipeline.STAGE_OK

    def test_provider_failure_is_failed(self, tmp_path, monkeypatch):
        ctx = _ats_ctx(tmp_path)
        _ats_client(monkeypatch, _CountingClient(fail=True))
        pipeline.step_ats_check(ctx, _llm(_CountingClient(fail=True)), _console())
        assert ctx["ats_status"] == pipeline.STAGE_FAILED

    def test_intentional_skip_is_skipped(self, tmp_path, monkeypatch):
        ctx = _ats_ctx(tmp_path)
        ctx["skip_ats"] = True
        client = _CountingClient()
        _ats_client(monkeypatch, client)
        pipeline.step_ats_check(ctx, _llm(client), _console())
        assert client.calls == 0
        assert ctx["ats_status"] == pipeline.STAGE_SKIPPED
        assert ctx["ats_skip_reason"] == pipeline.STAGE_SKIP_NOT_REQUESTED


# ─── F3: reviewer status fidelity ────────────────────────────────


def _review_ctx(tmp_path):
    return {
        "run_dir": str(_run_dir(tmp_path)),
        "company_safe": "TestCo",
        "job": {
            "title": "PM",
            "company": "TestCo",
            "url": "https://example.com/job/1",
            "description": "A product management role.",
        },
        "master_resume": "### Experience",
        "tailoring_brief": "brief",
        "tailored_latex": "\\section*{Experience}",
    }


def _run_review(monkeypatch, ctx, payloads=(), fail=False):
    client = _CountingClient(payloads, fail=fail)
    monkeypatch.setattr(pipeline, "create_reviewer_client_v2", lambda *a, **k: client)
    monkeypatch.setattr(pipeline, "_load_behavioral_profile", lambda *a, **k: "")
    monkeypatch.setattr(pipeline, "_load_prompt", lambda *a, **k: "prompt")
    pipeline.step_review_drafts(ctx, _no_llm(), _console())
    return client


class TestReviewerStatusFidelity:
    def test_usable_feedback_is_ok(self, tmp_path, monkeypatch):
        ctx = _review_ctx(tmp_path)
        _run_review(monkeypatch, ctx, payloads=[REVIEWER_OK_PAYLOAD])
        assert ctx["reviewer_status"] == pipeline.STAGE_OK

    def test_empty_feedback_is_not_ok(self, tmp_path, monkeypatch):
        ctx = _review_ctx(tmp_path)
        _run_review(monkeypatch, ctx, payloads=[REVIEWER_JUNK_PAYLOAD])
        assert ctx["reviewer_status"] == pipeline.STAGE_FAILED
        assert ctx["reviewer_status"] != pipeline.STAGE_OK

    def test_provider_failure_is_failed(self, tmp_path, monkeypatch):
        ctx = _review_ctx(tmp_path)
        _run_review(monkeypatch, ctx, fail=True)
        assert ctx["reviewer_status"] == pipeline.STAGE_FAILED

    def test_intentional_skip_is_skipped_without_a_call(self, tmp_path, monkeypatch):
        ctx = _review_ctx(tmp_path)
        ctx["skip_reviewer"] = True
        client = _run_review(monkeypatch, ctx)
        assert client.calls == 0
        assert ctx["reviewer_status"] == pipeline.STAGE_SKIPPED


# ─── Gate integration: optional statuses must not change the verdict ──


def _gate(tmp_path, outcome, **overrides):
    run_dir = _run_dir(tmp_path)
    tex = run_dir / "Resume.tex"
    tex.write_text((PROJECT_ROOT / "templates" / "resume.tex").read_text())
    pdf = run_dir / "Resume.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    ctx = {
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "tex_path": str(tex),
        "pdf_path": str(pdf),
        "master_resume": "plain master",
        "tailoring_mode": "targeted",
        "tailoring_outcome": outcome,
    }
    ctx.update(overrides)
    pipeline.step_evaluate_sendability(ctx, _no_llm(), _console())
    return ctx["sendability"]


class TestGateIntegration:
    def test_intentional_skips_produce_no_warnings(self, tmp_path):
        verdict = _gate(
            tmp_path,
            sendability.TAILORING_OUTCOME_TAILORED,
            reviewer_status=pipeline.STAGE_SKIPPED,
            ats_status=pipeline.STAGE_SKIPPED,
        )
        assert verdict["status"] == sendability.READY_TO_SEND
        assert verdict["warnings"] == []

    def test_reviewer_failure_alone_is_warning_not_hold(self, tmp_path):
        verdict = _gate(
            tmp_path,
            sendability.TAILORING_OUTCOME_TAILORED,
            reviewer_status=pipeline.STAGE_FAILED,
            ats_status=pipeline.STAGE_OK,
        )
        assert verdict["status"] == sendability.READY_WITH_WARNINGS
        assert [w["code"] for w in verdict["warnings"]] == [
            sendability.WARN_REVIEWER_FAILED
        ]

    def test_ats_failure_alone_is_warning_not_hold(self, tmp_path):
        verdict = _gate(
            tmp_path,
            sendability.TAILORING_OUTCOME_TAILORED,
            reviewer_status=pipeline.STAGE_OK,
            ats_status=pipeline.STAGE_FAILED,
        )
        assert verdict["status"] == sendability.READY_WITH_WARNINGS
        assert [w["code"] for w in verdict["warnings"]] == [
            sendability.WARN_ATS_SEMANTIC_UNAVAILABLE
        ]

    def test_absent_optional_stages_do_not_warn(self, tmp_path):
        verdict = _gate(tmp_path, sendability.TAILORING_OUTCOME_TAILORED)
        assert verdict["status"] == sendability.READY_TO_SEND
        assert verdict["warnings"] == []

    def test_missing_status_keys_are_not_failures(self, tmp_path):
        """A stage that never ran is not a warning; only STAGE_FAILED is."""
        run_dir = tmp_path / "evidence"
        run_dir.mkdir()
        for value in (None, "", "OK", "SKIPPED", "garbage"):
            verdict = _gate(
                tmp_path, sendability.TAILORING_OUTCOME_TAILORED, reviewer_status=value
            )
            assert verdict["status"] == sendability.READY_TO_SEND, value
            assert verdict["warnings"] == [], value


def test_no_generic_qa_artifact_when_there_are_no_questions(tmp_path, monkeypatch):
    """Skipped Q&A must not fabricate output to satisfy downstream code."""
    ctx = _qa_ctx(tmp_path, questions=())
    _run_qa(monkeypatch, ctx)
    assert ctx["qa_answers"] == []
    run_dir = Path(ctx["run_dir"])
    assert not any(run_dir.iterdir())


def test_cover_letter_body_is_not_generated_as_a_side_effect(tmp_path, monkeypatch):
    """Q&A-only runs must not smuggle a cover-letter body into the answers."""
    ctx = _qa_ctx(tmp_path, questions=[QUESTION], cover_letter=False)
    _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
    assert len(ctx["qa_answers"]) == 1
    assert re.search(r"cover letter", ctx["qa_answers"][0]["question"], re.I) is None


# ═══════════════════════════════════════════════════════════════════
# Gate A.4.1 - fidelity cleanup
# ═══════════════════════════════════════════════════════════════════

# Two answers where the cover-letter answer is deliberately NOT first, so any
# positional extraction would pick the unrelated answer.
MIXED_PAYLOAD = (
    f"### Q: {QUESTION}\n\n### A: An unrelated answer, long enough to look usable. "
    f"{LONG_ANSWER}\n\n"
    f"### Q: {pipeline.COVER_LETTER_QUESTION_PREFIX}\n\n### A: {LONG_ANSWER}\n"
)
USER_CL_PAYLOAD = f"### Q: Cover letter\n\n### A: {LONG_ANSWER}\n"


def _broken_write(monkeypatch, *prefixes):
    """Make Path.write_text raise for filenames under the given prefixes."""
    real = Path.write_text

    def _boom(self, *args, **kwargs):
        if self.name.startswith(prefixes):
            raise OSError("simulated disk failure")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _boom)


class TestCoverLetterIdentity:
    """A.4.1-A: the cover-letter body is found by identity, never position."""

    def test_unrelated_answer_never_becomes_the_cover_letter_body(
        self, tmp_path, monkeypatch
    ):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION], cover_letter=True)
        _run_qa(monkeypatch, ctx, payloads=[MIXED_PAYLOAD])
        assert len(ctx["qa_answers"]) == 2
        assert ctx["cover_letter_body"] == LONG_ANSWER.strip()
        assert "unrelated answer" not in ctx["cover_letter_body"]
        assert ctx["cover_letter_body"] != ctx["qa_answers"][0]["answer"].strip()

    def test_body_selected_from_a_user_supplied_cover_letter_question(
        self, tmp_path, monkeypatch
    ):
        """already_has_cl suppresses injection; identity still finds the body."""
        ctx = _qa_ctx(tmp_path, questions=["Cover letter"], cover_letter=True)
        _run_qa(monkeypatch, ctx, payloads=[USER_CL_PAYLOAD])
        assert ctx["cover_letter_body"] == LONG_ANSWER.strip()

    def test_qa_only_leaves_no_cover_letter_state(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION], cover_letter=False)
        _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        assert ctx["cover_letter_body"] is None
        assert ctx["qa_status"] == pipeline.STAGE_OK
        run_dir = Path(ctx["run_dir"])
        form = json.loads(next(run_dir.glob("form_data_*.json")).read_text())
        assert "cover_letter" not in form

    def test_cover_letter_only_still_works(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=True)
        client = _run_qa(monkeypatch, ctx, payloads=[CL_ONLY_PAYLOAD])
        assert client.calls == 2, "draft + one mandatory prune pass"
        assert ctx["cover_letter_body"] == LONG_ANSWER.strip()
        assert ctx["qa_status"] == pipeline.STAGE_SKIPPED
        assert ctx["qa_status"] != pipeline.STAGE_FAILED

    def test_both_requested_share_the_stage_with_independent_statuses(
        self, tmp_path, monkeypatch
    ):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION], cover_letter=True)
        client = _run_qa(monkeypatch, ctx, payloads=[MIXED_PAYLOAD])
        assert client.calls == 2, "draft + one mandatory prune pass"
        assert ctx["qa_status"] == pipeline.STAGE_OK
        assert ctx["cover_letter_body"] is not None

    def test_qa_only_keeps_cover_letter_skipped(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION], cover_letter=False)
        _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        pipeline.step_compile_cover_letter(ctx, _no_llm(), _console())
        assert ctx["cover_letter_status"] == pipeline.STAGE_SKIPPED
        assert ctx["cover_letter_skip_reason"] == pipeline.STAGE_SKIP_NOT_REQUESTED


class TestOptionalIoBoundaries:
    """A.4.1-B: optional I/O failures must never abort the core resume pipeline."""

    def test_research_failure_is_non_fatal(self, tmp_path, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("research backend down")

        monkeypatch.setattr(pipeline, "research_company", _boom)
        ctx = _qa_ctx(tmp_path, questions=[QUESTION])
        client = _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        assert client.calls == 1
        assert ctx["company_research"] == ""
        assert ctx["qa_status"] == pipeline.STAGE_OK

    def test_qa_artifact_write_failure_is_non_fatal(self, tmp_path, monkeypatch):
        _broken_write(monkeypatch, "qa_")
        ctx = _qa_ctx(tmp_path, questions=[QUESTION])
        _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        assert ctx["qa_status"] == pipeline.STAGE_OK

    def test_form_data_write_failure_is_non_fatal(self, tmp_path, monkeypatch):
        _broken_write(monkeypatch, "form_data_")
        ctx = _qa_ctx(tmp_path, questions=[QUESTION])
        _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        assert ctx["qa_status"] == pipeline.STAGE_OK

    def test_cover_letter_compile_failure_is_non_fatal(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=True)
        _run_qa(monkeypatch, ctx, payloads=[CL_ONLY_PAYLOAD])
        monkeypatch.setattr(
            pipeline,
            "compile_and_inspect",
            lambda *a, **k: {"ok": False, "error": "pdflatex down", "details": []},
        )
        pipeline.step_compile_cover_letter(ctx, _no_llm(), _console())
        assert ctx["cover_letter_status"] == pipeline.STAGE_FAILED

    def test_interview_prep_failure_is_non_fatal(self, tmp_path, monkeypatch):
        ctx = _interview_ctx(tmp_path, requested=True)
        monkeypatch.setattr(
            pipeline, "create_interview_client", lambda *a, **k: _CountingClient(fail=True)
        )
        monkeypatch.setattr(pipeline, "_load_prompt", lambda *a, **k: "prompt")
        pipeline.step_generate_interview_prep(ctx, _no_llm(), _console())
        assert ctx["interview_prep_status"] == pipeline.STAGE_FAILED


class TestReviewerStructureSemantics:
    """A.4.1-C: success means a valid review was recognised, not that it criticised."""

    @pytest.mark.parametrize(
        "payload",
        [
            "## Part A\n```json\n[]\n```\n## Part B\nThe draft matches the brief.",
            "## Part A\n```json\n[]\n```",
            "## Part B\nNo narrative suggestions were needed.",
            REVIEWER_OK_PAYLOAD,
        ],
        ids=["clean_with_part_b", "clean_part_a_only", "part_b_only", "findings"],
    )
    def test_recognised_review_is_ok(self, payload, tmp_path, monkeypatch):
        ctx = _review_ctx(tmp_path)
        _run_review(monkeypatch, ctx, payloads=[payload])
        assert ctx["reviewer_status"] == pipeline.STAGE_OK

    @pytest.mark.parametrize(
        "payload",
        ["", "Sorry, I cannot review this draft right now.", "totally unstructured prose"],
        ids=["empty", "refusal", "prose"],
    )
    def test_unrecognisable_review_is_failed(self, payload, tmp_path, monkeypatch):
        ctx = _review_ctx(tmp_path)
        _run_review(monkeypatch, ctx, payloads=[payload])
        assert ctx["reviewer_status"] == pipeline.STAGE_FAILED

    def test_provider_exception_is_failed(self, tmp_path, monkeypatch):
        ctx = _review_ctx(tmp_path)
        _run_review(monkeypatch, ctx, fail=True)
        assert ctx["reviewer_status"] == pipeline.STAGE_FAILED

    def test_intentional_skip_is_skipped_without_a_call(self, tmp_path, monkeypatch):
        ctx = _review_ctx(tmp_path)
        ctx["skip_reviewer"] = True
        client = _run_review(monkeypatch, ctx)
        assert client.calls == 0
        assert ctx["reviewer_status"] == pipeline.STAGE_SKIPPED

    def test_parser_reports_structure_explicitly(self):
        clean = pipeline._parse_review_feedback(
            "## Part A\n```json\n[]\n```\n## Part B\nNothing to change.",
            _console(),
        )
        assert clean["part_a"] == [] and clean["part_b"] == []
        assert clean["structure_recognized"] is True
        junk = pipeline._parse_review_feedback("no structure here", _console())
        assert junk["structure_recognized"] is False

    @pytest.mark.parametrize(
        "heading",
        ["### Part A - Structured JSON Edits", "### Part A", "# Part A", "## Part A"],
    )
    def test_prompt_mandated_heading_levels_are_recognised(self, heading):
        """prompts/reviewer.md mandates '### Part A'/'### Part B' (h3)."""
        part_b_heading = heading.replace("Part A", "Part B")
        raw = (
            f"{heading}\n\nNo mechanical edits needed.\n\n"
            f"{part_b_heading}\n\nSUGGESTION: tighten the summary"
        )
        fb = pipeline._parse_review_feedback(raw, _console())
        assert fb["structure_recognized"] is True, heading
        assert fb["part_b"], f"Part B suggestions were discarded for {heading}"

    def test_prompt_format_clean_review_is_ok_end_to_end(self, tmp_path, monkeypatch):
        """The canonical prompt reply must not be recorded FAILED."""
        payload = (
            "### Part A - Structured JSON Edits\n\nNo mechanical edits needed.\n\n"
            "### Part B - Narrative Suggestions\n\nSUGGESTION: tighten the summary"
        )
        ctx = _review_ctx(tmp_path)
        _run_review(monkeypatch, ctx, payloads=[payload])
        assert ctx["reviewer_status"] == pipeline.STAGE_OK
        assert ctx["review_feedback"]["part_b"]


class TestAtsUsabilitySemantics:
    """A.4.1-D: OK requires a structurally usable ATS payload."""

    def test_valid_payload_is_ok(self, tmp_path, monkeypatch):
        ctx = _ats_ctx(tmp_path)
        _ats_client(monkeypatch, _CountingClient([ATS_OK_PAYLOAD]))
        pipeline.step_ats_check(ctx, _llm(_CountingClient([ATS_OK_PAYLOAD])), _console())
        assert ctx["ats_status"] == pipeline.STAGE_OK

    @pytest.mark.parametrize(
        "payload",
        [
            '```json\n{"error": "cannot analyse"}\n```',
            '```json\n{"note": "insufficient data"}\n```',
            ATS_PROSE_PAYLOAD,
            "",
        ],
        ids=["error_key", "arbitrary_truthy", "prose", "empty"],
    )
    def test_unusable_payload_is_failed(self, payload, tmp_path, monkeypatch):
        ctx = _ats_ctx(tmp_path)
        _ats_client(monkeypatch, _CountingClient([payload]))
        pipeline.step_ats_check(ctx, _llm(_CountingClient([payload])), _console())
        assert ctx["ats_status"] == pipeline.STAGE_FAILED

    def test_provider_failure_is_failed(self, tmp_path, monkeypatch):
        ctx = _ats_ctx(tmp_path)
        _ats_client(monkeypatch, _CountingClient(fail=True))
        pipeline.step_ats_check(ctx, _llm(_CountingClient(fail=True)), _console())
        assert ctx["ats_status"] == pipeline.STAGE_FAILED

    def test_intentional_skip_is_skipped(self, tmp_path, monkeypatch):
        ctx = _ats_ctx(tmp_path)
        ctx["skip_ats"] = True
        client = _CountingClient()
        _ats_client(monkeypatch, client)
        pipeline.step_ats_check(ctx, _llm(client), _console())
        assert client.calls == 0
        assert ctx["ats_status"] == pipeline.STAGE_SKIPPED

    @pytest.mark.parametrize(
        "report,expected",
        [
            ({"json": {"coverage_score": {"coverage_pct": 80}}}, True),
            ({"json": {"coverage_score": {}}}, True),
            ({"json": {"error": "x"}}, False),
            ({"json": [1, 2]}, False),
            ({"json": None}, False),
            ({"json": {"coverage_score": "80"}}, False),
            (None, False),
        ],
    )
    def test_is_usable_ats_report(self, report, expected):
        assert pipeline.is_usable_ats_report(report) is expected


class TestSkipReporting:
    """A.4.1-E: intentional skip renders SKIPPED, never PASS, never a warning."""

    def test_reviewer_skip_check_is_skipped(self, tmp_path):
        verdict = _gate(
            tmp_path,
            sendability.TAILORING_OUTCOME_TAILORED,
            reviewer_status=pipeline.STAGE_SKIPPED,
        )
        assert verdict["checks"]["reviewer"] == sendability.CHECK_SKIPPED
        assert verdict["checks"]["reviewer"] != sendability.CHECK_PASS
        assert verdict["warnings"] == []
        assert verdict["status"] == sendability.READY_TO_SEND

    def test_ats_skip_check_is_skipped(self, tmp_path):
        verdict = _gate(
            tmp_path,
            sendability.TAILORING_OUTCOME_TAILORED,
            ats_status=pipeline.STAGE_SKIPPED,
        )
        assert verdict["checks"]["ats_semantic"] == sendability.CHECK_SKIPPED
        assert verdict["checks"]["ats_semantic"] != sendability.CHECK_PASS
        assert verdict["warnings"] == []
        assert verdict["status"] == sendability.READY_TO_SEND

    def test_failed_reviewer_still_warns(self, tmp_path):
        verdict = _gate(
            tmp_path,
            sendability.TAILORING_OUTCOME_TAILORED,
            reviewer_status=pipeline.STAGE_FAILED,
        )
        assert [w["code"] for w in verdict["warnings"]] == [
            sendability.WARN_REVIEWER_FAILED
        ]
        assert verdict["status"] == sendability.READY_WITH_WARNINGS

    def test_failed_ats_still_warns(self, tmp_path):
        verdict = _gate(
            tmp_path,
            sendability.TAILORING_OUTCOME_TAILORED,
            ats_status=pipeline.STAGE_FAILED,
        )
        assert [w["code"] for w in verdict["warnings"]] == [
            sendability.WARN_ATS_SEMANTIC_UNAVAILABLE
        ]
        assert verdict["status"] == sendability.READY_WITH_WARNINGS


class TestFinalizeOptionalStageWarnings:
    """A.4.1-F: deterministic warning finalization that can never weaken a verdict."""

    @pytest.mark.parametrize(
        "code",
        [
            sendability.WARN_QA_FAILED,
            sendability.WARN_COVER_LETTER_FAILED,
            sendability.WARN_INTERVIEW_PREP_FAILED,
            sendability.WARN_COVER_LETTER_HUMAN_REVIEW_REQUIRED,
        ],
    )
    def test_ready_to_send_becomes_ready_with_warnings(self, code):
        base = sendability.evaluate_sendability(
            run_id="R",
            final_latex=None,
            resume_artifact_present=False,
            resume_artifact_bytes=0,
            pdf_present=False,
            pdf_bytes=0,
            master_resume=None,
            canonical_template=None,
            evaluated_at="T",
        )
        base = dict(base)
        base["status"] = sendability.READY_TO_SEND
        base["blockers"] = []
        out = sendability.finalize_optional_stage_warnings(base, {code: "detail"})
        assert out["status"] == sendability.READY_WITH_WARNINGS
        assert [w["code"] for w in out["warnings"]] == [code]
        assert out["checks"][code] == sendability.CHECK_WARN

    def test_multiple_failures_merge_deterministically(self):
        base = {"status": sendability.READY_TO_SEND, "warnings": [], "checks": {}}
        failures = {
            sendability.WARN_QA_FAILED: "a",
            sendability.WARN_COVER_LETTER_FAILED: "b",
            sendability.WARN_INTERVIEW_PREP_FAILED: "c",
        }
        first = sendability.finalize_optional_stage_warnings(base, failures)
        second = sendability.finalize_optional_stage_warnings(base, failures)
        assert first == second
        assert [w["code"] for w in first["warnings"]] == sorted(failures)

    def test_duplicate_codes_are_deduplicated(self):
        base = {"status": sendability.READY_TO_SEND, "warnings": [], "checks": {}}
        once = sendability.finalize_optional_stage_warnings(
            base, {sendability.WARN_QA_FAILED: "a"}
        )
        twice = sendability.finalize_optional_stage_warnings(
            once, {sendability.WARN_QA_FAILED: "a"}
        )
        assert [w["code"] for w in twice["warnings"]] == [sendability.WARN_QA_FAILED]

    def test_ready_with_warnings_remains_ready_with_warnings(self):
        base = {
            "status": sendability.READY_WITH_WARNINGS,
            "warnings": [{"code": "EXISTING", "detail": "d"}],
            "checks": {},
        }
        out = sendability.finalize_optional_stage_warnings(
            base, {sendability.WARN_QA_FAILED: "a"}
        )
        assert out["status"] == sendability.READY_WITH_WARNINGS
        assert [w["code"] for w in out["warnings"]] == ["EXISTING", sendability.WARN_QA_FAILED]

    def test_hold_is_never_changed(self):
        base = {
            "status": sendability.HOLD,
            "warnings": [],
            "checks": {},
            "blockers": [{"code": "PDF_MISSING", "detail": "x"}],
        }
        out = sendability.finalize_optional_stage_warnings(
            base, {sendability.WARN_QA_FAILED: "a"}
        )
        assert out is base
        assert out["status"] == sendability.HOLD
        assert out["blockers"] == base["blockers"]

    def test_no_failures_returns_the_same_object(self):
        base = {"status": sendability.READY_TO_SEND, "warnings": [], "checks": {}}
        assert sendability.finalize_optional_stage_warnings(base, {}) is base

    def test_ok_stages_produce_no_warning(self):
        base = {"status": sendability.READY_TO_SEND, "warnings": [], "checks": {}}
        assert sendability.finalize_optional_stage_warnings(base, {}) is base


class TestFinalizeStepIntegration:
    """A.4.1-G: the pipeline step rewrites the same report and never touches lifecycle."""

    def _finalize(self, tmp_path, **statuses):
        """Build a real ctx, run the gate, then run the finalization step."""
        run_dir = _run_dir(tmp_path)
        tex = run_dir / "Resume.tex"
        tex.write_text((PROJECT_ROOT / "templates" / "resume.tex").read_text())
        pdf = run_dir / "Resume.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        ctx = {
            "run_dir": str(run_dir),
            "run_id": run_dir.name,
            "tex_path": str(tex),
            "pdf_path": str(pdf),
            "master_resume": "plain master",
            "tailoring_mode": "targeted",
            "tailoring_outcome": sendability.TAILORING_OUTCOME_TAILORED,
        }
        ctx.update(statuses)
        pipeline.step_evaluate_sendability(ctx, _no_llm(), _console())
        pipeline.step_finalize_sendability(ctx, _no_llm(), _console())
        return ctx

    @pytest.mark.parametrize(
        "field,status",
        [
            ("qa_status", pipeline.STAGE_FAILED),
            ("cover_letter_status", pipeline.STAGE_FAILED),
            ("interview_prep_status", pipeline.STAGE_FAILED),
        ],
    )
    def test_requested_stage_failure_becomes_ready_with_warnings(
        self, field, status, tmp_path
    ):
        ctx = self._finalize(tmp_path, **{field: status})
        assert ctx["sendability"]["status"] == sendability.READY_WITH_WARNINGS
        report = json.loads(
            (Path(ctx["run_dir"]) / sendability.REPORT_FILENAME).read_text()
        )
        assert report["status"] == sendability.READY_WITH_WARNINGS
        assert report["warnings"][0]["code"] in {
            sendability.WARN_QA_FAILED,
            sendability.WARN_COVER_LETTER_FAILED,
            sendability.WARN_INTERVIEW_PREP_FAILED,
        }

    @pytest.mark.parametrize(
        "field", ["qa_status", "cover_letter_status", "interview_prep_status"]
    )
    def test_intentional_skip_produces_no_warning(self, field, tmp_path):
        ctx = self._finalize(tmp_path, **{field: pipeline.STAGE_SKIPPED})
        assert ctx["sendability"]["status"] == sendability.READY_TO_SEND
        assert ctx["sendability"]["warnings"] == []

    def test_same_report_file_is_rewritten_not_duplicated(self, tmp_path):
        ctx = self._finalize(tmp_path, qa_status=pipeline.STAGE_FAILED)
        run_dir = Path(ctx["run_dir"])
        assert len(list(run_dir.glob("*sendability*"))) == 1
        assert run_dir.name == ctx["run_id"]

    def test_cover_letter_review_required_becomes_ready_with_warnings(
        self, tmp_path
    ):
        ctx = self._finalize(
            tmp_path, cover_letter_style={"review_required": True}
        )
        result = ctx["sendability"]
        assert result["status"] == sendability.READY_WITH_WARNINGS
        codes = [w["code"] for w in result["warnings"]]
        assert codes == [sendability.WARN_COVER_LETTER_HUMAN_REVIEW_REQUIRED]
        assert result["warnings"][0]["detail"] == (
            "cover letter requires human review before sending"
        )
        # a human-review warning is not a factual blocker
        assert result["blockers"] == []
        # tracker promotion semantics are unchanged by a warning
        assert (
            sendability.promoted_tracker_status(result["status"])
            == sendability.STATUS_READY_TO_APPLY
        )
        report = json.loads(
            (Path(ctx["run_dir"]) / sendability.REPORT_FILENAME).read_text()
        )
        assert report["status"] == sendability.READY_WITH_WARNINGS
        assert [w["code"] for w in report["warnings"]] == codes

    def test_cover_letter_review_not_required_adds_no_warning(self, tmp_path):
        ctx = self._finalize(
            tmp_path, cover_letter_style={"review_required": False}
        )
        assert ctx["sendability"]["status"] == sendability.READY_TO_SEND
        assert ctx["sendability"]["warnings"] == []

    def test_missing_cover_letter_style_adds_no_warning(self, tmp_path):
        ctx = self._finalize(tmp_path)
        assert ctx["sendability"]["status"] == sendability.READY_TO_SEND
        assert ctx["sendability"]["warnings"] == []

    def test_cover_letter_review_warning_coexists_with_stage_warning(self, tmp_path):
        ctx = self._finalize(
            tmp_path,
            qa_status=pipeline.STAGE_FAILED,
            cover_letter_style={"review_required": True},
        )
        result = ctx["sendability"]
        assert result["status"] == sendability.READY_WITH_WARNINGS
        assert [w["code"] for w in result["warnings"]] == sorted(
            [
                sendability.WARN_QA_FAILED,
                sendability.WARN_COVER_LETTER_HUMAN_REVIEW_REQUIRED,
            ]
        )
        assert result["blockers"] == []

    def test_hold_is_preserved_and_tracker_stays_generated(self, tmp_path):
        ctx = self._finalize(tmp_path)
        # Re-run the whole flow with a HOLD-producing outcome (fallback).
        run_dir = _run_dir(tmp_path / "hold")
        tex = run_dir / "Resume.tex"
        tex.write_text((PROJECT_ROOT / "templates" / "resume.tex").read_text())
        pdf = run_dir / "Resume.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        ctx = {
            "run_dir": str(run_dir),
            "run_id": run_dir.name,
            "tex_path": str(tex),
            "pdf_path": str(pdf),
            "master_resume": "plain master",
            "tailoring_mode": "targeted",
            "tailoring_outcome": sendability.TAILORING_OUTCOME_FALLBACK_UNTAILORED,
            "qa_status": pipeline.STAGE_FAILED,
        }
        pipeline.step_evaluate_sendability(ctx, _no_llm(), _console())
        assert ctx["sendability"]["status"] == sendability.HOLD
        pipeline.step_finalize_sendability(ctx, _no_llm(), _console())
        assert ctx["sendability"]["status"] == sendability.HOLD
        assert (
            sendability.promoted_tracker_status(ctx["sendability"]["status"])
            == "generated"
        )

    def test_ready_with_warnings_still_promotes(self):
        assert (
            sendability.promoted_tracker_status(sendability.READY_WITH_WARNINGS)
            == "ready_to_apply"
        )

    def test_finalization_writes_no_applied_and_no_llm(self, tmp_path, monkeypatch):
        ctx = self._finalize(tmp_path, qa_status=pipeline.STAGE_FAILED)
        assert "applied" not in json.dumps(ctx["sendability"])
        report = json.loads(
            (Path(ctx["run_dir"]) / sendability.REPORT_FILENAME).read_text()
        )
        assert "applied" not in json.dumps(report)


class TestQaParseUsability:
    """A.4.1-H"""

    def test_usable_answers_are_ok(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION])
        _run_qa(monkeypatch, ctx, payloads=[QA_PAYLOAD])
        assert ctx["qa_status"] == pipeline.STAGE_OK

    def test_zero_usable_answers_is_failed(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=[QUESTION])
        _run_qa(monkeypatch, ctx, payloads=["Sorry, no answers available."])
        assert ctx["qa_answers"] == []
        assert ctx["qa_status"] == pipeline.STAGE_FAILED

    def test_no_questions_is_skipped(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=())
        _run_qa(monkeypatch, ctx)
        assert ctx["qa_status"] == pipeline.STAGE_SKIPPED

    def test_cover_letter_only_does_not_fail_qa(self, tmp_path, monkeypatch):
        ctx = _qa_ctx(tmp_path, questions=(), cover_letter=True)
        _run_qa(monkeypatch, ctx, payloads=[CL_ONLY_PAYLOAD])
        assert ctx["qa_status"] == pipeline.STAGE_SKIPPED
        assert ctx["qa_status"] != pipeline.STAGE_FAILED

    def test_intentional_qa_absence_creates_no_warning(self, tmp_path):
        verdict = _gate(tmp_path, sendability.TAILORING_OUTCOME_TAILORED)
        assert verdict["warnings"] == []


class TestWritingCallCountInvariants:
    """A.4.1-I: the A.4 savings must not regress, and A.4.1 adds no calls."""

    def _scenario(self, tmp_path, questions, cover_letter, interview=False):
        ctx = _qa_ctx(tmp_path, questions=questions, cover_letter=cover_letter)
        if interview:
            ctx["interview_prep_requested"] = True
        qa = _CountingClient([QA_PAYLOAD])
        iv = _CountingClient(["# prep\n"])
        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.setattr(pipeline, "create_qa_client", lambda *a, **k: qa)
            monkeypatch.setattr(
                pipeline, "create_interview_client", lambda *a, **k: iv
            )
            monkeypatch.setattr(pipeline, "_load_prompt", lambda *a, **k: "p")
            _stub_prompt_loaders(monkeypatch)
            pipeline.step_generate_qa(ctx, _no_llm(), _console())
            pipeline.step_generate_interview_prep(ctx, _no_llm(), _console())
        finally:
            monkeypatch.undo()
        return qa.calls, iv.calls

    @pytest.mark.parametrize(
        "questions,cover_letter,expected_qa,expected_iv",
        [
            ((), False, 0, 0),
            ((QUESTION,), False, 1, 0),
            ((), True, 2, 0),
            ((QUESTION,), True, 1, 0),
            ((QUESTION,), False, 1, 1),
        ],
        ids=["resume_only", "qa_only", "cl_only", "qa_and_cl", "interview_prep"],
    )
    def test_matrix(
        self, questions, cover_letter, expected_qa, expected_iv, tmp_path
    ):
        interview = expected_iv == 1
        qa_calls, iv_calls = self._scenario(
            tmp_path, questions, cover_letter, interview=interview
        )
        assert qa_calls == expected_qa
        assert iv_calls == expected_iv

    def test_finalization_and_validators_make_no_llm_calls(self, tmp_path):
        run_dir = _run_dir(tmp_path)
        tex = run_dir / "Resume.tex"
        tex.write_text((PROJECT_ROOT / "templates" / "resume.tex").read_text())
        pdf = run_dir / "Resume.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        ctx = {
            "run_dir": str(run_dir),
            "run_id": run_dir.name,
            "tex_path": str(tex),
            "pdf_path": str(pdf),
            "master_resume": "plain master",
            "tailoring_mode": "targeted",
            "tailoring_outcome": sendability.TAILORING_OUTCOME_TAILORED,
            "qa_status": pipeline.STAGE_FAILED,
        }
        pipeline.step_evaluate_sendability(ctx, _no_llm(), _console())
        before = json.dumps(ctx["sendability"], sort_keys=True)
        pipeline.step_finalize_sendability(ctx, _no_llm(), _console())
        # Pure predicates: no client involvement, so no additional LLM calls.
        assert pipeline.is_usable_ats_report({"json": {"coverage_score": {}}}) is True
        fb = pipeline._parse_review_feedback("## Part A\n```json\n[]\n```", _console())
        assert fb["structure_recognized"] is True
        assert before != json.dumps(ctx["sendability"], sort_keys=True)
