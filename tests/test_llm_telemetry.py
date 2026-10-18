"""Gate B.1 tests: LLM telemetry.

Contract under test:

* the JSONL event stream (``llm_attempt`` / ``stage_result``) is well formed;
* metadata the provider response already contained is captured, and anything
  unavailable is ``null`` rather than a fabricated ``0``;
* run/stage/attempt context is isolated per :mod:`contextvars` context, so
  concurrent runs cannot cross-contaminate;
* a concrete provider/model attempt is the unit of numbering, including the
  internal Gemini model walk, while low-level HTTP retries are aggregated;
* nothing sensitive (prompts, responses, keys, exception messages) is written;
* telemetry never changes pipeline behaviour: no extra requests, no swallowed
  exceptions, and a filesystem failure is inert.

No network access: every provider response is mocked.
"""

import io
import json
import threading
from pathlib import Path
from typing import Any
from unittest import mock

import httpx
import pytest
from rich.console import Console

import modules.llm_client as llm_module
import modules.llm_telemetry as llm_telemetry
from modules.llm_client import (
    GroqClient,
    OpenRouterClient,
    _anthropic_response_metadata,
    _as_token_count,
    _gemini_response_metadata,
    _openai_compatible_response_metadata,
    _WritingFallbackClient,
)

SENTINEL_SYSTEM = "SYSTEM-PROMPT-SENTINEL-AAA"
SENTINEL_USER = "USER-PROMPT-SENTINEL-BBB"
SENTINEL_RESPONSE = "RESPONSE-CONTENT-SENTINEL-DDD"
SENTINEL_KEY = "sk-API-KEY-SENTINEL-EEE"
SENTINEL_ERROR = "EXCEPTION-MESSAGE-SENTINEL-FFF"


# ── Fixtures / helpers ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def telemetry_file(tmp_path):
    """Point telemetry at a temp file and clear context around every test."""
    path = tmp_path / "llm_calls.jsonl"
    llm_telemetry.set_telemetry_path(path)
    llm_telemetry.reset_telemetry_context()
    try:
        yield path
    finally:
        llm_telemetry.reset_telemetry_context()
        llm_telemetry.set_telemetry_path(None)


