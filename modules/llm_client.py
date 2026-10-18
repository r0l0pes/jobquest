"""LLM client abstraction layer.

Provides a pluggable interface for LLM providers.
Supports: Gemini (free tier), OpenCode Go (Kimi/GLM/DeepSeek V4/Qwen),
Groq, SambaNova, DeepSeek, OpenRouter, Anthropic.
"""

import os
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from modules import llm_telemetry

MAX_RETRIES = 5
RETRY_BASE_DELAY = 10  # seconds (longer for rate limits)

# Default provider (can override in .env with LLM_PROVIDER)
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# Available Gemini models, verified against Google's August 2026 lifecycle docs.
# Source: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions
GEMINI_MODELS = {
    "gemini-2.5-pro": "models/gemini-2.5-pro",               # Legacy, strong writing
    "gemini-3-flash": "models/gemini-3-flash-preview",       # Preview
    "gemini-3.7-flash": "models/gemini-3.7-flash",           # Current fast model
    "gemini-3.1-flash-lite": "models/gemini-3.1-flash-lite", # Current lightweight model
    "gemini-2.5-flash": "models/gemini-2.5-flash",           # Legacy fallback
    "gemini-2.5-flash-lite": "models/gemini-2.5-flash-lite", # Retires October 2026
}

# Fallback order when a Gemini model is unavailable or rate limited.
MODEL_FALLBACK_ORDER = [
    "models/gemini-3.7-flash",
    "models/gemini-3-flash-preview",
    "models/gemini-3.1-flash-lite",
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
]

DEFAULT_MODEL = "gemini-3.1-flash-lite"


