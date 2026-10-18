"""Gate A.3 invariants: deterministic sendability gate + tracker lifecycle wiring.

Guards three behaviours:

  1. the verdict is computed deterministically from pipeline state, never an LLM;
  2. required-condition failures HOLD, optional-stage failures only WARN;
  3. promotion is forward-only and can never write ``applied`` or downgrade.

Run with: pytest tests/test_sendability_gate.py -v
"""

import inspect
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
from apply import _save_application_json  # noqa: E402
from modules import sendability  # noqa: E402

TEMPLATE = (PROJECT_ROOT / "templates" / "resume.tex").read_text()
PLAIN_MASTER = "a plain master resume without postscript anchors"
JOB_URL = "https://example.com/job/gate-a3"
RUN_ID = "Acme_2026-10-05T194512_ab12cd"
EVALUATED_AT = "2026-10-05T12:00:00+00:00"

LATER_STATES = ["applied", "screening", "interview", "offer", "rejected"]


def _console():
    return Console(file=io.StringIO())


class _ExplodingLLM:
    """Any attribute access proves the sendability path touched the LLM."""

    def __getattr__(self, name):  # pragma: no cover - only runs on failure
        raise AssertionError(f"sendability must not touch the LLM (accessed .{name})")


def _llm_guard():
    """step_* variants that must never consult an LLM get this stand-in."""
    return cast(pipeline.LLMClient, _ExplodingLLM())


def evaluate(**overrides):
    """Evaluate with every required check passing, unless overridden."""
    inputs = {
        "run_id": RUN_ID,
        "final_latex": TEMPLATE,
        "resume_artifact_present": True,
        "resume_artifact_bytes": len(TEMPLATE),
        "pdf_present": True,
        "pdf_bytes": 4096,
        "master_resume": PLAIN_MASTER,
        "canonical_template": TEMPLATE,
        "tailoring_mode": sendability.TAILORING_TARGETED,
        "tailoring_outcome": sendability.TAILORING_OUTCOME_TAILORED,
        "evaluated_at": EVALUATED_AT,
    }
    inputs.update(overrides)
    return sendability.evaluate_sendability(**inputs)


def _make_run_dir(tmp_path, name=RUN_ID):
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True)
    tex = run_dir / "Resume_Rodrigo-Lopes.tex"
    tex.write_text(TEMPLATE)
    pdf = run_dir / "Resume_Rodrigo-Lopes.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake pdf bytes")
    return run_dir, tex, pdf


def _step_ctx(run_dir, tex, pdf, **overrides):
    ctx = {
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "tex_path": str(tex),
        "pdf_path": str(pdf),
        "master_resume": PLAIN_MASTER,
        "tailoring_mode": "targeted",
        "tailoring_outcome": "tailored",
    }
    ctx.update(overrides)
    return ctx


def _tracker_ctx(**overrides):
    ctx = {
        "job": {"company": "Acme", "title": "Test PM"},
        "job_url": JOB_URL,
        "pipeline_score": 72,
        "pipeline_score_label": "GOOD",
        "date": "2026-10-05",
    }
    ctx.update(overrides)
    return ctx


def _existing(status):
    return [
        {
            "company": "Acme",
            "role": "Test PM",
            "url": JOB_URL,
            "score": 10,
            "score_label": "WEAK",
            "date": "2026-01-01",
            "status": status,
            "notes": "manual",
        }
    ]


def _save_ctx(**overrides):
    ctx = {
        "job": {"company": "Acme", "title": "Test PM"},
        "job_url": JOB_URL,
        "company_safe": "Acme",
        "run_dir": "",
        "pipeline_score": 72,
        "pipeline_score_label": "GOOD",
        "pdf_path": "",
    }
    ctx.update(overrides)
    return ctx


def _read_apps(path):
    return json.loads(path.read_text())


# ─── 1. Deterministic verdicts ───────────────────────────────────


class TestDeterministicEvaluation:
    def test_valid_package_is_ready_to_send(self):
        """Required check 1."""
        result = evaluate()
        assert result["status"] == sendability.READY_TO_SEND
        assert result["blockers"] == []
        assert result["warnings"] == []
        assert result["checks"] == {
            "resume_artifact": "PASS",
            "pdf": "PASS",
            "integrity": "PASS",
            "unsupported_novel_claim": "PASS",
            "locked_experience": "PASS",
            "placeholders": "PASS",
            "reviewer": "PASS",
            "ats_semantic": "PASS",
            "application_questions_check": "NOT_YET_WIRED",
        }

    def test_result_is_reproducible_from_same_inputs(self):
        assert evaluate() == evaluate()

    def test_substantive_fields_are_stable_across_timestamps(self):
        """Step 3: evaluated_at may vary; status/blockers/warnings/checks must not."""
        first = evaluate(evaluated_at="2026-10-05T12:00:00+00:00")
        second = evaluate(evaluated_at="2027-01-01T00:00:00+00:00")
        assert first["evaluated_at"] != second["evaluated_at"]
        for key in ("run_id", "status", "blockers", "warnings", "checks"):
            assert first[key] == second[key]

    def test_result_shape(self):
        result = evaluate()
        assert set(result) == {
            "run_id",
            "status",
            "tailoring_mode",
            "tailoring_outcome",
            "evaluated_at",
            "blockers",
            "warnings",
            "checks",
        }
        assert result["run_id"] == RUN_ID
        assert result["evaluated_at"] == EVALUATED_AT
        assert result["tailoring_mode"] == sendability.TAILORING_TARGETED
        assert result["tailoring_outcome"] == sendability.TAILORING_OUTCOME_TAILORED
        assert result["status"] in sendability.SENDBILITY_STATUSES

    def test_readiness_does_not_imply_applied(self):
        """READY_TO_SEND must never be conflated with applied/submitted."""
        result = evaluate()
        assert result["status"] != "applied"
        assert "applied" not in json.dumps(result)


# ─── 2. HOLD conditions ──────────────────────────────────────────


