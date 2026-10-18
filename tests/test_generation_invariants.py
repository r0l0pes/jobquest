"""Gate A.2 invariants: unique run directories and an honest status lifecycle.

Guards exactly two behaviours:

  1. every package generation run gets its own artifact directory;
  2. generating a package never marks the application as ``applied``.

Run with: pytest tests/test_generation_invariants.py -v
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
from apply import _save_application_json  # noqa: E402

TRACKER_HTML = PROJECT_ROOT / "data" / "tracker.html"
JOB_QUEUE_HTML = PROJECT_ROOT / "data" / "job_queue.html"
SERVE_TRACKER = PROJECT_ROOT / "serve_tracker.py"

SAME_JOB_URL = "https://example.com/job/1"


def _console():
    """Console that captures instead of writing to the terminal."""
    return Console(file=io.StringIO())


def _no_llm():
    """step_create_tracker_entry never touches its llm argument."""
    return cast(pipeline.LLMClient, None)


def _tracker_ctx(**overrides):
    """Minimal ctx for pipeline.step_create_tracker_entry."""
    ctx = {
        "job": {"company": "TestCo", "title": "Test PM"},
        "job_url": SAME_JOB_URL,
        "pipeline_score": 72,
        "pipeline_score_label": "GOOD",
        "date": "2026-10-05",
    }
    ctx.update(overrides)
    return ctx


def _save_ctx(run_dir: str = ""):
    """Minimal ctx for apply._save_application_json."""
    return {
        "job": {"company": "TestCo", "title": "Test PM"},
        "job_url": SAME_JOB_URL,
        "company_safe": "TestCo",
        "run_dir": run_dir,
        "pipeline_score": 72,
        "pipeline_score_label": "GOOD",
        "pdf_path": "",
    }


def _existing_entry(status: str):
    return [
        {
            "company": "TestCo",
            "role": "Test PM",
            "url": SAME_JOB_URL,
            "score": 10,
            "score_label": "WEAK",
            "date": "2026-01-01",
            "status": status,
            "notes": "set by hand",
        }
    ]


# ─── 1. Unique run directories ───────────────────────────────────


class TestUniqueRunDirectories:
    def test_run_id_shape(self):
        assert (
            pipeline.make_run_id("Acme_PM", stamp="2026-10-05T194512", suffix="ab12cd")
            == "Acme_PM_2026-10-05T194512_ab12cd"
        )

    def test_two_runs_same_company_same_second_do_not_collide(
        self, tmp_path, monkeypatch
    ):
        """Requirement 1: same company, same day, same second -> different dirs."""
        # Freeze the timestamp so entropy is the only remaining differentiator.
        monkeypatch.setattr(pipeline.time, "strftime", lambda fmt: "2026-10-05T194512")
        first = pipeline.create_run_dir("Acme", base_dir=tmp_path)
        second = pipeline.create_run_dir("Acme", base_dir=tmp_path)
        assert first != second
        assert first.exists() and second.exists()
        assert first.name.startswith("Acme_2026-10-05T194512_")
        assert second.name.startswith("Acme_2026-10-05T194512_")

    def test_repeat_run_same_day_gets_a_new_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
        first, second = {}, {}
        pipeline.ensure_run_dir(first, "Acme")
        pipeline.ensure_run_dir(second, "Acme")
        assert first["run_dir"] != second["run_dir"]
        assert first["run_id"] != second["run_id"]
        assert Path(first["run_dir"]).exists()
        assert Path(second["run_dir"]).exists()

    def test_existing_directory_is_never_reused_or_overwritten(
        self, tmp_path, monkeypatch
    ):
        taken = tmp_path / "Acme_2026-10-05T194512_taken1"
        taken.mkdir()
        (taken / "resume.tex").write_text("DO NOT TOUCH")

        candidates = iter(
            ["Acme_2026-10-05T194512_taken1", "Acme_2026-10-05T194512_free22"]
        )
        monkeypatch.setattr(pipeline, "make_run_id", lambda *a, **k: next(candidates))

        got = pipeline.create_run_dir("Acme", base_dir=tmp_path)
        assert got.name == "Acme_2026-10-05T194512_free22"
        # The pre-existing run is untouched, not merged into.
        assert (taken / "resume.tex").read_text() == "DO NOT TOUCH"
        assert got.exists() and got != taken

    def test_raises_rather_than_silently_reusing(self, tmp_path, monkeypatch):
        (tmp_path / "Acme_same").mkdir()
        monkeypatch.setattr(pipeline, "make_run_id", lambda *a, **k: "Acme_same")
        with pytest.raises(RuntimeError):
            pipeline.create_run_dir("Acme", base_dir=tmp_path, attempts=3)

    def test_run_id_already_in_ctx_is_reused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
        ctx = {}
        first = pipeline.ensure_run_dir(ctx, "Acme")
        again = pipeline.ensure_run_dir(dict(ctx), "Acme")
        assert first == again
        assert ctx["run_id"] == first.name
        assert [p for p in tmp_path.iterdir() if p.is_dir()] == [first]

    def test_company_prefix_is_preserved_and_filesystem_safe(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
        ctx = {}
        safe = pipeline._safe_filename("Acme Corp / EU")
        run_dir = pipeline.ensure_run_dir(ctx, safe)
        # The human-readable company prefix is preserved verbatim, and the whole
        # directory name stays filesystem-safe.
        assert run_dir.name.startswith(safe + "_")
        assert "/" not in run_dir.name
        assert run_dir == tmp_path / run_dir.name


# ─── 2. Generation never marks a package as applied ──────────────


class TestGenerationNeverMarksApplied:
    def test_pipeline_entry_defaults_to_generated(self, tmp_path, monkeypatch):
        apps_file = tmp_path / "applications.json"
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)

        pipeline.step_create_tracker_entry(_tracker_ctx(), _no_llm(), _console())

        entries = json.loads(apps_file.read_text())
        assert len(entries) == 1
        assert entries[0]["status"] == "generated"
        assert entries[0]["status"] != "applied"

    def test_save_application_json_defaults_to_generated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)

        _save_application_json(_save_ctx(), _console())

        apps = json.loads((tmp_path / "data" / "applications.json").read_text())
        assert apps[0]["status"] == "generated"
        assert apps[0]["status"] != "applied"

    def test_no_generation_path_writes_applied(self, tmp_path, monkeypatch):
        """Requirement 5: both automatic write paths stay off ``applied``."""
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", tmp_path / "applications.json")
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)

        pipeline.step_create_tracker_entry(_tracker_ctx(), _no_llm(), _console())
        _save_application_json(_save_ctx(), _console())

        statuses = [
            a["status"]
            for a in json.loads((tmp_path / "data" / "applications.json").read_text())
        ]
        assert statuses == ["generated"]
        assert "applied" not in statuses

    def test_generation_modules_have_no_hardcoded_applied_status(self):
        for relative in ("modules/pipeline.py", "apply.py"):
            assert '"status": "applied"' not in (PROJECT_ROOT / relative).read_text()

    def test_status_constants_are_distinct(self):
        assert pipeline.STATUS_GENERATED == "generated"
        assert pipeline.STATUS_APPLIED == "applied"
        assert pipeline.STATUS_GENERATED != pipeline.STATUS_APPLIED


# ─── 3. Historical / manual statuses are preserved ───────────────


class TestHistoricalStatusIsPreserved:
    @pytest.mark.parametrize("status", ["applied", "screening", "interview", "offer"])
    def test_pipeline_dedup_preserves_existing_status(
        self, status, tmp_path, monkeypatch
    ):
        apps_file = tmp_path / "applications.json"
        apps_file.write_text(json.dumps(_existing_entry(status)))
        monkeypatch.setattr(pipeline, "APPLICATIONS_FILE", apps_file)

        pipeline.step_create_tracker_entry(
            _tracker_ctx(pipeline_score=90), _no_llm(), _console()
        )

        entries = json.loads(apps_file.read_text())
        assert len(entries) == 1
        assert entries[0]["status"] == status  # Requirement 4: not rewritten
        assert entries[0]["notes"] == "set by hand"
        assert entries[0]["score"] == 90  # generation metadata still refreshed

    @pytest.mark.parametrize("status", ["applied", "interview"])
    def test_save_application_json_preserves_existing_status(
        self, status, tmp_path, monkeypatch
    ):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "applications.json").write_text(json.dumps(_existing_entry(status)))
        monkeypatch.setattr("apply.PROJECT_ROOT", tmp_path)

        _save_application_json(_save_ctx(), _console())

        apps = json.loads((data_dir / "applications.json").read_text())
        assert len(apps) == 1
        assert apps[0]["status"] == status
        assert apps[0]["status"] != "generated"


# ─── 4. Tracker lifecycle / UI wiring ────────────────────────────


class TestTrackerLifecycle:
    def test_lifecycle_order(self):
        assert pipeline.APPLICATION_STATUSES == (
            "generated",
            "ready_to_apply",
            "applied",
            "screening",
            "interview",
            "offer",
            "rejected",
        )

    def test_ready_to_apply_is_a_valid_status(self):
        """Requirement 3."""
        assert pipeline.STATUS_READY_TO_APPLY == "ready_to_apply"
        assert pipeline.STATUS_READY_TO_APPLY in pipeline.APPLICATION_STATUSES

    def test_legacy_statuses_remain_valid(self):
        for legacy in ("screening", "interview", "offer", "rejected"):
            assert legacy in pipeline.APPLICATION_STATUSES

    def test_applied_remains_a_valid_status(self):
        assert "applied" in pipeline.APPLICATION_STATUSES

    def test_tracker_ui_offers_new_and_legacy_statuses(self):
        html = TRACKER_HTML.read_text()
        assert '<option value="ready_to_apply">' in html
        assert '<option value="generated">' in html

        match = re.search(r"const STATUS_OPTIONS = \[(.*?)\];", html, re.S)
        assert match, "STATUS_OPTIONS block not found in tracker.html"
        statuses = re.findall(r'"([^"]+)"', match.group(1))
        for expected in pipeline.APPLICATION_STATUSES + ("skipped",):
            assert expected in statuses, f"{expected} missing from tracker UI"

    def test_queue_promotion_does_not_mark_applied(self):
        for path in (SERVE_TRACKER, JOB_QUEUE_HTML):
            text = path.read_text()
            assert 'status: "applied"' not in text, f"{path.name} still promotes as applied"
            assert 'status: "generated"' in text, f"{path.name} missing generated default"
