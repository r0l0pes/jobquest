"""LLM telemetry for the JobQuest application pipeline (Gate B.1).

Observability only. Nothing in this module may change pipeline behaviour:
it does not choose providers, models, retries, prompts or parsers, and a
telemetry failure must never fail an application run.

Two event types are appended, one JSON object per line, to
``output/_telemetry/llm_calls.jsonl``:

* ``llm_attempt``  - one concrete provider/model attempt. Emitted by the
  provider client that actually performed the call.
* ``stage_result`` - one logical pipeline stage outcome: whether the stage
  succeeded, whether its structured parse succeeded, which attempt was
  consumed, and (where directly observable) how it degraded.

Design constraints:

* stdlib only.
* Run/stage/attempt state lives in :mod:`contextvars` so concurrent runs
  (the Gradio launcher can start several jobs at once) cannot
  cross-contaminate ``run_id``, ``stage`` or attempt numbering.
* Unavailable metadata is written as ``null``. Zero is never used to mean
  "unavailable" (a genuine zero token count or cache hit is preserved).
* Nothing sensitive is written: no API keys, prompts, responses, resume/JD
  text or exception messages - only exception class names.
* The JSONL write catches ``OSError`` only, so telemetry cannot break a run
  on a filesystem problem while genuine programming errors still surface.
"""

from __future__ import annotations

import contextvars
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "EVENT_ATTEMPT",
    "EVENT_STAGE_RESULT",
    "AttemptProbe",
    "attempt_context",
    "current_run_id",
    "current_stage",
    "elapsed_ms",
    "emit_attempt",
    "emit_stage_result",
    "get_last_successful_attempt",
    "reset_telemetry_context",
    "set_run_context",
    "set_telemetry_path",
    "stage_context",
    "telemetry_path",
]

EVENT_ATTEMPT = "llm_attempt"
EVENT_STAGE_RESULT = "stage_result"

# Canonical storage location. Overridable for tests via set_telemetry_path()
# or the JQUEST_TELEMETRY_PATH environment variable (path resolution only;
# never run state).
_DEFAULT_TELEMETRY_PATH = (
    Path(__file__).resolve().parent.parent / "output" / "_telemetry" / "llm_calls.jsonl"
)

_override_path: Path | None = None

# ── Context variables ────────────────────────────────────────────────────────
# _run_id        : the canonical run identity from ctx["run_id"].
# _stage         : {"stage": str, "step_index": int | None} for the active stage.
# _stage_state   : mutable per-stage counters. A fresh dict is installed by
#                  stage_context, so nested/concurrent stages are isolated.
# _attempt_meta  : composite-client decorations (chain_index, condensed).

_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "jquest_telemetry_run_id", default=None
)
_stage: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "jquest_telemetry_stage", default=None
)
_stage_state: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "jquest_telemetry_stage_state", default=None
)
_attempt_meta: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "jquest_telemetry_attempt_meta", default=None
)


# ── Value coercion ───────────────────────────────────────────────────────────


def _as_int(value: Any) -> int | None:
    """Return ``value`` as an int, or None when it is not a usable count.

    Booleans are not counts. Non-numeric values are not guessed at.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return int(value)
    return None


def elapsed_ms(started: float) -> int:
    """Milliseconds elapsed since a ``time.perf_counter()`` reading."""
    return round((time.perf_counter() - started) * 1000)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _safe_scalar(value: Any) -> Any:
    """Coerce a value to something JSON-serialisable without inventing data."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    return str(value)


# ── Storage ──────────────────────────────────────────────────────────────────


def set_telemetry_path(path: str | os.PathLike[str] | None) -> None:
    """Override the telemetry file path (tests / tooling). ``None`` resets it."""
    global _override_path
    _override_path = Path(path) if path is not None else None


def telemetry_path() -> Path:
    """Resolve the append-only JSONL destination."""
    if _override_path is not None:
        return _override_path
    env_path = os.getenv("JQUEST_TELEMETRY_PATH")
    if env_path:
        return Path(env_path)
    return _DEFAULT_TELEMETRY_PATH


def _write(record: dict[str, Any]) -> None:
    """Append one JSON line. Filesystem failures are swallowed; nothing else is."""
    line = json.dumps(record, ensure_ascii=False)
    path = telemetry_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
    except OSError:
        # Telemetry must never be able to fail an application run.
        return


# ── Run / stage context ──────────────────────────────────────────────────────


def set_run_context(run_id: str | None) -> None:
    """Install the canonical run identity for the current context."""
    _run_id.set(run_id or None)


def current_run_id() -> str | None:
    return _run_id.get()


def current_stage() -> dict[str, Any] | None:
    """Return ``{"stage": ..., "step_index": ...}`` for the active stage."""
    return _stage.get()


def reset_telemetry_context() -> None:
    """Clear all telemetry context. For tests and process boundaries."""
    _run_id.set(None)
    _stage.set(None)
    _stage_state.set(None)
    _attempt_meta.set(None)