# ── Gate B.1 telemetry: response-metadata extraction ─────────────────────────
# These helpers read only fields the provider response already contains. They
# never alter the request, the retry policy, the fallback order or the returned
# content. Attribute access is defensive because installed SDK versions may
# differ; absent metadata stays None and is never guessed at.


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _as_token_count(value):
    """Coerce a provider token count. Booleans and non-numbers are not counts.

    Non-finite floats are rejected rather than converted: ``int(float('nan'))``
    raises ValueError and ``int(float('inf'))`` raises OverflowError, and these
    helpers run inside each provider's retry ``try`` block. A provider body that
    carries a non-standard JSON ``NaN``/``Infinity`` usage field must never be
    able to raise here, because that would be re-interpreted as a provider
    failure and change retries/fallback routing. Mirrors ``llm_telemetry._as_int``.
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


def _gemini_response_metadata(response):
    """Return (usage, finish_reason, served_model) from a Gemini response.

    ``served_model`` prefers the API-reported ``model_version`` and falls back to
    the model id that was addressed. ``finish_reason`` is normalised to the bare
    enum name (e.g. ``"STOP"``) for telemetry only; the caller's existing
    truncation check still inspects the raw value.
    """
    usage = {}
    meta = getattr(response, "usage_metadata", None)
    if meta is not None:
        usage = {
            "input_tokens": _as_token_count(getattr(meta, "prompt_token_count", None)),
            "output_tokens": _as_token_count(
                getattr(meta, "candidates_token_count", None)
            ),
            "cached_tokens": _as_token_count(
                getattr(meta, "cached_content_token_count", None)
            ),
            "reasoning_tokens": _as_token_count(
                getattr(meta, "thoughts_token_count", None)
            ),
        }

    finish_reason = None
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        raw_reason = getattr(candidates[0], "finish_reason", None)
        if raw_reason is not None:
            text = str(raw_reason)
            finish_reason = text.split(".")[-1] if "." in text else text

    raw_version = getattr(response, "model_version", None)
    served_model = str(raw_version) if raw_version else None

    return usage, finish_reason, served_model


def _openai_compatible_response_metadata(data):
    """Return (usage, finish_reason, served_model, reported_cost_usd).

    Covers the OpenAI-compatible bodies returned by Groq, SambaNova, DeepSeek,
    OpenRouter and OpenCode. Providers differ in which usage fields they return,
    so each field is optional and absent fields stay ``None``. A genuine zero
    (for example zero cache hits) is preserved rather than treated as missing.
    """
    body = data if isinstance(data, dict) else {}
    raw_usage = body.get("usage")
    usage = raw_usage if isinstance(raw_usage, dict) else {}

    prompt_details = usage.get("prompt_tokens_details")
    completion_details = usage.get("completion_tokens_details")

    cached_tokens = _first_present(
        prompt_details.get("cached_tokens")
        if isinstance(prompt_details, dict)
        else None,
        usage.get("prompt_cache_hit_tokens"),
    )
    reasoning_tokens = _first_present(
        completion_details.get("reasoning_tokens")
        if isinstance(completion_details, dict)
        else None,
        usage.get("reasoning_tokens"),
    )

    extracted_usage = {
        "input_tokens": _as_token_count(
            _first_present(usage.get("prompt_tokens"), usage.get("input_tokens"))
        ),
        "output_tokens": _as_token_count(
            _first_present(usage.get("completion_tokens"), usage.get("output_tokens"))
        ),
        "cached_tokens": _as_token_count(cached_tokens),
        "reasoning_tokens": _as_token_count(reasoning_tokens),
    }

    finish_reason = None
    choices = body.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        raw_reason = choices[0].get("finish_reason")
        if raw_reason is not None:
            finish_reason = str(raw_reason)

    raw_model = body.get("model")
    served_model = str(raw_model) if raw_model else None

    # Only OpenRouter-style bodies carry a cost, and only when the request opted
    # in. Gate B.1 does not change the request shape, so this is usually None.
    reported_cost = usage.get("cost")
    if isinstance(reported_cost, bool) or not isinstance(reported_cost, (int, float)):
        reported_cost = None

    return extracted_usage, finish_reason, served_model, reported_cost


def _anthropic_response_metadata(data):
    """Return (usage, stop_reason, served_model, reported_cost_usd)."""
    body = data if isinstance(data, dict) else {}
    raw_usage = body.get("usage")
    usage = raw_usage if isinstance(raw_usage, dict) else {}

    extracted_usage = {
        "input_tokens": _as_token_count(usage.get("input_tokens")),
        "output_tokens": _as_token_count(usage.get("output_tokens")),
        "cached_tokens": _as_token_count(usage.get("cache_read_input_tokens")),
        "reasoning_tokens": None,
    }

    raw_stop = body.get("stop_reason")
    raw_model = body.get("model")
    return (
        extracted_usage,
        str(raw_stop) if raw_stop else None,
        str(raw_model) if raw_model else None,
        None,
    )


class LLMClient(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        **kwargs,
    ) -> str:
        """Generate text from system + user prompts."""
        ...

    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        ...


class _ObservedClient(LLMClient):
    """LLM client that records exactly one provider/model attempt per call.

    Subclasses rename their implementation to ``_generate_impl``, accept a
    ``probe`` argument, and declare the provider identity used for telemetry.
    ``generate`` times the call, emits the attempt (success or failure) and
    re-raises any exception unchanged, so retry/fallback behaviour is untouched.

    Providers whose single ``generate`` call can traverse several models (Gemini)
    do not use this base and emit one attempt per concrete model instead.
    """

    TELEMETRY_PROVIDER: str | None = None
    TELEMETRY_SERVED_PROVIDER: str | None = None
    TELEMETRY_MODEL_ATTR = "_model_id"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        **kwargs,
    ) -> str:
        probe = llm_telemetry.AttemptProbe(
            client_class=type(self).__name__,
            requested_provider=self.TELEMETRY_PROVIDER,
            requested_model=getattr(self, self.TELEMETRY_MODEL_ATTR, None),
            served_provider=self.TELEMETRY_SERVED_PROVIDER,
        )
        try:
            content = self._generate_impl(
                system_prompt, user_prompt, temperature, probe, **kwargs
            )
        except Exception as exc:
            probe.fail(type(exc).__name__)
            raise
        probe.succeed()
        return content

    def _generate_impl(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        probe,
        **kwargs,
    ) -> str:
        raise NotImplementedError


class GeminiClient(LLMClient):
    """Google Gemini API client via google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        model_fallback: bool = False,
    ):
        """Create the client.

        Args:
            model_fallback: opt in to the internal ``MODEL_FALLBACK_ORDER`` walk.
                Defaults to **off** (B.1.5): a client configured for one model
                performs exactly one model route, so ``fallback=False`` at the
                factory level is truthful. Gemini is no longer an active
                production gateway.
        """
        from google import genai  # pyright: ignore[reportMissingImports, reportAttributeAccessIssue]

        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Add it to your .env file.\n"
                "Get a free key at https://aistudio.google.com/apikey"
            )
        self._client = genai.Client(api_key=self._api_key)
        self._model_fallback = bool(model_fallback)

        # Resolve model alias to full path
        if model in GEMINI_MODELS:
            self._model_id = GEMINI_MODELS[model]
        elif model.startswith("models/"):
            self._model_id = model
        else:
            self._model_id = f"models/{model}"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        **kwargs,
    ) -> str:
        from google.genai import types  # pyright: ignore[reportMissingImports]
        import re

        # Build list of models to try: current model first, then (only when
        # explicitly opted in) the legacy Gemini fallback order. B.1.5: the
        # hidden walk is OFF by default so a configured model is honoured.
        models_to_try = [self._model_id]
        if self._model_fallback:
            for fallback in MODEL_FALLBACK_ORDER:
                if fallback not in models_to_try:
                    models_to_try.append(fallback)

        last_error = None
        for model_id in models_to_try:
            # Primary model gets more retries, fallbacks get 2 each
            retries_for_model = 2 if model_id == self._model_id else 1

            # Gate B.1 telemetry: this loop body is one concrete provider/model
            # attempt, including its internal retries. Metadata is captured only
            # when the SDK response exposes it, and nothing here changes which
            # models are tried, in what order, or on which errors.
            attempt_started = time.perf_counter()
            model_error: Exception | None = None
            model_usage: dict = {}
            model_finish_reason = None
            model_served_model = None
            model_retries = 0

            for attempt in range(retries_for_model):
                try:
                    model_retries = attempt
                    # Model-dependent output token budget.
                    # Pro models support 64K, lower avoids slow generation.
                    # Flash/Lite have ~8K hard limits.
                    if "2.5-pro" in model_id or "2.5-flash-pro" in model_id:
                        max_tokens = 32768
                    elif "flash" in model_id or "lite" in model_id:
                        max_tokens = 8192
                    else:
                        max_tokens = 16384
                    
                    response = self._client.models.generate_content(
                        model=model_id,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=temperature,
                            max_output_tokens=max_tokens,
                        ),
                    )
                    (
                        model_usage,
                        model_finish_reason,
                        model_served_model,
                    ) = _gemini_response_metadata(response)
                    # Check finish reason for truncation diagnostics
                    if response.candidates:
                        finish_reason = getattr(response.candidates[0], 'finish_reason', None)
                        if finish_reason and str(finish_reason) not in ('STOP', 'FinishReason.STOP', '1'):
                            output_len = len(response.text or '')
                            print(f"  ⚠️  Gemini finish_reason: {finish_reason} (model: {model_id.split('/')[-1]}, output: {output_len} chars)", flush=True)
                            # Treat MAX_TOKENS as a model failure so the fallback chain
                            # automatically tries the next model/provider.
                            # MAX_TOKENS means output was truncated — always bad for us.
                            raise RuntimeError(
                                f"Gemini {model_id.split('/')[-1]} hit {finish_reason} "
                                f"at {output_len} chars — truncated output, falling back"
                            )
                    if model_id != self._model_id:
                        print(f"  ✓ Success with fallback: {model_id.split('/')[-1]}", flush=True)
                    llm_telemetry.emit_attempt(
                        client_class=type(self).__name__,
                        success=True,
                        requested_provider="gemini",
                        requested_model=self._model_id,
                        served_provider="gemini",
                        served_model=model_served_model or model_id,
                        latency_ms=llm_telemetry.elapsed_ms(attempt_started),
                        finish_reason=model_finish_reason,
                        transport_retries=model_retries,
                        **model_usage,
                    )
                    return response.text
                except Exception as e:
                    last_error = e
                    model_error = e
                    error_str = str(e)

                    is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
                    is_daily_limit = "PerDay" in error_str

                    # Daily limit hit → skip ALL Gemini models (they share the same quota)
                    if is_daily_limit:
                        print(f"  Daily limit for {model_id.split('/')[-1]} — skipping remaining Gemini models", flush=True)
                        # Set last_error so it propagates to FallbackClient
                        last_error = e
                        models_to_try = models_to_try[:1]  # Skip remaining models
                        break

                    # Minute rate limit → short wait then retry or next model
                    if is_rate_limit:
                        if attempt < retries_for_model - 1:
                            match = re.search(r"retry in (\d+(?:\.\d+)?)", error_str.lower())
                            delay = min(float(match.group(1)) + 2, 35) if match else 20
                            print(f"  Rate limit ({model_id.split('/')[-1]}). Waiting {delay:.0f}s...", flush=True)
                            time.sleep(delay)
                    elif attempt < retries_for_model - 1:
                        time.sleep(RETRY_BASE_DELAY * (2**attempt))

            # After exhausting retries for this model, try next
            llm_telemetry.emit_attempt(
                client_class=type(self).__name__,
                success=False,
                requested_provider="gemini",
                requested_model=self._model_id,
                served_provider="gemini",
                served_model=model_served_model or model_id,
                latency_ms=llm_telemetry.elapsed_ms(attempt_started),
                finish_reason=model_finish_reason,
                error_type=type(model_error).__name__ if model_error else None,
                transport_retries=model_retries,
                **model_usage,
            )

        raise RuntimeError(
            f"All Gemini models exhausted. Last error: {last_error}"
        )

    def model_name(self) -> str:
        return self._model_id