class TestHoldConditions:
    def test_integrity_failure_holds(self):
        """Required check 2."""
        broken = TEMPLATE.replace("Dec 2024 -- Aug 2026", "whenever")
        result = evaluate(final_latex=broken, resume_artifact_bytes=len(broken))
        assert result["status"] == sendability.HOLD
        assert result["checks"]["integrity"] == "FAIL"
        assert any(
            b["code"] == sendability.BLOCK_INTEGRITY_FAILED for b in result["blockers"]
        )

    def test_locked_experience_drift_holds(self):
        """Required check 3."""
        drifted = TEMPLATE.replace(
            "Led product roadmap for FORVIA", "Owned product roadmap for FORVIA"
        )
        result = evaluate(final_latex=drifted, resume_artifact_bytes=len(drifted))
        assert result["status"] == sendability.HOLD
        assert result["checks"]["locked_experience"] == "FAIL"
        assert any(
            b["code"] == sendability.BLOCK_LOCKED_EXPERIENCE_DRIFT
            for b in result["blockers"]
        )

    def test_missing_pdf_holds(self):
        """Required check 4."""
        result = evaluate(pdf_present=False, pdf_bytes=0)
        assert result["status"] == sendability.HOLD
        assert result["checks"]["pdf"] == "FAIL"
        assert any(b["code"] == sendability.BLOCK_PDF_MISSING for b in result["blockers"])

    def test_empty_pdf_holds(self):
        """Required check 5."""
        result = evaluate(pdf_present=True, pdf_bytes=0)
        assert result["status"] == sendability.HOLD
        assert result["checks"]["pdf"] == "FAIL"
        assert any(b["code"] == sendability.BLOCK_PDF_EMPTY for b in result["blockers"])

    def test_unresolved_placeholder_holds(self):
        """Required check 6."""
        with_placeholder = TEMPLATE + "\n% TODO: finish this section\n"
        result = evaluate(
            final_latex=with_placeholder, resume_artifact_bytes=len(with_placeholder)
        )
        assert result["status"] == sendability.HOLD
        assert result["checks"]["placeholders"] == "FAIL"
        assert any(
            b["code"] == sendability.BLOCK_UNRESOLVED_PLACEHOLDER
            for b in result["blockers"]
        )

    def test_missing_resume_artifact_holds(self):
        result = evaluate(resume_artifact_present=False, resume_artifact_bytes=0)
        assert result["status"] == sendability.HOLD
        assert result["checks"]["resume_artifact"] == "FAIL"

    def test_empty_resume_artifact_holds(self):
        result = evaluate(final_latex="", resume_artifact_bytes=0)
        assert result["status"] == sendability.HOLD
        assert result["checks"]["resume_artifact"] == "FAIL"

    def test_missing_master_resume_is_not_a_false_ready(self):
        """Missing deterministic evidence must not yield a clean READY."""
        result = evaluate(master_resume=None)
        assert result["status"] == sendability.HOLD
        assert result["checks"]["integrity"] == "FAIL"
        assert any(
            b["code"] == sendability.BLOCK_INTEGRITY_UNVERIFIABLE
            for b in result["blockers"]
        )

    def test_missing_canonical_template_is_not_a_false_ready(self):
        result = evaluate(canonical_template=None)
        assert result["status"] == sendability.HOLD
        assert result["checks"]["locked_experience"] == "FAIL"

    def test_compile_layout_autofixes_do_not_cause_false_hold(self):
        """compile_and_inspect inserts layout commands; they are not drift."""
        autofixed = TEMPLATE.replace(
            "\\noindent\\textbf{FORVIA HELLA}",
            "\\needspace{5\\baselineskip}\n\\noindent\\textbf{FORVIA HELLA}",
        )
        assert "\\needspace" in autofixed
        result = evaluate(
            final_latex=autofixed, resume_artifact_bytes=len(autofixed)
        )
        assert result["status"] == sendability.READY_TO_SEND

    def test_full_generation_mode_skips_locked_check(self):
        result = evaluate(tailoring_mode=sendability.TAILORING_FULL)
        assert result["status"] == sendability.READY_TO_SEND
        assert result["checks"]["locked_experience"] == "NOT_APPLICABLE"


# ─── 3. READY_WITH_WARNINGS conditions ───────────────────────────


class TestWarningConditions:
    def test_reviewer_failure_alone_is_ready_with_warnings(self):
        """Required check 7."""
        result = evaluate(reviewer_failed=True)
        assert result["status"] == sendability.READY_WITH_WARNINGS
        assert result["blockers"] == []
        assert result["checks"]["reviewer"] == "WARN"
        assert [w["code"] for w in result["warnings"]] == [
            sendability.WARN_REVIEWER_FAILED
        ]

    def test_ats_semantic_failure_alone_is_ready_with_warnings(self):
        """Required check 8."""
        result = evaluate(ats_semantic_unavailable=True)
        assert result["status"] == sendability.READY_WITH_WARNINGS
        assert result["blockers"] == []
        assert result["checks"]["ats_semantic"] == "WARN"

    def test_both_optional_failures_still_ready_with_warnings(self):
        result = evaluate(reviewer_failed=True, ats_semantic_unavailable=True)
        assert result["status"] == sendability.READY_WITH_WARNINGS
        assert len(result["warnings"]) == 2
        assert result["blockers"] == []

    def test_optional_failures_never_produce_hold(self):
        result = evaluate(reviewer_failed=True, ats_semantic_unavailable=True)
        assert result["status"] != sendability.HOLD

    def test_absent_optional_artifacts_do_not_warn(self):
        """Required check 21: no run_dir coverage of Q&A/CL/interview prep exists."""
        result = evaluate()
        assert result["status"] == sendability.READY_TO_SEND
        assert result["warnings"] == []

    def test_application_questions_check_is_not_yet_wired(self):
        result = evaluate()
        assert (
            result["checks"]["application_questions_check"]
            == sendability.NOT_YET_WIRED
        )

    def test_blockers_override_warnings(self):
        result = evaluate(reviewer_failed=True, pdf_present=False, pdf_bytes=0)
        assert result["status"] == sendability.HOLD


# ─── 4. Tracker lifecycle wiring ─────────────────────────────────


class TestTrackerPromotion:
    def test_ready_to_send_new_entry_becomes_ready_to_apply(self, tmp_path, monkeypatch):
        """Required check 9."""
        apps_file = tmp_path / "applications.json"
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)
        ctx = _tracker_ctx(sendability={"status": sendability.READY_TO_SEND})

        pipeline.step_create_tracker_entry(ctx, _llm_guard(), _console())

        assert _read_apps(apps_file)[0]["status"] == "ready_to_apply"

    def test_ready_with_warnings_new_entry_becomes_ready_to_apply(
        self, tmp_path, monkeypatch
    ):
        """Required check 10."""
        apps_file = tmp_path / "applications.json"
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)
        ctx = _tracker_ctx(sendability={"status": sendability.READY_WITH_WARNINGS})

        pipeline.step_create_tracker_entry(ctx, _llm_guard(), _console())

        assert _read_apps(apps_file)[0]["status"] == "ready_to_apply"

    def test_hold_new_entry_stays_generated(self, tmp_path, monkeypatch):
        """Required check 11."""
        apps_file = tmp_path / "applications.json"
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)
        ctx = _tracker_ctx(sendability={"status": sendability.HOLD})

        pipeline.step_create_tracker_entry(ctx, _llm_guard(), _console())

        assert _read_apps(apps_file)[0]["status"] == "generated"

    def test_missing_sendability_does_not_promote(self, tmp_path, monkeypatch):
        apps_file = tmp_path / "applications.json"
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)

        pipeline.step_create_tracker_entry(_tracker_ctx(), _llm_guard(), _console())

        assert _read_apps(apps_file)[0]["status"] == "generated"

    @pytest.mark.parametrize("status", LATER_STATES)
    def test_pipeline_dedup_never_downgrades(self, status, tmp_path, monkeypatch):
        """Required checks 12-16."""
        apps_file = tmp_path / "applications.json"
        apps_file.write_text(json.dumps(_existing(status)))
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)
        ctx = _tracker_ctx(sendability={"status": sendability.READY_TO_SEND})

        pipeline.step_create_tracker_entry(ctx, _llm_guard(), _console())

        entries = _read_apps(apps_file)
        assert len(entries) == 1
        assert entries[0]["status"] == status
        assert entries[0]["notes"] == "manual"

    def test_pipeline_dedup_promotes_generated(self, tmp_path, monkeypatch):
        apps_file = tmp_path / "applications.json"
        apps_file.write_text(json.dumps(_existing("generated")))
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)
        ctx = _tracker_ctx(sendability={"status": sendability.READY_TO_SEND})

        pipeline.step_create_tracker_entry(ctx, _llm_guard(), _console())

        assert _read_apps(apps_file)[0]["status"] == "ready_to_apply"

    def test_pipeline_dedup_hold_leaves_ready_to_apply_intact(
        self, tmp_path, monkeypatch
    ):
        apps_file = tmp_path / "applications.json"
        apps_file.write_text(json.dumps(_existing("ready_to_apply")))
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)
        ctx = _tracker_ctx(sendability={"status": sendability.HOLD})

        pipeline.step_create_tracker_entry(ctx, _llm_guard(), _console())

        assert _read_apps(apps_file)[0]["status"] == "ready_to_apply"

    def test_pipeline_dedup_preserves_unknown_status(self, tmp_path, monkeypatch):
        apps_file = tmp_path / "applications.json"
        apps_file.write_text(json.dumps(_existing("some_manual_state")))
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)
        ctx = _tracker_ctx(sendability={"status": sendability.READY_TO_SEND})

        pipeline.step_create_tracker_entry(ctx, _llm_guard(), _console())

        assert _read_apps(apps_file)[0]["status"] == "some_manual_state"

    def test_apply_save_ready_to_send_becomes_ready_to_apply(self, tmp_path, monkeypatch):
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)
        _save_application_json(
            _save_ctx(sendability={"status": sendability.READY_TO_SEND}), _console()
        )
        apps = _read_apps(tmp_path / "data" / "applications.json")
        assert apps[0]["status"] == "ready_to_apply"

    def test_apply_save_hold_stays_generated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)
        _save_application_json(
            _save_ctx(sendability={"status": sendability.HOLD}), _console()
        )
        apps = _read_apps(tmp_path / "data" / "applications.json")
        assert apps[0]["status"] == "generated"

    @pytest.mark.parametrize("status", LATER_STATES)
    def test_apply_save_never_downgrades(self, status, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "applications.json").write_text(json.dumps(_existing(status)))
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)

        _save_application_json(
            _save_ctx(sendability={"status": sendability.READY_TO_SEND}), _console()
        )

        apps = _read_apps(data_dir / "applications.json")
        assert apps[0]["status"] == status


