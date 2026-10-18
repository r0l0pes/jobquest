"""Shared pytest configuration.

Gate B.1 adds LLM telemetry that appends to ``output/_telemetry/llm_calls.jsonl``
by default. Tests must never write to that production artifact, so every test
gets a throwaway telemetry path. A test module can still call
``llm_telemetry.set_telemetry_path()`` explicitly, which takes precedence over
this environment default.

This matters beyond tidiness: some pre-existing tests (for example the
``StructuredExtractor`` enrichment tests) reach a real provider client, so
without isolation a plain ``pytest tests/`` run would append live-API rows with
``run_id: null`` into the audit file that Gate B analysis reads.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_llm_telemetry(tmp_path, monkeypatch):
    """Point LLM telemetry at a per-test temporary path."""
    monkeypatch.setenv(
        "JQUEST_TELEMETRY_PATH", str(tmp_path / "_telemetry" / "llm_calls.jsonl")
    )
    yield