class GroqClient(_ObservedClient):
    """Groq API client - very fast inference, generous free tier."""

    TELEMETRY_PROVIDER = "groq"
    TELEMETRY_SERVED_PROVIDER = "groq"

    MODELS = {
        "llama-3.3-70b": "llama-3.3-70b-versatile",
        "llama-3.1-8b": "llama-3.1-8b-instant",
        "deepseek-r1-70b": "deepseek-r1-distill-llama-70b",
        "qwen-2.5-32b": "qwen-qwq-32b",
    }
    DEFAULT_MODEL = "llama-3.3-70b"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("GROQ_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Add it to your .env file.\n"
                "Get a free key at https://console.groq.com"
            )
        model = model or self.DEFAULT_MODEL
        self._model_id = self.MODELS.get(model, model)

    def _generate_impl(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        probe,
        **kwargs,
    ) -> str:
        import httpx  # pyright: ignore[reportMissingImports]

        # Groq models support max 8192 output tokens
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
                probe.transport_retries = attempt
                response = httpx.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model_id,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": 8192,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                usage, finish_reason, served_model, cost = (
                    _openai_compatible_response_metadata(data)
                )
                probe.set_response(
                    usage=usage,
                    finish_reason=finish_reason,
                    served_model=served_model,
                    reported_cost_usd=cost,
                )
                return data["choices"][0]["message"]["content"]
            except httpx.TimeoutException as e:
                print(f"  Timeout (Groq, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"Groq request timed out after {MAX_RETRIES} attempts")
            except httpx.RequestError as e:
                print(f"  Network error (Groq, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"Groq network error: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 429:
                    raise
                if attempt >= MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"  Rate limit (Groq). Waiting {delay}s...", flush=True)
                time.sleep(delay)
            except (KeyError, IndexError) as e:
                # Unexpected response structure
                raise RuntimeError(f"Groq returned unexpected response format: {e}")

        raise RuntimeError(f"Groq request failed after {MAX_RETRIES} attempts")

    def model_name(self) -> str:
        return f"groq/{self._model_id}"


class SambaNovaClient(_ObservedClient):
    """SambaNova Cloud API - free access to large models."""

    TELEMETRY_PROVIDER = "sambanova"
    TELEMETRY_SERVED_PROVIDER = "sambanova"

    MODELS = {
        "llama-3.1-405b": "Meta-Llama-3.1-405B-Instruct",
        "llama-3.3-70b": "Meta-Llama-3.3-70B-Instruct",
        "deepseek-v3": "DeepSeek-V3-0324",
        "qwen-2.5-72b": "Qwen2.5-72B-Instruct",
    }
    DEFAULT_MODEL = "llama-3.3-70b"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("SAMBANOVA_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "SAMBANOVA_API_KEY not set. Add it to your .env file.\n"
                "Get a free key at https://cloud.sambanova.ai"
            )
        model = model or self.DEFAULT_MODEL
        self._model_id = self.MODELS.get(model, model)

    def _generate_impl(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        probe,
        **kwargs,
    ) -> str:
        import httpx  # pyright: ignore[reportMissingImports]

        # SambaNova can be slower, use longer read timeout
        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
                probe.transport_retries = attempt
                response = httpx.post(
                    "https://api.sambanova.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model_id,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": 8192,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                usage, finish_reason, served_model, cost = (
                    _openai_compatible_response_metadata(data)
                )
                probe.set_response(
                    usage=usage,
                    finish_reason=finish_reason,
                    served_model=served_model,
                    reported_cost_usd=cost,
                )
                return data["choices"][0]["message"]["content"]
            except httpx.TimeoutException as e:
                print(f"  Timeout (SambaNova, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"SambaNova request timed out after {MAX_RETRIES} attempts")
            except httpx.RequestError as e:
                print(f"  Network error (SambaNova, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"SambaNova network error: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 429:
                    raise
                if attempt >= MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"  Rate limit (SambaNova). Waiting {delay}s...", flush=True)
                time.sleep(delay)
            except (KeyError, IndexError) as e:
                # Unexpected response structure
                raise RuntimeError(f"SambaNova returned unexpected response format: {e}")

        raise RuntimeError(f"SambaNova request failed after {MAX_RETRIES} attempts")

    def model_name(self) -> str:
        return f"sambanova/{self._model_id}"


class DeepSeekClient(_ObservedClient):
    """DeepSeek API client — api.deepseek.com (OpenAI-compatible).

    Model deepseek-chat = DeepSeek V3.2 (current stable).
    DeepSeek V4 will be accessible via this same endpoint when released.
    Supports prompt caching: repeated system prompts cost $0.028/1M (vs $0.28/1M cold).
    """

    DEFAULT_MODEL = "deepseek-chat"

    TELEMETRY_PROVIDER = "deepseek"
    TELEMETRY_SERVED_PROVIDER = "deepseek"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY not set. Add it to your .env file.\n"
                "Get a key at https://platform.deepseek.com/api_keys"
            )
        self._model_id = model or self.DEFAULT_MODEL

    def _generate_impl(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        probe,
        **kwargs,
    ) -> str:
        import httpx  # pyright: ignore[reportMissingImports]

        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
                probe.transport_retries = attempt
                response = httpx.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model_id,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": 8192,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                usage, finish_reason, served_model, cost = (
                    _openai_compatible_response_metadata(data)
                )
                probe.set_response(
                    usage=usage,
                    finish_reason=finish_reason,
                    served_model=served_model,
                    reported_cost_usd=cost,
                )
                return data["choices"][0]["message"]["content"]
            except httpx.TimeoutException as e:
                print(f"  Timeout (DeepSeek, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"DeepSeek request timed out after {MAX_RETRIES} attempts")
            except httpx.RequestError as e:
                print(f"  Network error (DeepSeek, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"DeepSeek network error: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 429:
                    raise
                if attempt >= MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"  Rate limit (DeepSeek). Waiting {delay}s...", flush=True)
                time.sleep(delay)
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"DeepSeek returned unexpected response format: {e}")

        raise RuntimeError(f"DeepSeek request failed after {MAX_RETRIES} attempts")

    def model_name(self) -> str:
        return f"deepseek/{self._model_id}"


class OpenRouterClient(_ObservedClient):
    """OpenRouter API client — openrouter.ai.

    Default model: Qwen3.5-397B-A17B ($0.15/$1.00 per 1M tokens, IFEval 92.6%).
    """

    TELEMETRY_PROVIDER = "openrouter"
    # The upstream provider that actually served a request is opaque behind
    # OpenRouter routing, so it is deliberately reported as unknown.
    TELEMETRY_SERVED_PROVIDER = None

    # Output cap for a single OpenRouter completion. Bounded so a mis-configured
    # model cannot run away with output-token spend.
    _max_tokens: int = 8192

    DEFAULT_MODEL = "qwen/qwen3.5-397b-a17b"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ):
        """Create the client.

        Args:
            model: explicit OpenRouter model slug. Never a router alias such as
                ``openrouter/auto``; B.1.5 forbids the Auto Router in the
                production path.
            reasoning_effort: optional ``low``/``medium``/``high`` (or ``off``).
                Bounded reasoning keeps output-token spend predictable and stops
                reasoning-only replies with empty ``content``. Defaults to the
                ``OPENROUTER_REASONING_EFFORT`` env var, then ``low``.
        """
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. Add it to your .env file.\n"
                "Get a key at https://openrouter.ai/keys"
            )
        if model and ":" in model:
            raise ValueError(
                f"OpenRouter model '{model}' looks like a routing variant. "
                "B.1.5 forbids Auto Router / variant routing in the production path."
            )
        self._model_id = model or self.DEFAULT_MODEL
        self._reasoning_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else os.getenv("OPENROUTER_REASONING_EFFORT", "low")
        )

    def _generate_impl(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        probe,
        **kwargs,
    ) -> str:
        import httpx  # pyright: ignore[reportMissingImports]

        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
                probe.transport_retries = attempt
                payload = {
                    "model": self._model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": self._max_tokens,
                }
                if self._reasoning_effort:
                    disabled = self._reasoning_effort in ("off", "none", "disabled")
                    payload["reasoning"] = (
                        {"enabled": False}
                        if disabled
                        else {"effort": self._reasoning_effort}
                    )
                response = httpx.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                usage, finish_reason, served_model, cost = (
                    _openai_compatible_response_metadata(data)
                )
                probe.set_response(
                    usage=usage,
                    finish_reason=finish_reason,
                    served_model=served_model,
                    reported_cost_usd=cost,
                )
                content = data["choices"][0]["message"].get("content")
                if not content:
                    # Reasoning-only or empty reply. Raising keeps the stage
                    # honest instead of returning None into a parser.
                    raise RuntimeError(
                        f"OpenRouter/{self._model_id} returned empty content "
                        f"(finish_reason={finish_reason})"
                    )
                return content
            except httpx.TimeoutException as e:
                print(f"  Timeout (OpenRouter, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"OpenRouter request timed out after {MAX_RETRIES} attempts")
            except httpx.RequestError as e:
                print(f"  Network error (OpenRouter, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"OpenRouter network error: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 429:
                    raise
                if attempt >= MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"  Rate limit (OpenRouter). Waiting {delay}s...", flush=True)
                time.sleep(delay)
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"OpenRouter returned unexpected response format: {e}")

        raise RuntimeError(f"OpenRouter request failed after {MAX_RETRIES} attempts")

    def model_name(self) -> str:
        return f"openrouter/{self._model_id}"