def _events(path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def _attempts(path) -> list[dict[str, Any]]:
    return [e for e in _events(path) if e["event_type"] == "llm_attempt"]


def _stage_results(path) -> list[dict[str, Any]]:
    return [e for e in _events(path) if e["event_type"] == "stage_result"]


class _FakeResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(
        self,
        payload: Any,
        status_code: int = 200,
        url: str = "https://example.invalid",
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self._request = httpx.Request("POST", url)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(  # noqa: TRY003 - mirrors httpx's own message
                f"Server error '{self.status_code}' for url '{self._request.url}'",
                request=self._request,
                response=httpx.Response(self.status_code, request=self._request),
            )

    def json(self) -> Any:
        return self._payload


def _groq_payload(content: str = "ok", **usage: Any) -> dict[str, Any]:
    return {
        "id": "req-1",
        "model": "llama-3.3-70b-versatile",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": dict(usage),
    }


def _console() -> Console:
    return Console(file=io.StringIO(), width=200)


# ── 1-4: JSONL well-formedness and schema ────────────────────────────────────


class TestEventStream:
    def test_valid_jsonl_line(self, telemetry_file):
        llm_telemetry.emit_attempt(client_class="X", success=True)
        raw = telemetry_file.read_text().strip()
        assert raw.count("\n") == 0
        assert json.loads(raw)["event_type"] == "llm_attempt"

    def test_emit_attempt_event_type_and_schema(self, telemetry_file):
        llm_telemetry.emit_attempt(
            client_class="GroqClient",
            success=True,
            requested_provider="groq",
            requested_model="llama-3.3-70b-versatile",
            served_provider="groq",
            served_model="llama-3.3-70b-versatile",
            input_tokens=10,
            output_tokens=2,
            latency_ms=5,
            finish_reason="stop",
        )
        event = _attempts(telemetry_file)[0]
        assert event["event_type"] == "llm_attempt"
        for field in (
            "ts", "run_id", "stage", "step_index", "attempt", "client_class",
            "requested_provider", "requested_model", "served_provider",
            "served_model", "chain_index", "condensed", "input_tokens",
            "output_tokens", "cached_tokens", "reasoning_tokens", "latency_ms",
            "finish_reason", "success", "error_type", "fallback_from",
            "fallback_to", "reported_cost_usd",
        ):
            assert field in event, field
        assert event["success"] is True

    def test_emit_stage_result_event_type_and_schema(self, telemetry_file):
        llm_telemetry.emit_stage_result(
            stage="ats",
            success=True,
            step_index=8,
            selected_attempt=1,
            structured_parse_success=True,
        )
        event = _stage_results(telemetry_file)[0]
        assert event["event_type"] == "stage_result"
        for field in (
            "ts", "run_id", "stage", "step_index", "success",
            "selected_attempt", "structured_parse_success", "degradation",
        ):
            assert field in event, field

    def test_unavailable_metadata_serializes_as_null_not_zero(self, telemetry_file):
        """Absent provider metadata must be null, never a fabricated 0."""
        llm_telemetry.emit_attempt(client_class="X", success=True)
        event = _attempts(telemetry_file)[0]
        for field in (
            "run_id", "stage", "step_index", "attempt", "chain_index",
            "input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens",
            "latency_ms", "finish_reason", "error_type", "fallback_from",
            "fallback_to", "served_provider", "served_model", "reported_cost_usd",
        ):
            assert event[field] is None, f"{field} should be null, got {event[field]!r}"

    def test_genuine_zero_is_preserved(self, telemetry_file):
        """A real zero (e.g. no cache hits) must survive, unlike an absent value."""
        llm_telemetry.emit_attempt(
            client_class="X", success=True, cached_tokens=0, input_tokens=0
        )
        event = _attempts(telemetry_file)[0]
        assert event["cached_tokens"] == 0
        assert event["input_tokens"] == 0

    def test_two_events_produce_two_lines(self, telemetry_file):
        llm_telemetry.emit_attempt(client_class="X", success=True)
        llm_telemetry.emit_stage_result(stage="s", success=True)
        lines = [
            line
            for line in telemetry_file.read_text().splitlines()
            if line.strip()
        ]
        assert len(lines) == 2
        assert [json.loads(line)["event_type"] for line in lines] == [
            "llm_attempt",
            "stage_result",
        ]


# ── 5-10, 22: context propagation, attempt numbering, isolation ──────────────


class TestContextPropagation:
    def test_run_id_and_stage_propagation(self, telemetry_file):
        llm_telemetry.set_run_context("Acme_2026-10-06T120000_ab12cd")
        with llm_telemetry.stage_context("ats", step_index=8):
            llm_telemetry.emit_attempt(client_class="X", success=True)
        event = _attempts(telemetry_file)[0]
        assert event["run_id"] == "Acme_2026-10-06T120000_ab12cd"
        assert event["stage"] == "ats"
        assert event["step_index"] == 8

    def test_attempt_numbering_increments_within_stage(self, telemetry_file):
        with llm_telemetry.stage_context("tailor_3b_edits"):
            llm_telemetry.emit_attempt(client_class="A", success=False)
            llm_telemetry.emit_attempt(client_class="B", success=True)
            llm_telemetry.emit_attempt(client_class="C", success=True)
        assert [e["attempt"] for e in _attempts(telemetry_file)] == [1, 2, 3]

    def test_attempt_numbering_resets_per_stage(self, telemetry_file):
        with llm_telemetry.stage_context("fit"):
            llm_telemetry.emit_attempt(client_class="A", success=True)
        with llm_telemetry.stage_context("ats"):
            llm_telemetry.emit_attempt(client_class="B", success=True)
        assert [e["attempt"] for e in _attempts(telemetry_file)] == [1, 1]

    def test_chain_index_and_condensed_propagation(self, telemetry_file):
        with (
            llm_telemetry.stage_context("qa_cover_letter"),
            llm_telemetry.attempt_context(chain_index=3, condensed=True),
        ):
            llm_telemetry.emit_attempt(client_class="X", success=True)
        event = _attempts(telemetry_file)[0]
        assert event["chain_index"] == 3
        assert event["condensed"] is True

    def test_condensed_defaults_to_false_for_direct_calls(self, telemetry_file):
        with llm_telemetry.stage_context("ats"):
            llm_telemetry.emit_attempt(client_class="X", success=True)
        assert _attempts(telemetry_file)[0]["condensed"] is False

    def test_fallback_relationship_and_selected_attempt(self, telemetry_file):
        with llm_telemetry.stage_context("tailor_3b_edits") as st:
            llm_telemetry.emit_attempt(
                client_class="A",
                success=False,
                requested_provider="gemini",
                requested_model="models/gemini-2.5-pro",
            )
            llm_telemetry.emit_attempt(
                client_class="B",
                success=True,
                requested_provider="gemini",
                requested_model="models/gemini-3.7-flash",
            )
        first, second = _attempts(telemetry_file)
        assert first["fallback_from"] is None
        assert first["fallback_to"] is None
        assert second["fallback_from"] == "gemini/models/gemini-2.5-pro"
        assert second["fallback_to"] == "gemini/models/gemini-3.7-flash"
        result = _stage_results(telemetry_file)[0]
        assert result["selected_attempt"] == 2
        # B.1.5: both attempts were served by the same provider (gemini), so this
        # is a MODEL fallback, not a provider fallback.
        assert result["degradation"] == "model_fallback_used"
        assert st.selected_attempt == 2

    def test_provider_fallback_used_requires_a_real_provider_change(
        self, telemetry_file
    ):
        with llm_telemetry.stage_context("reviewer"):
            llm_telemetry.emit_attempt(
                client_class="A",
                success=False,
                requested_provider="openrouter",
                requested_model="vendor/a",
            )
            llm_telemetry.emit_attempt(
                client_class="B",
                success=True,
                requested_provider="groq",
                requested_model="vendor/b",
            )
        result = _stage_results(telemetry_file)[0]
        assert result["degradation"] == "provider_fallback_used"

    def test_same_route_second_call_is_not_a_fallback(self, telemetry_file):
        """A deliberate second call on the same route (cover-letter prune pass)
        must not fabricate a fallback edge or a fallback degradation."""
        with llm_telemetry.stage_context("qa_cover_letter") as st:
            llm_telemetry.emit_attempt(
                client_class="A",
                success=True,
                requested_provider="openrouter",
                requested_model="deepseek/deepseek-v4.1-flash",
            )
            llm_telemetry.emit_attempt(
                client_class="A",
                success=True,
                requested_provider="openrouter",
                requested_model="deepseek/deepseek-v4.1-flash",
            )
        first, second = _attempts(telemetry_file)
        assert first["fallback_from"] is None
        assert second["fallback_from"] is None
        assert second["fallback_to"] is None
        result = _stage_results(telemetry_file)[0]
        assert result["selected_attempt"] == 2
        assert result["degradation"] is None
        assert st.selected_attempt == 2

    def test_get_last_successful_attempt_skips_failures(self):
        with llm_telemetry.stage_context("reviewer"):
            llm_telemetry.emit_attempt(client_class="A", success=False)
            assert llm_telemetry.get_last_successful_attempt() is None
            llm_telemetry.emit_attempt(client_class="B", success=True)
            assert llm_telemetry.get_last_successful_attempt() == 2

    def test_nested_stages_do_not_share_attempt_state(self, telemetry_file):
        with llm_telemetry.stage_context("outer"):
            llm_telemetry.emit_attempt(client_class="A", success=True)
            with llm_telemetry.stage_context("inner"):
                llm_telemetry.emit_attempt(client_class="B", success=True)
            llm_telemetry.emit_attempt(client_class="C", success=True)
        by_stage: dict[str, list[Any]] = {}
        for event in _attempts(telemetry_file):
            by_stage.setdefault(event["stage"], []).append(event["attempt"])
        assert by_stage == {"outer": [1, 2], "inner": [1]}

    def test_contextvar_isolation_across_concurrent_runs(self, telemetry_file):
        """Two concurrent runs must never cross-contaminate run_id or stage."""
        barrier = threading.Barrier(2)

        def worker(tag: str) -> None:
            llm_telemetry.set_run_context(f"run-{tag}")
            with llm_telemetry.stage_context(f"stage_{tag}"):
                barrier.wait(timeout=5)
                llm_telemetry.emit_attempt(
                    client_class="X",
                    success=True,
                    requested_model=f"model-{tag}",
                )

        threads = [
            threading.Thread(target=worker, args=(tag,)) for tag in ("a", "b")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        events = _attempts(telemetry_file)
        assert len(events) == 2
        for event in events:
            tag = str(event["stage"]).removeprefix("stage_")
            assert event["run_id"] == f"run-{tag}"
            assert event["requested_model"] == f"model-{tag}"

    def test_reset_clears_context(self, telemetry_file):
        llm_telemetry.set_run_context("run-x")
        llm_telemetry.reset_telemetry_context()
        assert llm_telemetry.current_run_id() is None
        llm_telemetry.emit_attempt(client_class="X", success=True)
        assert _attempts(telemetry_file)[0]["run_id"] is None


# ── 17-18: stage_result and structured_parse_success ─────────────────────────


class TestStageResults:
    def test_stage_result_records_parse_success(self, telemetry_file):
        with llm_telemetry.stage_context("fit") as st:
            llm_telemetry.emit_attempt(client_class="X", success=True)
            st.set_parse_result(True)
        assert _stage_results(telemetry_file)[0]["structured_parse_success"] is True

    def test_stage_result_records_parse_failure_and_degradation(self, telemetry_file):
        with llm_telemetry.stage_context("fit") as st:
            llm_telemetry.emit_attempt(client_class="X", success=True)
            st.set_parse_result(False)
            st.set_success(False)
            st.set_degradation("optional_stage_failed")
        result = _stage_results(telemetry_file)[0]
        assert result["structured_parse_success"] is False
        assert result["success"] is False
        assert result["degradation"] == "optional_stage_failed"

    def test_free_form_stage_reports_null_parse_result(self, telemetry_file):
        """Prose stages have no structured parse, so the field stays null."""
        with llm_telemetry.stage_context("tailor_3a"):
            llm_telemetry.emit_attempt(client_class="X", success=True)
        result = _stage_results(telemetry_file)[0]
        assert result["structured_parse_success"] is None
        assert result["degradation"] is None

    def test_stage_result_emits_on_exception_and_reraises(self, telemetry_file):
        with (
            pytest.raises(ValueError, match=SENTINEL_ERROR),
            llm_telemetry.stage_context("tailor_3b_full") as st,
        ):
            llm_telemetry.emit_attempt(client_class="X", success=True)
            st.set_parse_result(False)
            raise ValueError(SENTINEL_ERROR)
        result = _stage_results(telemetry_file)[0]
        assert result["success"] is False
        assert result["structured_parse_success"] is False
        assert result["error_type"] == "ValueError"

    def test_no_llm_path_emits_no_stage_result(self, telemetry_file):
        """A skipped/non-LLM path contributes no LLM telemetry at all."""
        with llm_telemetry.stage_context("jd_extraction"):
            pass
        assert _events(telemetry_file) == []

    def test_exception_before_any_attempt_still_reports_failure(self, telemetry_file):
        with (
            pytest.raises(RuntimeError),
            llm_telemetry.stage_context("jd_extraction"),
        ):
            raise RuntimeError("no provider configured")  # noqa: TRY003
        result = _stage_results(telemetry_file)[0]
        assert result["success"] is False
        assert result["selected_attempt"] is None


# ── 11-16, 19: provider metadata capture, privacy, failure safety ────────────


class TestProviderMetadataCapture:
    def test_successful_response_records_usage_and_served_model(self, telemetry_file):
        payload = _groq_payload(
            content=SENTINEL_RESPONSE, prompt_tokens=1200, completion_tokens=345
        )
        client = GroqClient(api_key=SENTINEL_KEY)
        with mock.patch("httpx.post", return_value=_FakeResponse(payload)):
            result = client.generate(SENTINEL_SYSTEM, SENTINEL_USER, temperature=0.1)
        assert result == SENTINEL_RESPONSE
        event = _attempts(telemetry_file)[0]
        assert event["input_tokens"] == 1200
        assert event["output_tokens"] == 345
        assert event["cached_tokens"] is None
        assert event["reasoning_tokens"] is None
        assert event["served_model"] == "llama-3.3-70b-versatile"
        assert event["served_provider"] == "groq"
        assert event["requested_model"] == "llama-3.3-70b-versatile"
        assert event["finish_reason"] == "stop"
        assert event["success"] is True
        assert event["client_class"] == "GroqClient"
        assert isinstance(event["latency_ms"], int)
        assert event["transport_retries"] == 0

    def test_zero_cache_hits_are_recorded_as_zero(self, telemetry_file):
        payload = _groq_payload(prompt_tokens=10, completion_tokens=1)
        payload["usage"]["prompt_tokens_details"] = {"cached_tokens": 0}
        client = GroqClient(api_key=SENTINEL_KEY)
        with mock.patch("httpx.post", return_value=_FakeResponse(payload)):
            client.generate("s", "u")
        assert _attempts(telemetry_file)[0]["cached_tokens"] == 0

    def test_failed_attempt_records_error_class_only(self, telemetry_file):
        client = GroqClient(api_key=SENTINEL_KEY)
        with (
            mock.patch("httpx.post", return_value=_FakeResponse({}, status_code=500)),
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.generate(SENTINEL_SYSTEM, SENTINEL_USER)
        event = _attempts(telemetry_file)[0]
        assert event["success"] is False
        assert event["error_type"] == "HTTPStatusError"

    def test_exception_message_is_not_written(self, telemetry_file):
        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise ValueError(SENTINEL_ERROR)

        client = GroqClient(api_key=SENTINEL_KEY)
        with (
            mock.patch("httpx.post", side_effect=_boom),
            pytest.raises(ValueError),
        ):
            client.generate(SENTINEL_SYSTEM, SENTINEL_USER)
        assert SENTINEL_ERROR not in telemetry_file.read_text()
        assert _attempts(telemetry_file)[0]["error_type"] == "ValueError"

    def test_prompt_response_and_key_contents_are_never_written(self, telemetry_file):
        payload = _groq_payload(content=SENTINEL_RESPONSE, prompt_tokens=5)
        client = GroqClient(api_key=SENTINEL_KEY)
        with mock.patch("httpx.post", return_value=_FakeResponse(payload)):
            client.generate(SENTINEL_SYSTEM, SENTINEL_USER)
        raw = telemetry_file.read_text()
        for secret in (
            SENTINEL_SYSTEM,
            SENTINEL_USER,
            SENTINEL_RESPONSE,
            SENTINEL_KEY,
            "Authorization",
            "Bearer",
        ):
            assert secret not in raw, secret

    def test_prompt_and_key_not_written_on_failure_path(self, telemetry_file):
        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError(SENTINEL_ERROR)

        client = GroqClient(api_key=SENTINEL_KEY)
        with (
            mock.patch("httpx.post", side_effect=_boom),
            pytest.raises(RuntimeError),
        ):
            client.generate(SENTINEL_SYSTEM, SENTINEL_USER)
        raw = telemetry_file.read_text()
        for secret in (SENTINEL_SYSTEM, SENTINEL_USER, SENTINEL_KEY, SENTINEL_ERROR):
            assert secret not in raw, secret

    def test_nonfinite_usage_does_not_change_provider_behaviour(self, telemetry_file):
        """A NaN/Infinity usage field must not alter the call's outcome.

        ``json.loads`` accepts the non-standard ``NaN``/``Infinity`` literals and
        the metadata helpers run inside the provider retry block, so a raise
        there would be re-interpreted as a provider failure (extra requests,
        silent model/provider fallback) - telemetry changing routing.
        """
        payload = _groq_payload(content=SENTINEL_RESPONSE)
        payload["usage"] = {
            "prompt_tokens": float("nan"),
            "completion_tokens": float("inf"),
        }
        client = GroqClient(api_key=SENTINEL_KEY)
        with mock.patch("httpx.post", return_value=_FakeResponse(payload)) as post:
            assert client.generate("s", "u") == SENTINEL_RESPONSE
        assert post.call_count == 1  # no retry or fallback was triggered
        event = _attempts(telemetry_file)[0]
        assert event["success"] is True
        assert event["input_tokens"] is None
        assert event["output_tokens"] is None

    def test_env_api_key_is_not_written(self, telemetry_file, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", SENTINEL_KEY)
        payload = _groq_payload(prompt_tokens=5)
        client = GroqClient()
        with mock.patch("httpx.post", return_value=_FakeResponse(payload)):
            client.generate("s", "u")
        assert SENTINEL_KEY not in telemetry_file.read_text()

    def test_telemetry_write_failure_does_not_fail_caller(self, tmp_path):
        """A filesystem problem must be inert: telemetry can never break a run."""
        blocked = tmp_path / "as_a_directory"
        blocked.mkdir()
        llm_telemetry.set_telemetry_path(blocked)
        try:
            with llm_telemetry.stage_context("ats"):
                record = llm_telemetry.emit_attempt(client_class="X", success=True)
        finally:
            llm_telemetry.set_telemetry_path(None)
        assert record["event_type"] == "llm_attempt"

    def test_telemetry_write_failure_does_not_fail_stage_context(self, tmp_path):
        blocked = tmp_path / "nested_dir_path"
        blocked.mkdir()
        llm_telemetry.set_telemetry_path(blocked)
        try:
            with llm_telemetry.stage_context("ats"):
                llm_telemetry.emit_attempt(client_class="X", success=True)
        finally:
            llm_telemetry.set_telemetry_path(None)

    def test_default_path_is_the_project_telemetry_file(self, monkeypatch):
        monkeypatch.delenv("JQUEST_TELEMETRY_PATH", raising=False)
        llm_telemetry.set_telemetry_path(None)
        path = llm_telemetry.telemetry_path()
        assert path.parts[-3:] == ("output", "_telemetry", "llm_calls.jsonl")

    def test_env_var_can_override_the_path(self, monkeypatch, tmp_path):
        target = tmp_path / "custom" / "events.jsonl"
        monkeypatch.setenv("JQUEST_TELEMETRY_PATH", str(target))
        llm_telemetry.set_telemetry_path(None)
        assert llm_telemetry.telemetry_path() == target


class _FakeUsage:
    def __init__(
        self,
        prompt: int | None = None,
        candidates: int | None = None,
        cached: int | None = None,
        thoughts: int | None = None,
    ) -> None:
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.cached_content_token_count = cached
        self.thoughts_token_count = thoughts


class _FakeCandidate:
    def __init__(self, finish_reason: Any) -> None:
        self.finish_reason = finish_reason


class _FakeGeminiResponse:
    def __init__(
        self,
        text: str = "body",
        usage: _FakeUsage | None = None,
        finish_reason: Any = None,
        model_version: str | None = None,
    ) -> None:
        self.text = text
        self.usage_metadata = usage
        self.model_version = model_version
        self.candidates = (
            [] if finish_reason is None else [_FakeCandidate(finish_reason)]
        )


class TestProviderMetadataExtractors:
    """Narrow tests over representative mocked response shapes."""

    def test_openai_usage_with_cached_and_reasoning_tokens(self):
        usage, finish, model, cost = _openai_compatible_response_metadata(
            {
                "model": "deepseek-chat",
                "choices": [{"finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 40,
                    "prompt_cache_hit_tokens": 64,
                    "completion_tokens_details": {"reasoning_tokens": 12},
                },
            }
        )
        assert usage == {
            "input_tokens": 100,
            "output_tokens": 40,
            "cached_tokens": 64,
            "reasoning_tokens": 12,
        }
        assert finish == "stop"
        assert model == "deepseek-chat"
        assert cost is None

    def test_openai_absent_usage_is_all_none(self):
        usage, finish, model, cost = _openai_compatible_response_metadata(
            {"choices": [{"message": {"content": "x"}}]}
        )
        assert usage == {
            "input_tokens": None,
            "output_tokens": None,
            "cached_tokens": None,
            "reasoning_tokens": None,
        }
        assert finish is None and model is None and cost is None

    def test_openai_cost_only_read_when_present(self):
        _, _, _, cost = _openai_compatible_response_metadata(
            {"usage": {"prompt_tokens": 1, "cost": 0.00042}}
        )
        assert cost == pytest.approx(0.00042)
        _, _, _, absent = _openai_compatible_response_metadata(
            {"usage": {"prompt_tokens": 1}}
        )
        assert absent is None

    def test_openai_malformed_body_is_tolerated(self):
        assert _openai_compatible_response_metadata(None)[0]["input_tokens"] is None
        assert (
            _openai_compatible_response_metadata({"usage": "nope"})[0]["output_tokens"]
            is None
        )

    def test_anthropic_usage_and_stop_reason(self):
        usage, stop, model, cost = _anthropic_response_metadata(
            {
                "model": "claude-haiku-4-5-20251001",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 900,
                    "output_tokens": 120,
                    "cache_read_input_tokens": 300,
                },
            }
        )
        assert usage["input_tokens"] == 900
        assert usage["output_tokens"] == 120
        assert usage["cached_tokens"] == 300
        assert stop == "end_turn"
        assert model == "claude-haiku-4-5-20251001"
        assert cost is None

    def test_gemini_metadata_with_usage(self):
        response = _FakeGeminiResponse(
            usage=_FakeUsage(prompt=2048, candidates=512, cached=0, thoughts=77),
            finish_reason="FinishReason.STOP",
            model_version="gemini-3.7-flash-001",
        )
        usage, finish, served = _gemini_response_metadata(response)
        assert usage["input_tokens"] == 2048
        assert usage["output_tokens"] == 512
        assert usage["cached_tokens"] == 0
        assert usage["reasoning_tokens"] == 77
        assert finish == "STOP"
        assert served == "gemini-3.7-flash-001"

    def test_nonfinite_token_counts_coerce_to_none(self):
        assert _as_token_count(float("nan")) is None
        assert _as_token_count(float("inf")) is None
        assert _as_token_count(float("-inf")) is None
        assert _as_token_count(0) == 0
        assert _as_token_count(12.7) == 12
        assert _as_token_count(True) is None
        assert _as_token_count("12") is None

    def test_gemini_metadata_absent_is_tolerated(self):
        usage, finish, served = _gemini_response_metadata(_FakeGeminiResponse())
        assert usage == {}
        assert finish is None and served is None


# ── 21, 24: composites — one attempt per concrete provider/model ─────────────


class TestCompositeFallbackVisibility:
    def test_writing_chain_emits_one_attempt_per_provider(self, telemetry_file):
        payload = {
            "model": "qwen/qwen3.5-397b-a17b",
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 1},
        }

        def _post(url: str, **_kwargs: Any) -> _FakeResponse:
            if "groq.com" in url:
                return _FakeResponse({}, status_code=500)
            return _FakeResponse(payload)

        groq = GroqClient(api_key=SENTINEL_KEY)
        router = OpenRouterClient(api_key=SENTINEL_KEY)
        chain = _WritingFallbackClient([(groq, 0), (router, 0)])

        with (
            llm_telemetry.stage_context("tailor_3b_edits") as st,
            mock.patch("httpx.post", side_effect=_post),
        ):
            assert chain.generate("s", "u") == "ok"

        first, second = _attempts(telemetry_file)
        assert first["attempt"] == 1
        assert first["chain_index"] == 0
        assert first["requested_provider"] == "groq"
        assert first["success"] is False
        assert first["error_type"] == "HTTPStatusError"
        assert second["attempt"] == 2
        assert second["chain_index"] == 1
        assert second["requested_provider"] == "openrouter"
        assert second["success"] is True
        assert str(second["fallback_from"]).startswith("groq/")
        assert str(second["fallback_to"]).startswith("openrouter/")
        assert st.selected_attempt == 2
        assert _stage_results(telemetry_file)[0]["structured_parse_success"] is None

    def test_chain_index_and_condensed_reach_the_concrete_attempt(self, telemetry_file):
        payload = _groq_payload(prompt_tokens=1)
        groq = GroqClient(api_key=SENTINEL_KEY)
        chain = _WritingFallbackClient([(groq, 0)])
        with (
            llm_telemetry.stage_context("tailor_3b_edits"),
            mock.patch("httpx.post", return_value=_FakeResponse(payload)),
        ):
            chain.generate("s", "u")
        event = _attempts(telemetry_file)[0]
        assert event["chain_index"] == 0
        assert event["condensed"] is False

    def test_composite_model_name_is_not_reported_as_served_model(self, telemetry_file):
        payload = _groq_payload(prompt_tokens=1)
        groq = GroqClient(api_key=SENTINEL_KEY)
        chain = _WritingFallbackClient([(groq, 0)])
        assert chain.model_name().startswith("writing/")
        with (
            llm_telemetry.stage_context("tailor_3a"),
            mock.patch("httpx.post", return_value=_FakeResponse(payload)),
        ):
            chain.generate("s", "u")
        event = _attempts(telemetry_file)[0]
        assert event["served_model"] == "llama-3.3-70b-versatile"
        assert not str(event["served_model"]).startswith("writing/")

    def test_instrumentation_adds_no_extra_request(self, telemetry_file):
        """Call telemetry must be 1:1 with concrete requests."""
        payload = _groq_payload(prompt_tokens=1)
        groq = GroqClient(api_key=SENTINEL_KEY)
        with (
            llm_telemetry.stage_context("ats"),
            mock.patch("httpx.post", return_value=_FakeResponse(payload)) as post,
        ):
            groq.generate("s", "u")
        assert post.call_count == 1
        assert len(_attempts(telemetry_file)) == 1


class _FakeGeminiModels:
    """Fake ``client.models`` that records the models actually addressed."""

    def __init__(self, behavior: dict[str, Any]) -> None:
        self.calls: list[str] = []
        self._behavior = behavior

    def generate_content(  # noqa: ARG002 - names must match the SDK's keyword call
        self, model: str, contents: Any, config: Any
    ) -> Any:
        self.calls.append(model)
        outcome = self._behavior[model]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeGenaiClient:
    def __init__(self, models: _FakeGeminiModels) -> None:
        self.models = models


class _TestGeminiClient(llm_module.GeminiClient):
    """GeminiClient whose SDK client is replaced by a fake (no network)."""

    _client: Any
    _model_id: str

    def __init__(self, model_id: str, behavior: dict[str, Any]) -> None:
        self._model_id = model_id
        self._api_key = SENTINEL_KEY
        # B.1.5: the Gemini model walk is opt-in, so this fake must request it
        # explicitly to exercise the walk (production never enables it).
        self._model_fallback = True
        self.models = _FakeGeminiModels(behavior)
        self._client = _FakeGenaiClient(self.models)


class TestGeminiInternalModelWalk:
    """The Gemini client can change model inside a single generate() call."""

    def test_one_attempt_per_model_with_aggregated_retries(
        self, telemetry_file, monkeypatch
    ):
        monkeypatch.setattr(
            llm_module, "MODEL_FALLBACK_ORDER", ["models/gemini-fallback"]
        )
        monkeypatch.setattr(llm_module, "RETRY_BASE_DELAY", 0.0)

        usage = _FakeUsage(prompt=500, candidates=100)
        # Primary truncates on both of its tries, then the fallback works.
        client = _TestGeminiClient(
            "models/gemini-primary",
            {
                "models/gemini-primary": _FakeGeminiResponse(
                    finish_reason="MAX_TOKENS", usage=usage
                ),
                "models/gemini-fallback": _FakeGeminiResponse(
                    finish_reason="STOP",
                    usage=usage,
                    model_version="gemini-fallback-001",
                ),
            },
        )

        with llm_telemetry.stage_context("fit"):
            assert client.generate("s", "u") == "body"

        first, second = _attempts(telemetry_file)
        # One attempt per concrete model, even though the primary was tried twice.
        assert first["attempt"] == 1
        assert first["requested_model"] == "models/gemini-primary"
        assert first["success"] is False
        assert first["finish_reason"] == "MAX_TOKENS"
        assert first["transport_retries"] == 1
        assert second["attempt"] == 2
        assert second["requested_model"] == "models/gemini-primary"
        assert second["served_model"] == "gemini-fallback-001"
        assert second["success"] is True
        assert second["fallback_from"] == "gemini/models/gemini-primary"
        assert client.models.calls == [
            "models/gemini-primary",
            "models/gemini-primary",
            "models/gemini-fallback",
        ]

    def test_exhausted_models_report_individual_failures(
        self, telemetry_file, monkeypatch
    ):
        monkeypatch.setattr(
            llm_module, "MODEL_FALLBACK_ORDER", ["models/gemini-fallback"]
        )
        monkeypatch.setattr(llm_module, "RETRY_BASE_DELAY", 0.0)
        client = _TestGeminiClient(
            "models/gemini-primary",
            {
                "models/gemini-primary": RuntimeError("primary down"),
                "models/gemini-fallback": RuntimeError("fallback down"),
            },
        )

        with (
            pytest.raises(RuntimeError, match="All Gemini models exhausted"),
            llm_telemetry.stage_context("tailor_3b_full"),
        ):
            client.generate("s", "u")

        attempts = _attempts(telemetry_file)
        assert [a["success"] for a in attempts] == [False, False]
        assert [a["error_type"] for a in attempts] == ["RuntimeError", "RuntimeError"]
        result = _stage_results(telemetry_file)[0]
        assert result["success"] is False
        assert result["error_type"] == "RuntimeError"


# ── 23: Firecrawl success must not create a fake LLM attempt ────────────────


class TestStructuredExtractionPath:
    def test_firecrawl_success_emits_no_llm_events(self, telemetry_file, monkeypatch):
        from modules.scrapers.sources.structured_extractor import StructuredExtractor

        monkeypatch.setenv("FIRECRAWL_API_KEY", "present")
        extractor = StructuredExtractor()
        with mock.patch.object(
            extractor,
            "_extract_via_firecrawl",
            return_value={"required_skills": ["Python"]},
        ):
            job = extractor.enrich({"url": "https://x", "description": "A" * 200})
        assert job["required_skills"] == ["Python"]
        assert _events(telemetry_file) == []

    def test_llm_fallback_is_visible_as_jd_extraction(
        self, telemetry_file, monkeypatch
    ):
        from modules.scrapers.sources.structured_extractor import StructuredExtractor

        payload = _groq_payload(
            content='{"required_skills": ["Python"], "remote_policy": "hybrid"}',
            prompt_tokens=42,
        )
        monkeypatch.setenv("FIRECRAWL_API_KEY", "present")
        # B.1.5: JD extraction owns JD routing; the ATS factory no longer serves it.
        monkeypatch.setattr(
            llm_module, "create_jd_client", lambda: GroqClient(api_key=SENTINEL_KEY)
        )
        extractor = StructuredExtractor()
        with (
            mock.patch.object(extractor, "_extract_via_firecrawl", return_value=None),
            mock.patch("httpx.post", return_value=_FakeResponse(payload)),
        ):
            job = extractor.enrich({"url": "https://x", "description": "A" * 200})

        assert job["required_skills"] == ["Python"]
        attempt = _attempts(telemetry_file)[0]
        assert attempt["stage"] == "jd_extraction"
        assert attempt["step_index"] == 1
        result = _stage_results(telemetry_file)[0]
        assert result["stage"] == "jd_extraction"
        assert result["structured_parse_success"] is True

    def test_unparseable_llm_output_reports_parse_failure(
        self, telemetry_file, monkeypatch
    ):
        from modules.scrapers.sources.structured_extractor import StructuredExtractor

        payload = _groq_payload(content="no json here at all", prompt_tokens=9)
        monkeypatch.setenv("FIRECRAWL_API_KEY", "present")
        # B.1.5: JD extraction owns JD routing; the ATS factory no longer serves it.
        monkeypatch.setattr(
            llm_module, "create_jd_client", lambda: GroqClient(api_key=SENTINEL_KEY)
        )
        extractor = StructuredExtractor()
        with (
            mock.patch.object(extractor, "_extract_via_firecrawl", return_value=None),
            mock.patch("httpx.post", return_value=_FakeResponse(payload)),
        ):
            job = extractor.enrich({"url": "https://x", "description": "A" * 200})

        assert "required_skills" not in job
        result = _stage_results(telemetry_file)[0]
        assert result["structured_parse_success"] is False
        assert result["success"] is False
        assert result["degradation"] == "optional_stage_failed"


# ── 25: behaviour preservation at real pipeline call sites ──────────────────


class TestStageWiring:
    """Structural guard: every LLM stage must still open a telemetry stage.

    This pins the ten instrumented call sites against accidental removal or
    renaming during a refactor. It is a wiring guard, not behaviour coverage:
    ``ats`` and ``jd_extraction`` have end-to-end behaviour tests above, and
    per-stage behaviour tests for the remaining sites are still outstanding
    (recorded in the Gate B.1 report).
    """

    PIPELINE_STAGES = (
        "fit",
        "tailor_3a",
        "tailor_3b_edits",
        "tailor_3b_full",
        "tailor_3c",
        "reviewer",
        "ats",
        "qa_cover_letter",
        "interview_prep",
    )

    def test_every_pipeline_stage_is_instrumented(self):
        source = (Path(llm_module.__file__).parent / "pipeline.py").read_text()
        missing = [
            stage
            for stage in self.PIPELINE_STAGES
            if f'stage_context("{stage}"' not in source
        ]
        assert missing == [], f"stage(s) lost their telemetry stage_context: {missing}"

    def test_jd_extraction_is_instrumented(self):
        from modules.scrapers.sources import structured_extractor

        source = Path(structured_extractor.__file__).read_text()
        assert 'stage_context("jd_extraction"' in source

    def test_run_context_is_installed_by_ensure_run_dir(self):
        source = (Path(llm_module.__file__).parent / "pipeline.py").read_text()
        assert "llm_telemetry.set_run_context(" in source


class TestPipelineIntegration:
    def _ats_ctx(self, tmp_path) -> dict:
        return {
            "job": {"title": "PM", "company": "Acme", "description": "jd"},
            "run_dir": str(tmp_path),
            "company_safe": "Acme",
            "tailored_latex": "tex",
            "skills_inventory": "",
        }

    def test_ats_step_records_run_id_stage_and_parse_result(
        self, telemetry_file, tmp_path, monkeypatch
    ):
        import modules.pipeline as pipeline

        ats_body = (
            "```json\n"
            '{"company": "Acme", "job_title": "PM", '
            '"coverage_score": {"coverage_pct": 88, "verdict": "PASS"}, '
            '"suggested_edits": [], "consistency": {}}\n'
            "```\n"
        )
        payload = _groq_payload(content=ats_body, prompt_tokens=99)
        ctx = self._ats_ctx(tmp_path)
        client = GroqClient(api_key=SENTINEL_KEY)
        # B.1.5: the ATS stage owns its route, so inject through its factory.
        monkeypatch.setattr(pipeline, "create_ats_client", lambda: client)
        with mock.patch("httpx.post", return_value=_FakeResponse(payload)):
            pipeline.step_ats_check(ctx, client, _console())

        assert ctx["ats_status"] == pipeline.STAGE_OK
        attempt = _attempts(telemetry_file)[0]
        assert attempt["stage"] == "ats"
        assert attempt["step_index"] == 8
        result = _stage_results(telemetry_file)[0]
        assert result["stage"] == "ats"
        assert result["structured_parse_success"] is True
        assert result["success"] is True
        assert result["selected_attempt"] == 1

    def test_ats_step_unusable_payload_reports_parse_failure(
        self, telemetry_file, tmp_path, monkeypatch
    ):
        import modules.pipeline as pipeline

        payload = _groq_payload(
            content='{"error": "cannot analyse"}', prompt_tokens=10
        )
        ctx = self._ats_ctx(tmp_path)
        client = GroqClient(api_key=SENTINEL_KEY)
        # B.1.5: the ATS stage owns its route, so inject through its factory.
        monkeypatch.setattr(pipeline, "create_ats_client", lambda: client)
        with mock.patch("httpx.post", return_value=_FakeResponse(payload)):
            pipeline.step_ats_check(ctx, client, _console())

        assert ctx["ats_status"] == pipeline.STAGE_FAILED
        result = _stage_results(telemetry_file)[0]
        assert result["structured_parse_success"] is False
        assert result["success"] is False

    def test_ensure_run_dir_installs_run_context(
        self, telemetry_file, tmp_path, monkeypatch
    ):
        import modules.pipeline as pipeline

        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path / "output")
        ctx: dict = {"company_safe": "Acme"}
        pipeline.ensure_run_dir(ctx, "Acme")
        assert llm_telemetry.current_run_id() == ctx["run_id"]

        with llm_telemetry.stage_context("fit"):
            llm_telemetry.emit_attempt(client_class="X", success=True)
        assert _attempts(telemetry_file)[0]["run_id"] == ctx["run_id"]

    def test_client_exception_type_propagates_unchanged(self, telemetry_file):
        """Instrumentation must not translate or swallow provider errors."""

        class _CustomError(Exception):
            pass

        def _boom(*_args: Any, **_kwargs: Any) -> Any:
            raise _CustomError(SENTINEL_ERROR)

        client = GroqClient(api_key=SENTINEL_KEY)
        with (
            mock.patch("httpx.post", side_effect=_boom),
            pytest.raises(_CustomError),
        ):
            client.generate("s", "u")
        assert _attempts(telemetry_file)[0]["error_type"] == "_CustomError"

    def test_stage_context_does_not_alter_return_value(self, telemetry_file):
        """The wrapper must not change what the provider call returns."""
        payload = _groq_payload(content=SENTINEL_RESPONSE, prompt_tokens=1)
        client = GroqClient(api_key=SENTINEL_KEY)
        with mock.patch("httpx.post", return_value=_FakeResponse(payload)):
            unwrapped = client.generate("s", "u")
        with (
            mock.patch("httpx.post", return_value=_FakeResponse(payload)),
            llm_telemetry.stage_context("ats"),
        ):
            wrapped = client.generate("s", "u")
        assert unwrapped == wrapped == SENTINEL_RESPONSE