@contextmanager
def attempt_context(
    *, chain_index: int | None = None, condensed: bool = False
) -> Iterator[None]:
    """Decorate the concrete attempts made by a composite client.

    Set by ``FallbackClient`` / ``_WritingFallbackClient`` around each inner
    client call so a provider attempt can report its position in the chain and
    whether the prompt was shortened for that provider.
    """
    token = _attempt_meta.set({"chain_index": chain_index, "condensed": condensed})
    try:
        yield
    finally:
        _attempt_meta.reset(token)


def get_last_successful_attempt() -> int | None:
    """Attempt number of the last transport-successful attempt in this stage."""
    state = _stage_state.get()
    if state is None:
        return None
    return state.get("last_success")


def _identity(provider: str | None, model: str | None) -> str | None:
    if not provider and not model:
        return None
    return f"{provider or '?'}/{model or '?'}"


def _identity_provider(identity: str | None) -> str:
    """Provider portion of a ``provider/model`` identity string."""
    return (identity or "").split("/", 1)[0]


def emit_attempt(
    *,
    client_class: str,
    success: bool,
    requested_provider: str | None = None,
    requested_model: str | None = None,
    served_provider: str | None = None,
    served_model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    latency_ms: int | None = None,
    finish_reason: str | None = None,
    error_type: str | None = None,
    transport_retries: int | None = None,
    reported_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Append one ``llm_attempt`` event and return the emitted record.

    ``attempt``, ``stage``, ``step_index``, ``run_id``, ``chain_index``,
    ``condensed`` and the ``fallback_from``/``fallback_to`` pair are derived
    from the active context so composites and clients stay unaware of them.

    Fallback relationships are derived from the previous attempt emitted in
    the same stage, which means an internal Gemini model walk and a composite
    chain entry are represented identically and accurately.
    """
    state = _stage_state.get()
    stage_info = _stage.get() or {}
    meta = _attempt_meta.get() or {}

    attempt_number: int | None = None
    fallback_from: str | None = None
    fallback_to: str | None = None

    if state is not None:
        state["count"] = int(state.get("count", 0)) + 1
        attempt_number = state["count"]
        identity = _identity(
            served_provider or requested_provider, served_model or requested_model
        )
        previous_identity = state.get("last_identity")
        # A fallback edge requires a real identity CHANGE. A deliberate second
        # call on the same route (for example the cover-letter prune pass) is not
        # a fallback and must not be reported as one.
        if (
            attempt_number > 1
            and previous_identity
            and identity
            and identity != previous_identity
        ):
            fallback_from = previous_identity
            fallback_to = identity
            state["fallback_seen"] = True
            # B.1.5: remember whether the provider itself changed, so the stage
            # result can label model-level vs provider-level fallback truthfully.
            if _identity_provider(previous_identity) != _identity_provider(identity):
                state["provider_changed"] = True
        state["last_identity"] = identity
        state["last_attempt"] = attempt_number
        if success:
            state["last_success"] = attempt_number

    record: dict[str, Any] = {
        "event_type": EVENT_ATTEMPT,
        "ts": _now_iso(),
        "run_id": _run_id.get(),
        "stage": stage_info.get("stage"),
        "step_index": stage_info.get("step_index"),
        "attempt": attempt_number,
        "client_class": _safe_scalar(client_class),
        "requested_provider": _safe_scalar(requested_provider),
        "requested_model": _safe_scalar(requested_model),
        "served_provider": _safe_scalar(served_provider),
        "served_model": _safe_scalar(served_model),
        "chain_index": _as_int(meta.get("chain_index")),
        "condensed": bool(meta.get("condensed", False)),
        "input_tokens": _as_int(input_tokens),
        "output_tokens": _as_int(output_tokens),
        "cached_tokens": _as_int(cached_tokens),
        "reasoning_tokens": _as_int(reasoning_tokens),
        "latency_ms": _as_int(latency_ms),
        "finish_reason": _safe_scalar(finish_reason),
        "success": bool(success),
        "error_type": _safe_scalar(error_type),
        "fallback_from": fallback_from,
        "fallback_to": fallback_to,
        "transport_retries": _as_int(transport_retries),
        "reported_cost_usd": _safe_scalar(reported_cost_usd),
    }
    _write(record)
    return record


def emit_stage_result(
    *,
    stage: str | None,
    success: bool,
    step_index: int | None = None,
    selected_attempt: int | None = None,
    structured_parse_success: bool | None = None,
    degradation: str | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    """Append one ``stage_result`` event and return the emitted record.

    ``structured_parse_success`` is tri-state on purpose: ``True``/``False``
    where a structured parser exists, ``None`` for free-form prose stages where
    no structured parse happens at all.
    """
    record: dict[str, Any] = {
        "event_type": EVENT_STAGE_RESULT,
        "ts": _now_iso(),
        "run_id": _run_id.get(),
        "stage": _safe_scalar(stage),
        "step_index": _as_int(step_index),
        "success": bool(success),
        "selected_attempt": _as_int(selected_attempt),
        "structured_parse_success": (
            None if structured_parse_success is None else bool(structured_parse_success)
        ),
        "degradation": _safe_scalar(degradation),
        "error_type": _safe_scalar(error_type),
    }
    _write(record)
    return record


class StageHandle:
    """Mutable outcome handle yielded by :func:`stage_context`."""

    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    def set_parse_result(self, value: bool | None) -> None:
        """Record whether the stage's structured parse succeeded."""
        self._state["parse_result"] = None if value is None else bool(value)

    def set_degradation(self, value: str | None) -> None:
        """Record an observable degradation string for this stage."""
        self._state["degradation"] = value

    def set_success(self, value: bool) -> None:
        """Override the stage-level success flag (defaults to "no exception")."""
        self._state["success"] = bool(value)

    @property
    def attempts(self) -> int:
        return int(self._state.get("count", 0))

    @property
    def selected_attempt(self) -> int | None:
        return self._state.get("last_attempt")


@contextmanager
def stage_context(stage: str, step_index: int | None = None) -> Iterator[StageHandle]:
    """Scope the telemetry identity of one logical pipeline stage.

    Exactly one ``stage_result`` is emitted on exit, except when the stage
    never reached an LLM provider attempt and did not fail (a skipped,
    non-LLM path contributes no LLM telemetry at all). An exception is
    recorded and then re-raised unchanged, so control flow is untouched.
    """
    state: dict[str, Any] = {
        "stage": stage,
        "step_index": step_index,
        "count": 0,
        "last_identity": None,
        "last_attempt": None,
        "last_success": None,
        "parse_result": None,
        "degradation": None,
        "provider_changed": False,
        "fallback_seen": False,
        "success": None,
    }
    stage_token = _stage.set({"stage": stage, "step_index": step_index})
    state_token = _stage_state.set(state)
    error_type: str | None = None
    try:
        yield StageHandle(state)
    except BaseException as exc:  # re-raised unchanged below
        error_type = type(exc).__name__
        raise
    finally:
        attempts = int(state.get("count", 0))
        try:
            no_llm_path = attempts == 0 and error_type is None
            if not no_llm_path:
                success = state.get("success")
                if success is None:
                    success = error_type is None
                degradation = state.get("degradation")
                if degradation is None and state.get("fallback_seen"):
                    # B.1.5: distinguish a real provider change from a
                    # same-provider model change. Calling a same-provider model
                    # walk a "provider fallback" was misleading.
                    degradation = (
                        "provider_fallback_used"
                        if state.get("provider_changed")
                        else "model_fallback_used"
                    )
                emit_stage_result(
                    stage=stage,
                    step_index=step_index,
                    success=bool(success),
                    selected_attempt=state.get("last_attempt"),
                    structured_parse_success=state.get("parse_result"),
                    degradation=degradation,
                    error_type=error_type,
                )
        finally:
            _stage_state.reset(state_token)
            _stage.reset(stage_token)


class AttemptProbe:
    """One concrete provider/model attempt for a single ``generate()`` call.

    Providers that perform exactly one provider/model attempt per call (the
    HTTP clients and Anthropic) wrap their implementation in this probe. When
    the implementation raises, the probe records the exception class only and
    the original exception propagates unchanged.
    """

    def __init__(
        self,
        *,
        client_class: str,
        requested_provider: str | None = None,
        requested_model: str | None = None,
        served_provider: str | None = None,
    ) -> None:
        self._client_class = client_class
        self._requested_provider = requested_provider
        self._requested_model = requested_model
        self._served_provider = served_provider
        self._started = time.perf_counter()
        self._usage: dict[str, Any] = {}
        self._finish_reason: str | None = None
        self._served_model: str | None = None
        self._cost: float | None = None
        self._emitted = False
        # Number of retries already performed inside this attempt. Set by the
        # provider retry loop; 0 means the first try.
        self.transport_retries: int | None = 0

    def set_response(
        self,
        *,
        usage: dict[str, Any] | None = None,
        finish_reason: str | None = None,
        served_model: str | None = None,
        reported_cost_usd: float | None = None,
    ) -> None:
        """Attach metadata the provider response already contained."""
        if usage:
            self._usage = dict(usage)
        self._finish_reason = finish_reason
        self._served_model = served_model
        self._cost = reported_cost_usd

    def _emit(self, *, success: bool, error_type: str | None) -> None:
        if self._emitted:
            return
        self._emitted = True
        emit_attempt(
            client_class=self._client_class,
            success=success,
            requested_provider=self._requested_provider,
            requested_model=self._requested_model,
            served_provider=self._served_provider,
            served_model=self._served_model,
            latency_ms=elapsed_ms(self._started),
            finish_reason=self._finish_reason,
            error_type=error_type,
            transport_retries=self.transport_retries,
            reported_cost_usd=self._cost,
            **self._usage,
        )

    def succeed(self) -> None:
        """Emit the successful attempt."""
        self._emit(success=True, error_type=None)

    def fail(self, error_type: str | None) -> None:
        """Emit the failed attempt. The caller re-raises the original error."""
        self._emit(success=False, error_type=error_type or None)