class OpenCodeClient(_ObservedClient):
    """OpenCode Go client — flat-rate open-source models via OpenAI-compatible API.

    Base URL: https://opencode.ai/zen/go/v1
    Models: kimi-k2.6, deepseek-v4-pro, glm-5, qwen3.6-plus, etc.
    Some models return reasoning_content in addition to content.
    """

    TELEMETRY_PROVIDER = "opencode"
    TELEMETRY_SERVED_PROVIDER = "opencode"

    BASE_URL = "https://opencode.ai/zen/go/v1"
    DEFAULT_MODEL = "kimi-k2.6"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("OPENCODE_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OPENCODE_API_KEY not set. Add it to your .env file.\n"
                "Get a key at https://opencode.ai"
            )
        self._model_id = model or self.DEFAULT_MODEL

    def _generate_impl(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        probe,
        **kwargs,
    ) -> str:
        import httpx  # pyright: ignore[reportMissingImports]

        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
                probe.transport_retries = attempt
                response = httpx.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model_id,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": 8192,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                usage, finish_reason, served_model, cost = (
                    _openai_compatible_response_metadata(data)
                )
                probe.set_response(
                    usage=usage,
                    finish_reason=finish_reason,
                    served_model=served_model,
                    reported_cost_usd=cost,
                )
                content = data["choices"][0]["message"].get("content", "")
                if not content:
                    # Some reasoning models return empty content on short prompts
                    # Retry with higher max_tokens if content is empty
                    if attempt < MAX_RETRIES - 1:
                        continue
                return content
            except httpx.TimeoutException as e:
                print(f"  Timeout (OpenCode/{self._model_id}, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"OpenCode/{self._model_id} timed out after {MAX_RETRIES} attempts")
            except httpx.RequestError as e:
                print(f"  Network error (OpenCode/{self._model_id}, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"OpenCode/{self._model_id} network error: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 429:
                    raise
                if attempt >= MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"  Rate limit (OpenCode/{self._model_id}). Waiting {delay}s...", flush=True)
                time.sleep(delay)
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"OpenCode/{self._model_id} unexpected response: {e}")

        raise RuntimeError(f"OpenCode/{self._model_id} failed after {MAX_RETRIES} attempts (empty responses)")

    def model_name(self) -> str:
        return f"opencode/{self._model_id}"