# ─── 5. No path can write ``applied`` ────────────────────────────


class TestNeverWritesApplied:
    def test_promotion_helper_only_emits_two_states(self):
        """Required check 17."""
        emitted = {
            sendability.promoted_tracker_status(s)
            for s in (*sendability.SENDBILITY_STATUSES, None, "", "garbage")
        }
        assert emitted == {"ready_to_apply", "generated"}
        assert "applied" not in emitted

    def test_resolve_helper_never_produces_applied(self):
        for existing in (None, "generated", "ready_to_apply", *LATER_STATES):
            for candidate in ("generated", "ready_to_apply"):
                resolved = sendability.resolve_tracker_status(existing, candidate)
                if existing != "applied":
                    assert resolved != "applied"

    def test_generation_modules_have_no_hardcoded_applied_status(self):
        for relative in ("modules/pipeline.py", "apply.py", "modules/sendability.py"):
            assert '"status": "applied"' not in (PROJECT_ROOT / relative).read_text()

    def test_end_to_end_run_never_writes_applied(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", tmp_path / "applications.json")
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)

        for status in sendability.SENDBILITY_STATUSES:
            ctx = _tracker_ctx(sendability={"status": status})
            pipeline.step_create_tracker_entry(ctx, _llm_guard(), _console())
            _save_application_json(_save_ctx(sendability={"status": status}), _console())

        statuses = {
            a["status"]
            for a in _read_apps(tmp_path / "data" / "applications.json")
        }
        assert "applied" not in statuses


# ─── 6. Report persistence ───────────────────────────────────────


class TestReportPersistence:
    def test_report_written_in_run_dir_with_canonical_run_id(self, tmp_path, monkeypatch):
        """Required checks 18 and 19."""
        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path, raising=False)
        run_dir, tex, pdf = _make_run_dir(tmp_path)
        ctx = _step_ctx(run_dir, tex, pdf)

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        report_path = run_dir / sendability.REPORT_FILENAME
        assert report_path.is_file()
        report = json.loads(report_path.read_text())
        assert report["run_id"] == ctx["run_id"] == run_dir.name
        assert report["status"] == sendability.READY_TO_SEND
        assert ctx["sendability"]["status"] == sendability.READY_TO_SEND

    def test_hold_report_is_also_persisted(self, tmp_path, monkeypatch):
        run_dir, tex, pdf = _make_run_dir(tmp_path)
        pdf.unlink()  # missing PDF must still produce a report, as HOLD
        ctx = _step_ctx(run_dir, tex, pdf)

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        report = json.loads((run_dir / sendability.REPORT_FILENAME).read_text())
        assert report["status"] == sendability.HOLD
        assert report["checks"]["pdf"] == "FAIL"

    def test_distinct_runs_write_distinct_reports(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path, raising=False)
        reports = []
        for name in ("Acme_2026-10-05T194512_ab12cd", "Acme_2026-10-05T194512_cd34ef"):
            run_dir, tex, pdf = _make_run_dir(tmp_path, name)
            ctx = _step_ctx(run_dir, tex, pdf)
            pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
            reports.append(json.loads((run_dir / sendability.REPORT_FILENAME).read_text()))

        assert reports[0]["run_id"] != reports[1]["run_id"]
        assert len(list(tmp_path.glob(f"*/{sendability.REPORT_FILENAME}"))) == 2

    def test_report_is_small_and_has_no_llm_prose(self, tmp_path, monkeypatch):
        run_dir, tex, pdf = _make_run_dir(tmp_path)
        ctx = _step_ctx(run_dir, tex, pdf)
        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        report = json.loads((run_dir / sendability.REPORT_FILENAME).read_text())
        assert len(json.dumps(report)) < 5000
        # No bleed-through of the resume body or other large LLM output.
        assert TEMPLATE[:120] not in json.dumps(report)

    def test_step_does_not_raise_when_artifacts_are_absent(self, tmp_path, monkeypatch):
        run_dir = tmp_path / RUN_ID
        run_dir.mkdir()
        ctx: dict = {
            "run_dir": str(run_dir),
            "run_id": RUN_ID,
            "tex_path": "",
            "pdf_path": "",
            "master_resume": PLAIN_MASTER,
        }

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        assert ctx["sendability"]["status"] == sendability.HOLD


# ─── 7. No LLM dependence ────────────────────────────────────────


class TestNoLlmDependence:
    def test_evaluator_takes_no_llm_input(self):
        """Required check 20."""
        params = set(inspect.signature(sendability.evaluate_sendability).parameters)
        assert not any("llm" in p or "prompt" in p or "model" in p for p in params)

    def test_pipeline_step_never_touches_the_llm(self, tmp_path, monkeypatch):
        """Required check 20: an exploding LLM proves no call is made."""
        run_dir, tex, pdf = _make_run_dir(tmp_path)
        ctx = _step_ctx(run_dir, tex, pdf)

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        assert ctx["sendability"]["status"] == sendability.READY_TO_SEND

    def test_sendability_module_imports_no_llm_client(self):
        source = (PROJECT_ROOT / "modules" / "sendability.py").read_text()
        assert "llm_client" not in source
        assert "generate(" not in source


# ─── 8. Compile auto-fix / recovery semantics (F1 regression) ────