class AnthropicClient(_ObservedClient):
    """Anthropic API client — Claude Haiku for writing fallback.

    Default model: claude-haiku-4-5-20251001 ($0.80/$4.00 per 1M tokens).
    Used only as last-resort fallback when OpenCode Go is exhausted.
    """

    TELEMETRY_PROVIDER = "anthropic"
    TELEMETRY_SERVED_PROVIDER = "anthropic"

    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file.\n"
                "Get a key at https://console.anthropic.com"
            )
        self._model_id = model or self.DEFAULT_MODEL

    def _generate_impl(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        probe,
        **kwargs,
    ) -> str:
        import httpx  # pyright: ignore[reportMissingImports]

        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
                probe.transport_retries = attempt
                response = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model_id,
                        "system": system_prompt,
                        "messages": [
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": 8192,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                usage, stop_reason, served_model, cost = _anthropic_response_metadata(
                    data
                )
                probe.set_response(
                    usage=usage,
                    finish_reason=stop_reason,
                    served_model=served_model,
                    reported_cost_usd=cost,
                )
                return data["content"][0]["text"]
            except httpx.TimeoutException as e:
                print(f"  Timeout (Anthropic, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"Anthropic request timed out after {MAX_RETRIES} attempts")
            except httpx.RequestError as e:
                print(f"  Network error (Anthropic, attempt {attempt + 1}/{MAX_RETRIES}): {e}", flush=True)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
                else:
                    raise RuntimeError(f"Anthropic network error: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 429:
                    raise
                if attempt >= MAX_RETRIES - 1:
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"  Rate limit (Anthropic). Waiting {delay}s...", flush=True)
                time.sleep(delay)
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Anthropic returned unexpected response format: {e}")

        raise RuntimeError(f"Anthropic request failed after {MAX_RETRIES} attempts")

    def model_name(self) -> str:
        return f"anthropic/{self._model_id}"


# Legacy cross-provider broadcast order. B.1.5 removed the broadcast from the
# production path: routing is now explicit (see ``RoutedClient`` / ``STAGE_ROUTES``)
# and Gemini is no longer an active production gateway. The constant is kept only
# so legacy/importing code still resolves.
PROVIDER_FALLBACK_ORDER = ["openrouter"]

# Track which provider was actually used (for stats)
_last_used_provider = None


def get_last_used_provider() -> str | None:
    """Return the provider that was used in the last generate() call."""
    return _last_used_provider


class FallbackClient(LLMClient):
    """Client that automatically falls back across providers when rate limited."""

    def __init__(self, primary_provider: str = "gemini"):
        self._primary = primary_provider
        self._clients: dict[str, LLMClient | None] = {}
        self._available_providers: list[str] = []

        # Build ordered list: primary first, then others
        provider_order = [primary_provider] + [
            p for p in PROVIDER_FALLBACK_ORDER if p != primary_provider
        ]

        # Initialize clients for providers that have API keys configured
        for provider in provider_order:
            try:
                client = _create_single_client(provider)
                self._clients[provider] = client
                self._available_providers.append(provider)
            except ValueError:
                # API key not configured, skip this provider
                self._clients[provider] = None

        if not self._available_providers:
            raise ValueError(
                "No LLM providers configured. Add at least one API key to .env:\n"
                "  GEMINI_API_KEY (https://aistudio.google.com/apikey)\n"
                "  GROQ_API_KEY (https://console.groq.com)\n"
                "  SAMBANOVA_API_KEY (https://cloud.sambanova.ai)"
            )

        # Log available providers
        print(f"  LLM: Primary={primary_provider}, Fallback chain={self._available_providers}", flush=True)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        **kwargs,
    ) -> str:
        global _last_used_provider
        last_error = None

        for chain_index, provider in enumerate(self._available_providers):
            client = self._clients[provider]
            if client is None:
                continue

            try:
                # Gate B.1: decorate the concrete attempt made by this provider
                # client with its position in the cross-provider chain. This does
                # not affect which provider is tried or in what order.
                with llm_telemetry.attempt_context(chain_index=chain_index):
                    result = client.generate(system_prompt, user_prompt, temperature)
                _last_used_provider = provider
                return result
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Provider failures are safe to retry through the chain. This
                # includes quota/rate-limit, transient network, timeout, and
                # server errors. Authentication/configuration errors still fail
                # fast because another provider cannot repair them reliably.
                is_transient = any(x in error_str for x in [
                    "429", "rate", "quota", "exhausted", "limit",
                    "too many requests", "resource_exhausted", "timeout",
                    "timed out", "network", "503", "502", "500",
                    "temporarily unavailable",
                ])

                if is_transient:
                    print(f"  ⚠️  {provider} unavailable, trying next provider...", flush=True)
                    continue
                raise

        raise RuntimeError(
            f"All providers exhausted. Last error: {last_error}\n"
            f"Tried: {', '.join(self._available_providers)}"
        )

    def model_name(self) -> str:
        return f"fallback/{self._primary}"


# ── B.1.5: explicit per-stage routing ────────────────────────────────────────
# Production inference gateway: OpenRouter pay-as-you-go.
#
# Every stage declares ONE explicit primary route and AT MOST one explicit
# fallback route. Model slugs are explicit strings; the OpenRouter Auto Router is
# never used. Each stage is overridable with its own env prefix, e.g.
#   FIT_PROVIDER / FIT_MODEL / FIT_FALLBACK_PROVIDER / FIT_FALLBACK_MODEL
# Setting ``<PREFIX>_FALLBACK_MODEL=''`` disables the fallback for that stage.
#
# Gemini is deliberately absent: it is legacy, not the production runtime.
STAGE_ROUTES: dict[str, dict[str, str]] = {
    # fit: GLM scored the location hard-gate correctly on all 3 cases (3/3 PASS);
    # gpt-6-luna mis-judged Clickboat (offers "fully remote from France", Spain is
    # preferred) and flipped on InsiderOne. GLM needs reasoning enabled (low).
    "fit": {
        "provider": "openrouter",
        "model": "z-ai/glm-5.3-flash",
        "fallback_provider": "openrouter",
        "fallback_model": "qwen/qwen3.8-flash",
        "reasoning_effort": "low",
        "fallback_reasoning_effort": "off",
    },
    # jd: Qwen was the only candidate to honour the Evidence-line contract on
    # every case (3/3) with full STRONG/PARTIAL/INDIRECT/GAP discipline.
    "jd": {
        "provider": "openrouter",
        "model": "qwen/qwen3.8-flash",
        "fallback_provider": "openrouter",
        "fallback_model": "z-ai/glm-5.3-flash",
        "reasoning_effort": "off",
        "fallback_reasoning_effort": "low",
    },
    # tailor: all candidates passed the deterministic novel-claim gate with
    # near-identical grounded patches, so cost decides. gpt-6-luna is the
    # cheapest reliable option (~$0.0008/call vs ~$0.028 for Claude).
    "tailor": {
        "provider": "openrouter",
        "model": "openai/gpt-6-luna",
        "fallback_provider": "openrouter",
        "fallback_model": "deepseek/deepseek-v4.1-flash",
        "reasoning_effort": "off",
        "fallback_reasoning_effort": "off",
    },
    # reviewer: gpt-6-luna produced complete Part A + Part B with bounded output
    # on every case; deepseek-completion truncated at the eval cap.
    "reviewer": {
        "provider": "openrouter",
        "model": "openai/gpt-6-luna",
        "fallback_provider": "openrouter",
        "fallback_model": "deepseek/deepseek-v4.1-flash",
        "reasoning_effort": "off",
        "fallback_reasoning_effort": "off",
    },
    # ats: GLM returned a usable, fully-keyed report on 3/3 cases with sensible
    # coverage verdicts at the lowest cost.
    "ats": {
        "provider": "openrouter",
        "model": "z-ai/glm-5.3-flash",
        "fallback_provider": "openrouter",
        "fallback_model": "openai/gpt-6-luna",
        "reasoning_effort": "low",
        "fallback_reasoning_effort": "low",
    },
    # qa: deepseek matched Claude's length and evidence density at ~1/40 the cost,
    # with every numeric claim traceable to the resume.
    "qa": {
        "provider": "openrouter",
        "model": "deepseek/deepseek-v4.1-flash",
        "fallback_provider": "openrouter",
        "fallback_model": "openai/gpt-6-luna",
        "reasoning_effort": "off",
        "fallback_reasoning_effort": "off",
    },
}

# Bounded reasoning keeps output-token spend predictable and stops
# reasoning-only replies that arrive with empty ``content``. Each stage route
# may override its own (and its fallback's) setting; see ``STAGE_ROUTES``.
DEFAULT_REASONING_EFFORT = os.getenv("OPENROUTER_REASONING_EFFORT", "low")


class RoutedClient(LLMClient):
    """One explicit primary route plus at most one explicit fallback route.

    The only production routing primitive after B.1.5. It never walks a hidden
    model list and never broadcasts across more than the two configured routes.
    A configured stage therefore has a bounded worst case of two requests.
    """

    def __init__(
        self,
        stage: str,
        primary_provider: str,
        primary_model: str,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
        reasoning_effort: str | None = None,
        fallback_reasoning_effort: str | None = None,
    ):
        """

        Reasoning effort is per route: some models reject ``enabled: false`` with
        HTTP 400 (glm-5.3-flash, claude-sonnet-5.5) while others consume the whole
        output budget on reasoning unless it is disabled (qwen3.8-flash,
        deepseek-v4.1-flash). ``fallback_reasoning_effort`` defaults to
        ``reasoning_effort``.
        """
        self._stage = stage
        self._primary_id = f"{primary_provider}/{primary_model}"
        self._primary = _create_single_client(
            primary_provider, primary_model, reasoning_effort=reasoning_effort
        )
        self._fallback: LLMClient | None = None
        self._fallback_id: str | None = None
        if fallback_provider and fallback_model:
            self._fallback_id = f"{fallback_provider}/{fallback_model}"
            self._fallback = _create_single_client(
                fallback_provider,
                fallback_model,
                reasoning_effort=(
                    fallback_reasoning_effort
                    if fallback_reasoning_effort is not None
                    else reasoning_effort
                ),
            )

    @property
    def route_ids(self) -> list[str]:
        """Every provider/model this client can reach, primary first."""
        return [self._primary_id] + ([self._fallback_id] if self._fallback_id else [])

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        **kwargs,
    ) -> str:
        try:
            with llm_telemetry.attempt_context(chain_index=0):
                return self._primary.generate(
                    system_prompt, user_prompt, temperature, **kwargs
                )
        except Exception as primary_error:  # noqa: BLE001 - re-raised when no fallback
            if self._fallback is None:
                raise
            print(
                f"  ↳ {self._stage}: primary {self._primary_id} failed "
                f"({type(primary_error).__name__}), trying declared fallback "
                f"{self._fallback_id}",
                flush=True,
            )
            with llm_telemetry.attempt_context(chain_index=1):
                return self._fallback.generate(
                    system_prompt, user_prompt, temperature, **kwargs
                )

    def model_name(self) -> str:
        return f"{self._stage}/{self._primary_id}"


def _create_stage_client(stage: str, prefix: str) -> LLMClient:
    """Build the routed client for one stage from its own configuration."""
    defaults = STAGE_ROUTES[stage]
    provider = os.getenv(f"{prefix}_PROVIDER", defaults["provider"])
    model = os.getenv(f"{prefix}_MODEL", defaults["model"])
    fb_provider = os.getenv(
        f"{prefix}_FALLBACK_PROVIDER", defaults.get("fallback_provider", "")
    )
    fb_model = os.getenv(
        f"{prefix}_FALLBACK_MODEL", defaults.get("fallback_model", "")
    )
    effort = os.getenv(
        f"{prefix}_REASONING_EFFORT",
        defaults.get("reasoning_effort", DEFAULT_REASONING_EFFORT),
    )
    fb_effort = os.getenv(
        f"{prefix}_FALLBACK_REASONING_EFFORT",
        defaults.get("fallback_reasoning_effort", effort),
    )
    return RoutedClient(
        stage=stage,
        primary_provider=provider,
        primary_model=model,
        fallback_provider=fb_provider or None,
        fallback_model=fb_model or None,
        reasoning_effort=effort or None,
        fallback_reasoning_effort=fb_effort or None,
    )