class TestCompileRecoverySemantics:
    """The PDF check must judge the FINAL state, after any successful auto-fix.

    compile_and_inspect can rewrite the .tex while recovering from PDF layout
    issues (orphan entries, page spills, isolated sections). A recovered run has
    a valid final PDF and must never be judged on the intermediate failing
    attempt, nor report phantom locked-experience drift caused by the recovery.
    """

    FORVIA_BULLET = "Led product roadmap for FORVIA HELLA's B2B e-commerce platform"

    def _apply_real_autofix(self, title_text, tmp_path):
        """Run the pipeline's real _apply_fixes and return the rewritten .tex."""
        from scripts.render_pdf import _apply_fixes

        tex = tmp_path / "Resume_Rodrigo-Lopes.tex"
        tex.write_text(TEMPLATE)
        fixes = _apply_fixes(
            str(tex),
            [
                {
                    "type": "orphaned_entry",
                    "detail": f"Entry title '{title_text}' may be orphaned at page 1 bottom",
                }
            ],
        )
        return tex.read_text(), fixes

    def test_strip_removes_the_whole_inserted_line(self):
        """Unit: the strip must consume the line break, not only the command."""
        assert (
            sendability.strip_compile_layout_commands(
                "X\n\\needspace{5\\baselineskip}\nY"
            )
            == "X\nY"
        )
        assert (
            sendability.strip_compile_layout_commands(
                "X\n\\enlargethispage{2\\baselineskip}\nY"
            )
            == "X\nY"
        )

    def test_initial_compile_success_is_not_hold(self):
        """Required behaviour 1: clean first compile -> PDF check PASSES."""
        result = evaluate()
        assert result["status"] == sendability.READY_TO_SEND
        assert result["checks"]["pdf"] == "PASS"

    def test_recovered_compile_is_not_hold(self, tmp_path):
        """Required behaviour 2 + F1 regression.

        The real auto-fix inserts a layout command INSIDE the locked FORVIA
        block while recovering. The recovered run has a valid final PDF, so it
        must not be held and must not report phantom locked-experience drift.
        """
        recovered, fixes = self._apply_real_autofix(self.FORVIA_BULLET, tmp_path)
        assert fixes, "precondition: the real auto-fix must have inserted something"
        assert "\\needspace" in recovered, "precondition: layout line rewritten in"

        # The inserted command sits inside the locked block, and removing it
        # must restore the canonical block byte-for-byte.
        from modules.parsers import locked_experience_drift

        normalised = sendability.strip_compile_layout_commands(recovered)
        assert locked_experience_drift(TEMPLATE, normalised) == []

        result = evaluate(final_latex=recovered, resume_artifact_bytes=len(recovered))
        assert result["blockers"] == []
        assert result["status"] == sendability.READY_TO_SEND
        assert result["checks"]["locked_experience"] == "PASS"

    def test_autofix_recovery_does_not_weaken_real_drift_detection(self):
        """A genuinely edited locked block must still HOLD after the fix."""
        edited = TEMPLATE.replace(
            "Led product roadmap for FORVIA", "Owned product roadmap for FORVIA"
        )
        result = evaluate(final_latex=edited, resume_artifact_bytes=len(edited))
        assert result["status"] == sendability.HOLD
        assert any(
            b["code"] == sendability.BLOCK_LOCKED_EXPERIENCE_DRIFT
            for b in result["blockers"]
        )

    def test_failed_compile_has_no_final_pdf_and_holds(self, tmp_path, monkeypatch):
        """Required behaviour 3: compile/auto-fix ultimately fails -> HOLD."""
        run_dir = tmp_path / RUN_ID
        run_dir.mkdir()
        tex = run_dir / "Resume_Rodrigo-Lopes.tex"
        tex.write_text(TEMPLATE)

        monkeypatch.setattr(
            pipeline,
            "compile_and_inspect",
            lambda *a, **k: {"ok": False, "error": "pdflatex failed", "details": ["! Emergency stop."]},
        )
        ctx: dict = {"tex_path": str(tex), "run_dir": str(run_dir), "run_id": RUN_ID}
        with pytest.raises(RuntimeError):
            pipeline.step_compile_pdf(ctx, _llm_guard(), _console())

        # ctx carries no pdf_path; the gate must still refuse to pass it.
        ctx["master_resume"] = PLAIN_MASTER
        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        assert ctx["sendability"]["status"] == sendability.HOLD
        assert any(
            b["code"] == sendability.BLOCK_PDF_MISSING
            for b in ctx["sendability"]["blockers"]
        )

    def test_missing_final_pdf_holds(self):
        """Required behaviour 4."""
        result = evaluate(pdf_present=False, pdf_bytes=0)
        assert result["status"] == sendability.HOLD
        assert result["checks"]["pdf"] == "FAIL"

    def test_empty_final_pdf_holds(self):
        """Required behaviour 5."""
        result = evaluate(pdf_present=True, pdf_bytes=0)
        assert result["status"] == sendability.HOLD
        assert result["checks"]["pdf"] == "FAIL"

    def test_recovery_does_not_make_a_bad_resume_ready(self, tmp_path):
        """Recovery must not mask a genuinely broken final artifact."""
        recovered, _ = self._apply_real_autofix(self.FORVIA_BULLET, tmp_path)
        broken = recovered.replace("Dec 2024 -- Aug 2026", "whenever")
        result = evaluate(final_latex=broken, resume_artifact_bytes=len(broken))
        assert result["status"] == sendability.HOLD


# ─── 9. Canonical runtime tailoring mode (F7 regression) ─────────

FULL_GEN_LATEX = "```latex\n" + TEMPLATE + "\n```"
# A full-generation payload that genuinely differs from the base template, so a
# "successful tailoring" fixture is never itself a no-op artifact.
FULL_GEN_LATEX_TAILORED = "```latex\n" + TEMPLATE.replace(
    "Senior Product Manager with 8+ years",
    "Senior Product Manager with 9 years",
) + "\n```"
DRIFTED_FORVIA = TEMPLATE.replace(
    "Led product roadmap for FORVIA", "Drove product roadmap for FORVIA"
)