def _create_single_client(
    provider: str,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> LLMClient:
    """Create a single provider client (exactly one model, no fallback)."""
    providers = {
        "gemini": GeminiClient,
        "groq": GroqClient,
        "sambanova": SambaNovaClient,
        "deepseek": DeepSeekClient,
        "openrouter": OpenRouterClient,
        "anthropic": AnthropicClient,
        "opencode": OpenCodeClient,
    }
    if provider not in providers:
        available = ", ".join(providers.keys())
        raise ValueError(f"Unknown provider '{provider}'. Available: {available}")

    kwargs = {}
    if model:
        kwargs["model"] = model
    if reasoning_effort and provider == "openrouter":
        kwargs["reasoning_effort"] = reasoning_effort

    return providers[provider](**kwargs)


def create_client(
    provider: str | None = None,
    model: str | None = None,
    fallback: bool = True,
) -> LLMClient:
    """Factory for the shared/legacy pipeline client.

    B.1.5: ``provider`` defaults to the OpenRouter gateway, not Gemini, and
    ``fallback`` no longer means "broadcast across every configured provider".
    ``fallback=True`` grants exactly ONE declared fallback route; ``fallback=False``
    grants none and performs exactly one model route per call.
    """
    provider = provider or os.getenv("LLM_PROVIDER", "openrouter")
    model = model or os.getenv("LLM_MODEL", "") or None

    if not fallback:
        return _create_single_client(provider, model)

    fallback_provider = os.getenv("LLM_FALLBACK_PROVIDER", "openrouter")
    fallback_model = os.getenv("LLM_FALLBACK_MODEL", "openai/gpt-6-luna")
    if model is None:
        # No explicit model: fall back to the stage defaults for this provider.
        defaults = STAGE_ROUTES["fit"]
        model = defaults["model"] if provider == "openrouter" else ""
    return RoutedClient(
        stage="shared",
        primary_provider=provider,
        primary_model=model,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
    )


# ── Writing pipeline: user-selectable model with free-first fallback ──

# Complete writing model chain (free-first, then paid).
# Each tuple: (provider, model_alias, user_label, max_input_chars)
# max_input_chars: rough character limit for system + user prompt combined.
#   - Large-context models (Gemini, OpenRouter Qwen): send full prompt
#   - Medium-context (SambaNova): condense if >24K chars
#   - Small-context (Groq 8K): condense if >12K chars
# The chain orders models by quality, availability, and cost:
#   Gemini → free/low-cost providers → OpenRouter DeepSeek/Qwen → Kimi
WRITING_CHAIN: list[tuple[str, str, str, int]] = [
    ("gemini",     "gemini-2.5-pro",             "Gemini 2.5 Pro",              0),
    ("gemini",     "gemini-3.7-flash",           "Gemini 3.7 Flash",             0),
    ("gemini",     "gemini-3.1-flash-lite",      "Gemini 3.1 Flash Lite",        0),
    ("groq",       "llama-3.3-70b",              "Groq Llama 3.3 70B",          12000),
    ("sambanova",  "llama-3.1-405b",             "SambaNova Llama 3.1",         24000),
    ("openrouter", "deepseek/deepseek-v4-flash", "OpenRouter DeepSeek V4 Flash", 0),
    ("openrouter", "qwen/qwen3.5-397b-a17b",    "OpenRouter Qwen 3.5",          0),
    ("opencode",   "kimi-k2.6",                  "Kimi K2.6",                    0),
    ("deepseek",   "deepseek-chat",              "DeepSeek stable",               0),
]


def _condense_prompt(user_prompt: str, max_chars: int) -> str:
    """Condense a user prompt to fit within max_chars.

    Strategy: keep the tailoring brief and instructions intact (usually at
    the top), truncate the master resume and job description sections.
    """
    if len(user_prompt) <= max_chars:
        return user_prompt

    # Find the master resume section — it's marked with ## Master Resume
    resume_start = user_prompt.find("## Master Resume")
    jd_start = user_prompt.find("## Job Posting")

    if resume_start == -1 or jd_start == -1:
        # Fallback: simple truncation with ellipsis
        return user_prompt[:max_chars - 3] + "..."

    # Keep everything before master resume (brief, instructions)
    prefix = user_prompt[:resume_start]

    # Truncate master resume to ~40% of remaining budget
    remaining = max_chars - len(prefix) - 500  # 500 for suffix/instructions
    resume_section = user_prompt[resume_start:jd_start]
    if len(resume_section) > remaining * 0.4:
        # Keep first 2 roles, truncate the rest
        lines = resume_section.split("\n")
        truncated = []
        role_count = 0
        for line in lines:
            if line.startswith(("### ", "## ")):
                role_count += 1
            if role_count > 2 and line.startswith("---"):
                truncated.append("\n*[Earlier experience condensed for brevity]*\n")
                break
            truncated.append(line)
        resume_section = "\n".join(truncated)

    # Job description section
    jd_section = user_prompt[jd_start:]
    if len(jd_section) > remaining * 0.5:
        try:
            jd_budget = max(0, int(remaining * 0.5))
            jd_section = jd_section[:jd_budget] + "\n\n*[Job description truncated for brevity]*\n"
        except (TypeError, ValueError, IndexError):
            jd_section = "*[Job description omitted because it could not be condensed safely]*"

    condensed = prefix + resume_section + jd_section
    if len(condensed) > max_chars:
        return condensed[:max_chars - 3] + "..."
    return condensed


class _WritingFallbackClient(LLMClient):
    """Internal: tries a pre-built list of clients in order on rate-limit errors.

    Each entry is a tuple of (client, max_input_chars). 0 means no limit.
    """

    def __init__(self, clients: list[tuple[LLMClient, int]]):
        self._entries = clients

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        content_validator: Callable[[str], bool] | None = None,
        **kwargs,
    ) -> str:
        """Generate content, falling back through providers.

        If content_validator is provided, it's called with each provider's
        output. If it returns False, the output is treated as a failure and
        the next provider in the chain is tried.
        """
        last_error = None
        for i, (client, max_input_chars) in enumerate(self._entries):
            try:
                if i > 0:
                    print(f"  ↳ Falling back to {client.model_name()}...", flush=True)

                # Condense prompt if provider has a context limit
                prompt_to_send = user_prompt
                condensed = False
                if max_input_chars > 0:
                    total_len = len(system_prompt) + len(user_prompt)
                    if total_len > max_input_chars:
                        print(f"  Condensing prompt for {client.model_name()} ({total_len} → ~{max_input_chars} chars)", flush=True)
                        prompt_to_send = _condense_prompt(user_prompt, max_input_chars - len(system_prompt))
                        condensed = True

                # Gate B.1: chain position plus whether this provider received a
                # shortened prompt. Neither affects which client is called.
                with llm_telemetry.attempt_context(chain_index=i, condensed=condensed):
                    result = client.generate(system_prompt, prompt_to_send, temperature)
                # If a content validator is provided, check output completeness
                if content_validator is not None and not content_validator(result):
                    print(f"  ⚠️  {client.model_name()} output failed validation, trying next writing provider...", flush=True)
                    last_error = RuntimeError(f"{client.model_name()} output failed validation")
                    continue
                if i > 0:
                    print(f"  ↳ Success with {client.model_name()}", flush=True)
                return result
            except Exception as e:
                print(f"  ⚠️  {client.model_name()} failed ({e.__class__.__name__}), trying next writing provider...", flush=True)
                last_error = e
                continue
        raise RuntimeError(
            f"All writing providers exhausted. Last error: {last_error}"
        )

    def model_name(self) -> str:
        return f"writing/{self._entries[0][0].model_name()}"


def create_writing_client() -> LLMClient:
    """Legacy name for the resume-writing route.

    B.1.5: the 9/10-entry ``WRITING_CHAIN`` is no longer an active production
    route. ``WRITING_CHAIN`` and ``_WritingFallbackClient`` remain importable for
    historical callers, but every production writing surface now resolves through
    the explicit ``tailor`` stage route (one primary + at most one fallback).
    """
    return create_tailor_client()


# ── Reviewer client: separate model for adversarial quality review ──

def create_reviewer_client() -> LLMClient:
    """Create a reviewer LLM client from the explicit ``reviewer`` route.

    The reviewer should use a different model family from the drafter
    (adversarial principle), which is expressed in the stage route config.
    """
    return _create_stage_client("reviewer", "REVIEWER")


# ── Per-step LLM client factories (U1) ──
# Each pipeline step gets its own factory function so model assignment
# can be controlled independently via env vars. See Key Technical Decision 3
# in docs/plans/2026-07-05-002-refactor-scraping-llm-seams-plan.md.
#
# B.1.5: every factory below resolves an explicit stage route through
# ``_create_stage_client``. Provider + model are chosen by that stage's own
# configuration (one primary, at most one fallback).


def create_tailor_client() -> LLMClient:
    """Create a client for resume tailoring (Step 3: stages 3a/3b/3c)."""
    return _create_stage_client("tailor", "TAILOR")


def create_reviewer_client_v2() -> LLMClient:
    """Create a client for adversarial review (Step 5)."""
    return _create_stage_client("reviewer", "REVIEWER")


def create_ats_client() -> LLMClient:
    """Create a client for the ATS semantic check (Step 5/9).

    B.1.5: ``ATS_PROVIDER``/``ATS_MODEL`` now control the **ATS** stage
    (previously they were ignored there and leaked into JD extraction).
    """
    return _create_stage_client("ats", "ATS")


def create_jd_client() -> LLMClient:
    """Create a client for JD structured extraction / analysis.

    B.1.5: JD routing has its own ownership (``JD_PROVIDER``/``JD_MODEL``) instead
    of borrowing the ATS factory.
    """
    return _create_stage_client("jd", "JD")


def create_qa_client() -> LLMClient:
    """Create a client for Q&A + cover-letter generation (Step 8)."""
    return _create_stage_client("qa", "QA")


def create_interview_client() -> LLMClient:
    """Create a client for interview prep (Step 8b, opt-in and off by default).

    B.1.5: the accidental OpenCode/Kimi production default is gone. Interview prep
    inherits the selected Q&A route unless ``INTERVIEW_*`` overrides it.
    """
    defaults = STAGE_ROUTES["qa"]
    provider = (
        os.getenv("INTERVIEW_PROVIDER") or os.getenv("QA_PROVIDER") or defaults["provider"]
    )
    model = os.getenv("INTERVIEW_MODEL") or os.getenv("QA_MODEL") or defaults["model"]
    fb_provider = (
        os.getenv("INTERVIEW_FALLBACK_PROVIDER")
        or os.getenv("QA_FALLBACK_PROVIDER")
        or defaults["fallback_provider"]
    )
    fb_model = (
        os.getenv("INTERVIEW_FALLBACK_MODEL")
        or os.getenv("QA_FALLBACK_MODEL")
        or defaults["fallback_model"]
    )
    effort = os.getenv(
        "INTERVIEW_REASONING_EFFORT",
        os.getenv("QA_REASONING_EFFORT", defaults.get("reasoning_effort", DEFAULT_REASONING_EFFORT)),
    )
    fb_effort = os.getenv(
        "INTERVIEW_FALLBACK_REASONING_EFFORT",
        os.getenv(
            "QA_FALLBACK_REASONING_EFFORT",
            defaults.get("fallback_reasoning_effort", effort),
        ),
    )
    return RoutedClient(
        stage="interview",
        primary_provider=provider,
        primary_model=model,
        fallback_provider=fb_provider or None,
        fallback_model=fb_model or None,
        reasoning_effort=effort or None,
        fallback_reasoning_effort=fb_effort or None,
    )


def create_fit_client_v2() -> LLMClient:
    """Create a client for fit evaluation (Step 2b).

    B.1.5: exposes at most ONE declared fallback (previously ``fallback=False``
    was not truthful - a hidden 6-model Gemini walk still ran underneath).
    """
    return _create_stage_client("fit", "FIT")