class _FakeTailorClient:
    """Returns queued payloads so both tailoring paths are deterministic."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []

    def model_name(self):
        return "fake-tailor-model"

    def generate(self, system, user, temperature=0.2, **kwargs):
        self.calls.append((system, user))
        if not self._payloads:
            raise AssertionError("fake tailor client ran out of payloads")
        return self._payloads.pop(0)


def _tailor_ctx(tmp_path):
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": str(run_dir),
        "run_id": RUN_ID,
        "company_safe": "Acme",
        "master_resume": PLAIN_MASTER,
        "job": {
            "title": "Test PM",
            "company": "Acme",
            "url": JOB_URL,
            "description": "A product management role.",
        },
    }


class TestTailoringModeCanonicalState:
    """F7: the gate must use the mode actually used, never configured intent."""

    def _run_tailor(self, tmp_path, monkeypatch, payloads, parse_result):
        client = _FakeTailorClient(payloads)
        monkeypatch.setattr(pipeline, "create_tailor_client", lambda *a, **k: client)
        monkeypatch.setattr(pipeline, "parse_resume_edits", lambda raw: parse_result)
        ctx = _tailor_ctx(tmp_path)
        pipeline.step_tailor_resume(ctx, _llm_guard(), _console())
        return ctx

    def test_targeted_configured_and_succeeds_records_targeted(
        self, tmp_path, monkeypatch
    ):
        """Step 7.1"""
        monkeypatch.setenv("TARGETED_EDITS", "1")
        ctx = self._run_tailor(
            tmp_path,
            monkeypatch,
            payloads=["brief", '{"tagline": "x"}', "PASS"],
            parse_result={"postscript_bullets": []},
        )
        assert ctx["tailoring_mode"] == sendability.TAILORING_TARGETED

    def test_targeted_configured_but_runtime_fallback_records_full(
        self, tmp_path, monkeypatch
    ):
        """Step 7.2 - exactly the F7 scenario: configured targeted, actually full."""
        monkeypatch.setenv("TARGETED_EDITS", "1")
        ctx = self._run_tailor(
            tmp_path,
            monkeypatch,
            # four calls: analysis(3a) -> targeted attempt(3b) -> full fallback(3b) -> review(3c)
            payloads=["brief", "not a JSON patch", FULL_GEN_LATEX, "PASS"],
            parse_result={},  # targeted patch failed to parse -> runtime fallback
        )
        assert ctx["tailoring_mode"] == sendability.TAILORING_FULL

    def test_full_generation_configured_directly_records_full(
        self, tmp_path, monkeypatch
    ):
        """Step 7.3"""
        monkeypatch.setenv("TARGETED_EDITS", "0")
        ctx = self._run_tailor(
            tmp_path,
            monkeypatch,
            payloads=["brief", FULL_GEN_LATEX, "PASS"],
            parse_result={"unused": True},
        )
        assert ctx["tailoring_mode"] == sendability.TAILORING_FULL

    def test_actual_targeted_genuine_drift_still_holds(self):
        """Step 7.4 - protection is NOT weakened in real targeted mode."""
        result = evaluate(
            tailoring_mode=sendability.TAILORING_TARGETED,
            final_latex=DRIFTED_FORVIA,
            resume_artifact_bytes=len(DRIFTED_FORVIA),
        )
        assert result["status"] == sendability.HOLD
        assert result["checks"]["locked_experience"] == "FAIL"
        assert any(
            b["code"] == sendability.BLOCK_LOCKED_EXPERIENCE_DRIFT
            for b in result["blockers"]
        )

    def test_actual_full_mode_locked_comparison_is_not_applicable(self):
        """Step 7.5 - same artifact, full mode: NOT_APPLICABLE, not HOLD."""
        result = evaluate(
            tailoring_mode=sendability.TAILORING_FULL,
            final_latex=DRIFTED_FORVIA,
            resume_artifact_bytes=len(DRIFTED_FORVIA),
        )
        assert result["checks"]["locked_experience"] == "NOT_APPLICABLE"
        assert result["status"] != sendability.HOLD
        assert not any(
            b["code"] == sendability.BLOCK_LOCKED_EXPERIENCE_DRIFT
            for b in result["blockers"]
        )

    def test_f7_regression_fallback_run_is_not_held(self, tmp_path, monkeypatch):
        """Step 7.6 - the F7 regression. Fails behaviourally before the fix.

        Uses literals (not the new constants) so this test can run against the
        unfixed code and demonstrate the real false HOLD.
        """
        monkeypatch.setenv("TARGETED_EDITS", "1")  # configured intent = targeted
        run_dir, tex, pdf = _make_run_dir(tmp_path)
        tex.write_text(DRIFTED_FORVIA)  # what full generation actually produced
        ctx = _step_ctx(run_dir, tex, pdf, tailoring_mode="full")

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        verdict = ctx["sendability"]
        assert verdict["checks"]["locked_experience"] == "NOT_APPLICABLE"
        assert not any(
            b["code"] == sendability.BLOCK_LOCKED_EXPERIENCE_DRIFT
            for b in verdict["blockers"]
        )
        assert verdict["status"] != sendability.HOLD

    def test_evaluator_verdict_is_independent_of_targeted_edits_env(self, monkeypatch):
        """Step 7.7 - no environment intent reaches the verdict."""
        observed = []
        for env_value in ("1", "0"):
            monkeypatch.setenv("TARGETED_EDITS", env_value)
            observed.append(evaluate())
        assert observed[0] == observed[1]
        assert observed[0]["status"] == sendability.READY_TO_SEND

    def test_evaluator_does_not_reference_targeted_edits_env(self):
        """Step 7.7 - source-level guard against reintroducing env inference."""
        source = (PROJECT_ROOT / "modules" / "sendability.py").read_text()
        # No environment access of any kind may influence applicability.
        assert "os.getenv" not in source
        assert "os.environ" not in source

    def test_report_records_actual_tailoring_mode(self, tmp_path, monkeypatch):
        """Step 7.8"""
        run_dir, tex, pdf = _make_run_dir(tmp_path)
        ctx = _step_ctx(run_dir, tex, pdf, tailoring_mode=sendability.TAILORING_FULL)
        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        report = json.loads((run_dir / sendability.REPORT_FILENAME).read_text())
        assert report["tailoring_mode"] == "full"
        assert ctx["sendability"]["tailoring_mode"] == "full"

    def test_full_mode_still_enforces_factual_and_integrity_checks(self):
        """Step 7.9 - full mode skips ONLY the targeted locked-block check."""
        broken = TEMPLATE.replace("Dec 2024 -- Aug 2026", "whenever")
        result = evaluate(
            tailoring_mode=sendability.TAILORING_FULL,
            final_latex=broken,
            resume_artifact_bytes=len(broken),
        )
        assert result["status"] == sendability.HOLD
        assert result["checks"]["integrity"] == "FAIL"

        placeholder = TEMPLATE + "\n% TODO: finish this section\n"
        result2 = evaluate(
            tailoring_mode=sendability.TAILORING_FULL,
            final_latex=placeholder,
            resume_artifact_bytes=len(placeholder),
        )
        assert result2["status"] == sendability.HOLD
        assert result2["checks"]["placeholders"] == "FAIL"

        # Missing/empty PDF is still a blocker in full mode too.
        result3 = evaluate(tailoring_mode=sendability.TAILORING_FULL, pdf_present=False, pdf_bytes=0)
        assert result3["status"] == sendability.HOLD
        assert result3["checks"]["pdf"] == "FAIL"

    def test_unknown_mode_does_not_become_ready(self, tmp_path, monkeypatch):
        """Step 4 - never guess from configuration; fail closed."""
        run_dir, tex, pdf = _make_run_dir(tmp_path)
        ctx = _step_ctx(run_dir, tex, pdf)
        ctx.pop("tailoring_mode")

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        verdict = ctx["sendability"]
        assert verdict["status"] == sendability.HOLD
        assert any(
            b["code"] == sendability.BLOCK_TAILORING_MODE_UNKNOWN
            for b in verdict["blockers"]
        )
        assert verdict["tailoring_mode"] == sendability.TAILORING_UNKNOWN


# ─── 10. Tailoring outcome: untailored fallback (F6 regression) ──

INVALID_DRAFT = TEMPLATE.replace("Dec 2024 -- Aug 2026", "whenever")
INVALID_FULL_GEN = "```latex\n" + INVALID_DRAFT + "\n```"


def _drive_tailor(tmp_path, monkeypatch, payloads, parse_result, apply_edits=None):
    """Run the real step_tailor_resume with a deterministic fake writing client."""
    client = _FakeTailorClient(payloads)
    monkeypatch.setattr(pipeline, "create_tailor_client", lambda *a, **k: client)
    monkeypatch.setattr(pipeline, "parse_resume_edits", lambda raw: parse_result)
    if apply_edits is not None:
        monkeypatch.setattr(pipeline, "apply_resume_edits", apply_edits)
    ctx = _tailor_ctx(tmp_path)
    pipeline.step_tailor_resume(ctx, _llm_guard(), _console())
    return ctx


def _successful_tailor(tmp_path, monkeypatch, mode):
    """A run whose accepted artifact genuinely differs from its own baseline."""
    if mode == "targeted":
        monkeypatch.setenv("TARGETED_EDITS", "1")
        return _drive_tailor(
            tmp_path, monkeypatch,
            payloads=["brief", '{"tagline": "x"}', "PASS"],
            # Must be a genuinely effective edit. An empty bullet list leaves the
            # artifact identical to the baseline, which is correctly reported as
            # no_effective_edits rather than tailored.
            parse_result={
                "postscript_bullets": [],
                "summary_bullet": GENERAL_SUMMARY,
            },
        )
    monkeypatch.setenv("TARGETED_EDITS", "0")
    return _drive_tailor(
        tmp_path, monkeypatch,
        payloads=["brief", FULL_GEN_LATEX_TAILORED, "PASS"],
        parse_result={},
    )


def _rejected_tailor(tmp_path, monkeypatch, mode):
    """Tailoring produces a draft the integrity validator rejects."""
    if mode == "targeted":
        monkeypatch.setenv("TARGETED_EDITS", "1")
        return _drive_tailor(
            tmp_path, monkeypatch,
            payloads=["brief", '{"tagline": "x"}', "PASS"],
            parse_result={"postscript_bullets": []},
            apply_edits=lambda base, edits, master: INVALID_DRAFT,
        )
    monkeypatch.setenv("TARGETED_EDITS", "0")
    return _drive_tailor(
        tmp_path, monkeypatch,
        payloads=["brief", INVALID_FULL_GEN, "PASS"],
        parse_result={},
    )


def _wire_artifacts(ctx):
    """Give the ctx a valid-looking .tex + PDF so only the outcome can HOLD it."""
    run_dir = Path(ctx["run_dir"])
    tex = run_dir / "Resume_Rodrigo-Lopes.tex"
    tex.write_text(ctx["tailored_latex"])
    pdf = run_dir / "Resume_Rodrigo-Lopes.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake pdf bytes")
    ctx["tex_path"] = str(tex)
    ctx["pdf_path"] = str(pdf)
    return ctx


class TestTailoringOutcomeFallback:
    """F6: a tailoring failure that substitutes the base template must HOLD."""

    @pytest.mark.parametrize("mode", ["targeted", "full"])
    def test_successful_tailoring_records_tailored(self, tmp_path, monkeypatch, mode):
        """Step 7.1 / 7.2"""
        ctx = _successful_tailor(tmp_path, monkeypatch, mode)
        assert ctx["tailoring_outcome"] == sendability.TAILORING_OUTCOME_TAILORED

    @pytest.mark.parametrize("mode", ["targeted", "full"])
    def test_rejected_draft_substitutes_the_base_template(self, tmp_path, monkeypatch, mode):
        """Precondition for the regression: the substitution really happens."""
        ctx = _rejected_tailor(tmp_path, monkeypatch, mode)
        assert ctx["tailored_latex"] == TEMPLATE

    @pytest.mark.parametrize("mode", ["targeted", "full"])
    def test_rejected_draft_records_fallback_untailored(self, tmp_path, monkeypatch, mode):
        """Step 7.3 / 7.4 - outcome is recorded at the source, not inferred."""
        ctx = _rejected_tailor(tmp_path, monkeypatch, mode)
        assert (
            ctx["tailoring_outcome"]
            == sendability.TAILORING_OUTCOME_FALLBACK_UNTAILORED
        )
        # tailoring_mode still describes the strategy that ran - not overloaded.
        expected_mode = (
            sendability.TAILORING_TARGETED
            if mode == "targeted"
            else sendability.TAILORING_FULL
        )
        assert ctx["tailoring_mode"] == expected_mode

    def test_f6_regression_untailored_fallback_is_held(self, tmp_path, monkeypatch):
        """Step 7.5 / 7.6 - the F6 regression. Fails behaviourally before the fix.

        Literals are used for the outcome so this test runs against the unfixed
        code and demonstrates the false READY.
        """
        ctx = _wire_artifacts(_rejected_tailor(tmp_path, monkeypatch, "targeted"))

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        verdict = ctx["sendability"]
        assert verdict["status"] == sendability.HOLD, (
            "an untailored fallback package must not be certifiable as ready, "
            f"got {verdict['status']} {[b['code'] for b in verdict['blockers']]}"
        )
        assert any(
            b["code"] == "TAILORING_FALLBACK_UNTAILORED" for b in verdict["blockers"]
        )
        assert verdict["tailoring_outcome"] == "fallback_untailored"

    def test_fallback_keeps_new_record_generated(self, tmp_path, monkeypatch):
        """Step 7.7 - HOLD must not promote, and must never write applied."""
        ctx = _wire_artifacts(_rejected_tailor(tmp_path, monkeypatch, "targeted"))
        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        assert ctx["sendability"]["status"] == sendability.HOLD

        apps = tmp_path / "applications.json"
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps)
        tracker_ctx = _tracker_ctx(title="Acme", sendability=ctx["sendability"])
        pipeline.step_create_tracker_entry(tracker_ctx, _llm_guard(), _console())

        entry = _read_apps(apps)[0]
        assert entry["status"] == "generated"
        assert entry["status"] != "applied"

    def test_successful_tailored_run_still_reaches_ready(self, tmp_path, monkeypatch):
        """Step 7.8 - no over-blocking of legitimate runs."""
        ctx = _wire_artifacts(_successful_tailor(tmp_path, monkeypatch, "targeted"))
        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        verdict = ctx["sendability"]
        assert verdict["status"] == sendability.READY_TO_SEND
        assert verdict["tailoring_outcome"] == sendability.TAILORING_OUTCOME_TAILORED

    def test_unknown_outcome_does_not_become_ready(self, tmp_path, monkeypatch):
        """Step 4 - fail closed when the outcome was never recorded."""
        run_dir, tex, pdf = _make_run_dir(tmp_path)
        ctx = _step_ctx(run_dir, tex, pdf)
        ctx.pop("tailoring_outcome")

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        verdict = ctx["sendability"]
        assert verdict["status"] == sendability.HOLD
        assert any(
            b["code"] == sendability.BLOCK_TAILORING_OUTCOME_UNKNOWN
            for b in verdict["blockers"]
        )
        assert verdict["tailoring_outcome"] == sendability.TAILORING_OUTCOME_UNKNOWN

    def test_evaluator_takes_outcome_and_uses_no_env(self):
        """Step 7.12 / 7.14 - explicit parameter, no config inference, no LLM."""
        params = set(inspect.signature(sendability.evaluate_sendability).parameters)
        assert "tailoring_outcome" in params
        assert not any("llm" in p or "prompt" in p for p in params)
        source = (PROJECT_ROOT / "modules" / "sendability.py").read_text()
        assert "os.getenv" not in source
        assert "os.environ" not in source


# ─── 11. No effective edits (A.3.4) ─────────────────────────────

GENERAL_SUMMARY = (
    "Senior Product Manager with 8+ years across growth, B2C e-commerce, "
    "B2B platforms, and AI-powered products, focused on measurable revenue impact."
)

# A genuinely different summary that also changes a NUMBER, proving numeric
# content is not normalized away by the tailoring-effect comparison. The number is
# one the canonical evidence supports ("18,000+ merchants"), because inventing an
# unsupported figure is a factual defect the sendability gate must block - it is
# not a valid example of a legitimate edit.
GENERAL_SUMMARY_METRIC_VARIANT = GENERAL_SUMMARY.replace(
    "focused on measurable revenue impact.",
    "focused on analytics instrumentation across 18,000+ merchants.",
)

# Payloads that parse and apply successfully yet leave the accepted artifact
# identical to the run baseline. Each must carry a recognised key
# (postscript_bullets or summary_bullet): parse_resume_edits rejects any other
# payload, which sends the pipeline down the full-generation path instead.
NOOP_PAYLOADS = {
    "empty_bullets": {"postscript_bullets": []},
    "all_edits_rejected": {
        "postscript_bullets": [],
        "skills": [{"category": "Nope", "content": "Quantum"}],
    },
    "claim_rejected": {
        "postscript_bullets": [],
        "summary_bullet": "Built RAG systems at scale.",
    },
}


def _run_targeted(tmp_path, monkeypatch, patch, apply_edits=None):
    """Drive the REAL targeted tailoring path with a given JSON patch payload."""
    monkeypatch.setenv("TARGETED_EDITS", "1")
    payload = json.dumps(patch)
    client = _FakeTailorClient(["brief", "```json\n" + payload + "\n```", "PASS"])
    monkeypatch.setattr(pipeline, "create_tailor_client", lambda *a, **k: client)
    if apply_edits is not None:
        monkeypatch.setattr(pipeline, "apply_resume_edits", apply_edits)
    ctx = _tailor_ctx(tmp_path)
    pipeline.step_tailor_resume(ctx, _llm_guard(), _console())
    return _wire_artifacts(ctx)


class TestNoEffectiveEdits:
    """A technically successful patch that changes nothing is not tailoring."""

    @pytest.mark.parametrize("name", sorted(NOOP_PAYLOADS))
    def test_noop_patch_records_no_effective_edits(self, name, tmp_path, monkeypatch):
        """Step 8.2 / 8.3 / 8.4 - empty, equal-value and all-rejected patches."""
        ctx = _run_targeted(tmp_path, monkeypatch, NOOP_PAYLOADS[name])
        assert ctx["tailoring_mode"] == sendability.TAILORING_TARGETED
        assert (
            ctx["tailoring_outcome"]
            == sendability.TAILORING_OUTCOME_NO_EFFECTIVE_EDITS
        )

    def test_config_tagline_identical_and_empty_bullets(self, tmp_path, monkeypatch):
        """Step 8.5 - reproduces the confirmed P1 shape explicitly."""
        from config import ROLE_VARIANT

        tagline = pipeline.TAGLINES.get(
            ROLE_VARIANT, pipeline.TAGLINES["growth_pm"]
        )
        ctx = _run_targeted(
            tmp_path,
            monkeypatch,
            {"postscript_bullets": [], "tagline": tagline},
        )
        assert (
            ctx["tailoring_outcome"]
            == sendability.TAILORING_OUTCOME_NO_EFFECTIVE_EDITS
        )

    def test_no_effective_edits_regression_is_held(self, tmp_path, monkeypatch):
        """Step 8.6 / 8.7 - the A.3.4 regression. Fails behaviourally before the fix.

        Literals are used so this test runs against the unfixed code and shows the
        false READY that would promote a no-op package.
        """
        ctx = _run_targeted(tmp_path, monkeypatch, NOOP_PAYLOADS["empty_bullets"])

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        verdict = ctx["sendability"]
        assert verdict["status"] == sendability.HOLD, (
            "a no-op tailored package must not be certifiable as ready, got "
            f"{verdict['status']} {[b['code'] for b in verdict['blockers']]}"
        )
        assert any(
            b["code"] == "TAILORING_NO_EFFECTIVE_EDITS"
            for b in verdict["blockers"]
        )
        assert verdict["tailoring_outcome"] == "no_effective_edits"

    def test_no_effective_edits_keeps_new_record_generated(self, tmp_path, monkeypatch):
        """Step 8.8 - HOLD must not promote and must never write applied."""
        ctx = _run_targeted(tmp_path, monkeypatch, NOOP_PAYLOADS["empty_bullets"])
        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        assert ctx["sendability"]["status"] == sendability.HOLD

        apps = tmp_path / "applications.json"
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps)
        pipeline.step_create_tracker_entry(
            _tracker_ctx(sendability=ctx["sendability"]), _llm_guard(), _console()
        )

        entry = _read_apps(apps)[0]
        assert entry["status"] == "generated"
        assert entry["status"] != "applied"

    def test_genuine_targeted_edit_is_tailored_and_ready(self, tmp_path, monkeypatch):
        """Step 8.1 / 8.9 - a real change is still tailored and still READY."""
        ctx = _run_targeted(
            tmp_path,
            monkeypatch,
            {"postscript_bullets": [], "summary_bullet": GENERAL_SUMMARY},
        )
        assert (
            ctx["tailoring_outcome"] == sendability.TAILORING_OUTCOME_TAILORED
        )

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        assert ctx["sendability"]["status"] == sendability.READY_TO_SEND

    def test_decision_is_artifact_based_not_payload_based(self, tmp_path, monkeypatch):
        """Step 8.15 - the same no-op payload becomes tailored once it changes bytes."""
        def _changes_artifact(base, edits, master):
            return base.replace(
                "Senior Product Manager with 8+ years",
                "Senior Product Manager with 9 years",
            )

        ctx = _run_targeted(
            tmp_path,
            monkeypatch,
            NOOP_PAYLOADS["empty_bullets"],
            apply_edits=_changes_artifact,
        )
        assert ctx["tailoring_outcome"] == sendability.TAILORING_OUTCOME_TAILORED

    def test_report_distinguishes_mode_and_outcome(self, tmp_path, monkeypatch):
        """Step 8.16"""
        ctx = _run_targeted(tmp_path, monkeypatch, NOOP_PAYLOADS["empty_bullets"])
        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())

        report = json.loads(
            (Path(ctx["run_dir"]) / sendability.REPORT_FILENAME).read_text()
        )
        assert report["tailoring_mode"] == "targeted"
        assert report["tailoring_outcome"] == "no_effective_edits"
        assert report["status"] == "HOLD"
        assert report["blockers"][0]["code"] == "TAILORING_NO_EFFECTIVE_EDITS"

    def test_noop_blocker_is_distinct_from_fallback_blocker(self):
        """Step 8.10 - the two outcomes must not be conflated."""
        assert (
            sendability.BLOCK_TAILORING_NO_EFFECTIVE_EDITS
            != sendability.BLOCK_TAILORING_FALLBACK_UNTAILORED
        )
        assert (
            sendability.TAILORING_OUTCOME_NO_EFFECTIVE_EDITS
            != sendability.TAILORING_OUTCOME_FALLBACK_UNTAILORED
        )
        noop = evaluate(
            tailoring_outcome=sendability.TAILORING_OUTCOME_NO_EFFECTIVE_EDITS
        )
        fallback = evaluate(
            tailoring_outcome=sendability.TAILORING_OUTCOME_FALLBACK_UNTAILORED
        )
        assert [b["code"] for b in noop["blockers"]] == [
            "TAILORING_NO_EFFECTIVE_EDITS"
        ]
        assert [b["code"] for b in fallback["blockers"]] == [
            "TAILORING_FALLBACK_UNTAILORED"
        ]


# ─── 12. Narrow normalization for effective tailoring (A.3.5) ───

_POSTSCRIPT_MATCH = re.search(
    r"\\noindent\\textbf\{Postscript\}.*?\\begin\{itemize\}[^\n]*\n(.*?)\\end\{itemize\}",
    TEMPLATE,
    re.S,
)
assert _POSTSCRIPT_MATCH is not None, "Postscript block not found in the template"
_POSTSCRIPT_BLOCK = _POSTSCRIPT_MATCH.group(1)

# The template's own Postscript bullets, presented the way a model echoing plain
# text would emit them (escaped characters unescaped) so that apply_resume_edits'
# own escaping round-trips to identity.
POSTSCRIPT_VERBATIM_BULLETS = [
    line[len("\\item "):].replace("\\%", "%")
    for line in _POSTSCRIPT_BLOCK.split("\n")
    if line.startswith("\\item ")
]


def _norm(latex):
    return sendability.normalize_for_tailoring_effect_comparison(latex)


class TestTailoringEffectNormalization:
    """Step 4 - the comparison ignores serialization churn, nothing else."""

    def test_exact_equality(self):
        assert _norm(TEMPLATE) == _norm(TEMPLATE)

    def test_line_endings_only(self):
        assert _norm("a\nb") == _norm("a\r\nb") == _norm("a\rb")

    def test_trailing_whitespace_only(self):
        assert _norm("a   \nb\t\n") == _norm("a\nb")

    def test_one_vs_multiple_blank_lines(self):
        assert _norm("a\n\nb") == _norm("a\nb")
        assert _norm("a\n\n\n\nb") == _norm("a\nb")

    def test_whitespace_only_lines(self):
        assert _norm("a\n   \nb") == _norm("a\nb")
        assert _norm("a\n\t \nb") == _norm("a\nb")

    def test_internal_spacing_is_not_stripped(self):
        """Must NOT be a remove-all-whitespace comparison."""
        assert _norm("a  b") != _norm("a b")
        assert _norm("\\item x") != _norm("\\item  x")
        assert _norm("Experiments that accelerate revenue.") != _norm(
            "Experimentsthatacceleraterevenue."
        )

    def test_wording_change_is_detected(self):
        assert _norm("led growth work") != _norm("led growth projects")

    def test_metric_change_is_detected(self):
        assert _norm("8+ years delivering impact") != _norm(
            "9 years delivering impact"
        )

    def test_reordering_is_detected(self):
        assert _norm("a\nb") != _norm("b\na")

    def test_latex_command_change_is_detected(self):
        assert _norm("\\textbf{Product:}") != _norm("\\textit{Product:}")

    def test_deleted_nonblank_line_is_detected(self):
        assert _norm("a\nb") != _norm("a")


class TestNoEffectiveEditsNormalization:
    """A.3.5 - the confirmed formatting-only no-op P1 and its neighbours."""

    def test_verbatim_postscript_echo_is_no_effective_edits(
        self, tmp_path, monkeypatch
    ):
        """Step 4.6 - the confirmed P1. Fails before the A.3.5 fix."""
        assert len(POSTSCRIPT_VERBATIM_BULLETS) == 3, "template shape changed"
        ctx = _run_targeted(
            tmp_path,
            monkeypatch,
            {"postscript_bullets": POSTSCRIPT_VERBATIM_BULLETS},
        )
        assert (
            ctx["tailoring_outcome"]
            == sendability.TAILORING_OUTCOME_NO_EFFECTIVE_EDITS
        )

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        verdict = ctx["sendability"]
        assert verdict["status"] == sendability.HOLD
        assert [b["code"] for b in verdict["blockers"]] == [
            "TAILORING_NO_EFFECTIVE_EDITS"
        ]

    @pytest.mark.parametrize(
        "summary",
        [
            GENERAL_SUMMARY,
            GENERAL_SUMMARY_METRIC_VARIANT,
        ],
        ids=["changed_wording", "changed_metric"],
    )
    def test_real_content_changes_remain_tailored(
        self, summary, tmp_path, monkeypatch
    ):
        """Step 4.7 / 4.8 - genuine changes must not be normalized away."""
        ctx = _run_targeted(
            tmp_path,
            monkeypatch,
            {"postscript_bullets": [], "summary_bullet": summary},
        )
        assert ctx["tailoring_outcome"] == sendability.TAILORING_OUTCOME_TAILORED

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        assert ctx["sendability"]["status"] == sendability.READY_TO_SEND

    def test_reordered_bullets_remain_tailored(self, tmp_path, monkeypatch):
        """Step 4.9 - ordering is tailoring-relevant."""
        ctx = _run_targeted(
            tmp_path,
            monkeypatch,
            {"postscript_bullets": list(reversed(POSTSCRIPT_VERBATIM_BULLETS))},
        )
        assert ctx["tailoring_outcome"] == sendability.TAILORING_OUTCOME_TAILORED

    def test_no_effective_edits_holds_and_stays_generated(
        self, tmp_path, monkeypatch
    ):
        """Step 4.12"""
        ctx = _run_targeted(
            tmp_path, monkeypatch, NOOP_PAYLOADS["empty_bullets"]
        )
        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        assert ctx["sendability"]["status"] == sendability.HOLD

        apps = tmp_path / "applications.json"
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps)
        pipeline.step_create_tracker_entry(
            _tracker_ctx(sendability=ctx["sendability"]), _llm_guard(), _console()
        )
        assert _read_apps(apps)[0]["status"] == "generated"

    def test_later_genuine_edit_revives_tailored(self, tmp_path, monkeypatch):
        """Step 6 - a real post-3b edit must not be held by a stale outcome."""
        ctx = _run_targeted(
            tmp_path, monkeypatch, NOOP_PAYLOADS["empty_bullets"]
        )
        assert (
            ctx["tailoring_outcome"]
            == sendability.TAILORING_OUTCOME_NO_EFFECTIVE_EDITS
        )

        ctx["review_feedback"] = {
            "part_a": [
                {
                    "old_string": (
                        "Senior Product Manager with 8+ years delivering "
                        "measurable impact"
                    ),
                    "new_string": (
                        "Senior Product Manager with 8+ years delivering "
                        "measurable commercial impact"
                    ),
                    "reason": "A.3.5 stale-state test",
                }
            ],
            "part_b": [],
        }
        pipeline.step_apply_review(ctx, _llm_guard(), _console())
        Path(ctx["tex_path"]).write_text(ctx["tailored_latex"])

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        verdict = ctx["sendability"]
        assert (
            verdict["tailoring_outcome"]
            == sendability.TAILORING_OUTCOME_TAILORED
        )
        assert not any(
            b["code"] == "TAILORING_NO_EFFECTIVE_EDITS"
            for b in verdict["blockers"]
        )
        assert verdict["status"] != sendability.HOLD

    def test_explicit_fallback_is_not_revived(self, tmp_path, monkeypatch):
        """Step 7 - fallback_untailored must never be overridden."""
        ctx = _wire_artifacts(_rejected_tailor(tmp_path, monkeypatch, "targeted"))
        assert (
            ctx["tailoring_outcome"]
            == sendability.TAILORING_OUTCOME_FALLBACK_UNTAILORED
        )
        # a later stage genuinely changes the substituted artifact
        ctx["tailored_latex"] = ctx["tailored_latex"].replace(
            "Senior Product Manager with 8+ years",
            "Senior Product Manager with 9 years",
        )
        Path(ctx["tex_path"]).write_text(ctx["tailored_latex"])

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        verdict = ctx["sendability"]
        assert (
            verdict["tailoring_outcome"]
            == sendability.TAILORING_OUTCOME_FALLBACK_UNTAILORED
        )
        assert verdict["status"] == sendability.HOLD

    def test_missing_reference_keeps_no_effective_edits(self, tmp_path, monkeypatch):
        """Fail closed when the run baseline reference is unavailable."""
        ctx = _run_targeted(
            tmp_path, monkeypatch, NOOP_PAYLOADS["empty_bullets"]
        )
        ctx.pop("tailoring_noop_reference")

        pipeline.step_evaluate_sendability(ctx, _llm_guard(), _console())
        assert ctx["sendability"]["status"] == sendability.HOLD
        assert any(
            b["code"] == "TAILORING_NO_EFFECTIVE_EDITS"
            for b in ctx["sendability"]["blockers"]
        )
