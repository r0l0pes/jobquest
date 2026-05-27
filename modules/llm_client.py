"""LLM client abstraction layer.

Provides a pluggable interface for LLM providers.
Supports: Gemini (free tier), OpenCode Go (Kimi/GLM/DeepSeek V4/Qwen),
Groq, SambaNova, DeepSeek, OpenRouter, Anthropic.
"""

import os
import time
from abc import ABC, abstractmethod

MAX_RETRIES = 5
RETRY_BASE_DELAY = 10  # seconds (longer for rate limits)

# Default provider (can override in .env with LLM_PROVIDER)
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# Available Gemini models (free tier only, as of May 2026)
# Source: https://ai.google.dev/gemini-api/docs/pricing
GEMINI_MODELS = {
    "gemini-2.5-pro": "models/gemini-2.5-pro",               # Free, 25 RPD, best free writing
    "gemini-3-flash": "models/gemini-3-flash-preview",       # Free, 500 RPD
    "gemini-3.1-flash-lite": "models/gemini-3.1-flash-lite", # Free, GA, fastest, 1500 RPD
    "gemini-2.5-flash": "models/gemini-2.5-flash",           # Free, 500 RPD
    "gemini-2.5-flash-lite": "models/gemini-2.5-flash-lite", # Free, 1500 RPD
}

# Fallback order when hitting rate limits (free-tier Gemini only)
MODEL_FALLBACK_ORDER = [
    "models/gemini-3-flash-preview",
    "models/gemini-3.1-flash-lite",
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
]

DEFAULT_MODEL = "gemini-3.1-flash-lite"


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


class GeminiClient(LLMClient):
    """Google Gemini API client via google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ):
        from google import genai

        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Add it to your .env file.\n"
                "Get a free key at https://aistudio.google.com/apikey"
            )
        self._client = genai.Client(api_key=self._api_key)

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
    ) -> str:
        from google.genai import types
        import re

        # Build list of models to try: current model first, then fallbacks
        models_to_try = [self._model_id]
        for fallback in MODEL_FALLBACK_ORDER:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None
        for model_id in models_to_try:
            # Primary model gets more retries, fallbacks get 2 each
            retries_for_model = 2 if model_id == self._model_id else 1

            for attempt in range(retries_for_model):
                try:
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
                    return response.text
                except Exception as e:
                    last_error = e
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
                    if is_rate_limit and attempt < retries_for_model - 1:
                        match = re.search(r"retry in (\d+(?:\.\d+)?)", error_str.lower())
                        delay = min(float(match.group(1)) + 2, 35) if match else 20
                        print(f"  Rate limit ({model_id.split('/')[-1]}). Waiting {delay:.0f}s...", flush=True)
                        time.sleep(delay)
                    elif not is_rate_limit and attempt < retries_for_model - 1:
                        time.sleep(RETRY_BASE_DELAY * (2**attempt))

            # After exhausting retries for this model, try next

        raise RuntimeError(
            f"All Gemini models exhausted. Last error: {last_error}"
        )

    def model_name(self) -> str:
        return self._model_id


class GroqClient(LLMClient):
    """Groq API client - very fast inference, generous free tier."""

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

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        import httpx

        # Groq models support max 8192 output tokens
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
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
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"  Rate limit (Groq). Waiting {delay}s...", flush=True)
                    time.sleep(delay)
                else:
                    raise
            except (KeyError, IndexError) as e:
                # Unexpected response structure
                raise RuntimeError(f"Groq returned unexpected response format: {e}")

    def model_name(self) -> str:
        return f"groq/{self._model_id}"


class SambaNovaClient(LLMClient):
    """SambaNova Cloud API - free access to large models."""

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

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        import httpx

        # SambaNova can be slower, use longer read timeout
        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
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
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"  Rate limit (SambaNova). Waiting {delay}s...", flush=True)
                    time.sleep(delay)
                else:
                    raise
            except (KeyError, IndexError) as e:
                # Unexpected response structure
                raise RuntimeError(f"SambaNova returned unexpected response format: {e}")

    def model_name(self) -> str:
        return f"sambanova/{self._model_id}"


class DeepSeekClient(LLMClient):
    """DeepSeek API client — api.deepseek.com (OpenAI-compatible).

    Model deepseek-chat = DeepSeek V3.2 (current stable).
    DeepSeek V4 will be accessible via this same endpoint when released.
    Supports prompt caching: repeated system prompts cost $0.028/1M (vs $0.28/1M cold).
    """

    DEFAULT_MODEL = "deepseek-chat"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY not set. Add it to your .env file.\n"
                "Get a key at https://platform.deepseek.com/api_keys"
            )
        self._model_id = model or self.DEFAULT_MODEL

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        import httpx

        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
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
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"  Rate limit (DeepSeek). Waiting {delay}s...", flush=True)
                    time.sleep(delay)
                else:
                    raise
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"DeepSeek returned unexpected response format: {e}")

    def model_name(self) -> str:
        return f"deepseek/{self._model_id}"


class OpenRouterClient(LLMClient):
    """OpenRouter API client — openrouter.ai.

    Default model: Qwen3.5-397B-A17B ($0.15/$1.00 per 1M tokens, IFEval 92.6%).
    """

    DEFAULT_MODEL = "qwen/qwen3.5-397b-a17b"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. Add it to your .env file.\n"
                "Get a key at https://openrouter.ai/keys"
            )
        self._model_id = model or self.DEFAULT_MODEL

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        import httpx

        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
                response = httpx.post(
                    "https://openrouter.ai/api/v1/chat/completions",
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
                return data["choices"][0]["message"]["content"]
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
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"  Rate limit (OpenRouter). Waiting {delay}s...", flush=True)
                    time.sleep(delay)
                else:
                    raise
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"OpenRouter returned unexpected response format: {e}")

    def model_name(self) -> str:
        return f"openrouter/{self._model_id}"


class OpenCodeClient(LLMClient):
    """OpenCode Go client — flat-rate open-source models via OpenAI-compatible API.

    Base URL: https://opencode.ai/zen/go/v1
    Models: kimi-k2.6, deepseek-v4-pro, glm-5, qwen3.6-plus, etc.
    Some models return reasoning_content in addition to content.
    """

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

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        import httpx

        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
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
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"  Rate limit (OpenCode/{self._model_id}). Waiting {delay}s...", flush=True)
                    time.sleep(delay)
                else:
                    raise
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"OpenCode/{self._model_id} unexpected response: {e}")

        raise RuntimeError(f"OpenCode/{self._model_id} failed after {MAX_RETRIES} attempts (empty responses)")

    def model_name(self) -> str:
        return f"opencode/{self._model_id}"


class AnthropicClient(LLMClient):
    """Anthropic API client — Claude Haiku for writing fallback.

    Default model: claude-haiku-4-5-20251001 ($0.80/$4.00 per 1M tokens).
    Used only as last-resort fallback when OpenCode Go is exhausted.
    """

    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file.\n"
                "Get a key at https://console.anthropic.com"
            )
        self._model_id = model or self.DEFAULT_MODEL

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        import httpx

        timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)

        for attempt in range(MAX_RETRIES):
            try:
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
                if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"  Rate limit (Anthropic). Waiting {delay}s...", flush=True)
                    time.sleep(delay)
                else:
                    raise
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Anthropic returned unexpected response format: {e}")

    def model_name(self) -> str:
        return f"anthropic/{self._model_id}"


# Provider fallback order (tries each in sequence if previous exhausted)
PROVIDER_FALLBACK_ORDER = ["gemini", "groq", "sambanova", "openrouter"]

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
    ) -> str:
        global _last_used_provider
        last_error = None

        for provider in self._available_providers:
            client = self._clients[provider]
            if client is None:
                continue

            try:
                result = client.generate(system_prompt, user_prompt, temperature)
                _last_used_provider = provider
                return result
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check if it's a rate limit / quota error
                is_exhausted = any(x in error_str for x in [
                    "429", "rate", "quota", "exhausted", "limit",
                    "too many requests", "resource_exhausted"
                ])

                if is_exhausted:
                    print(f"  ⚠️  {provider} exhausted, trying next provider...", flush=True)
                    continue
                else:
                    # Non-rate-limit error, re-raise
                    raise

        raise RuntimeError(
            f"All providers exhausted. Last error: {last_error}\n"
            f"Tried: {', '.join(self._available_providers)}"
        )

    def model_name(self) -> str:
        return f"fallback/{self._primary}"


def _create_single_client(provider: str, model: str | None = None) -> LLMClient:
    """Create a single provider client (no fallback)."""
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

    return providers[provider](**kwargs)


def create_client(
    provider: str | None = None,
    model: str | None = None,
    fallback: bool = True,
) -> LLMClient:
    """Factory function to create an LLM client.

    Args:
        provider: Primary LLM provider ("gemini", "groq", "sambanova")
                  Defaults to LLM_PROVIDER env var or "gemini"
        model: Model name/alias. Provider-specific.
        fallback: If True (default), uses FallbackClient that tries other
                  providers when primary is rate limited.
    """
    provider = provider or DEFAULT_PROVIDER

    if fallback:
        return FallbackClient(primary_provider=provider)
    else:
        return _create_single_client(provider, model)


# ── Writing pipeline: user-selectable model with free-first fallback ──

# Complete writing model chain (free-first, then paid).
# Each tuple: (provider, model_alias, user_label, max_input_chars)
# max_input_chars: rough character limit for system + user prompt combined.
#   - Large-context models (Gemini, OpenRouter Qwen): send full prompt
#   - Medium-context (SambaNova): condense if >24K chars
#   - Small-context (Groq 8K): condense if >12K chars
# The chain orders models by writing quality vs cost:
#   Free Gemini → Free Groq/SambaNova/OpenRouter → Paid Kimi/DeepSeek
WRITING_CHAIN: list[tuple[str, str, str, int]] = [
    ("gemini",     "gemini-2.5-pro",       "Gemini 2.5 Pro",        0),   # 1M ctx — no limit
    ("gemini",     "gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite", 0),   # 1M ctx — no limit
    ("groq",       "llama-3.3-70b",         "Groq Llama 3.3 70B",    12000),  # ~8K tokens ≈ 32K chars input, be conservative
    ("sambanova",  "llama-3.1-405b",        "SambaNova Llama 3.1",   24000),  # ~16K tokens ≈ 64K chars
    ("openrouter", "qwen/qwen3.5-397b-a17b","OpenRouter Qwen 3.5",   0),   # Large ctx
    ("opencode",   "kimi-k2.6",             "Kimi K2.6",             0),   # Paid fallback
    ("deepseek",   "deepseek-chat",         "DeepSeek V3.2",         0),   # Paid fallback
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
    brief_end = user_prompt.find("## Tailoring Brief")

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
            if line.startswith("### ") or line.startswith("## "):
                role_count += 1
            if role_count > 2 and line.startswith("---"):
                truncated.append("\n*[Earlier experience condensed for brevity]*\n")
                break
            truncated.append(line)
        resume_section = "\n".join(truncated)

    # Job description section
    jd_section = user_prompt[jd_start:]
    if len(jd_section) > remaining * 0.5:
        jd_section = jd_section[:int(remaining * 0.5)] + "\n\n*[Job description truncated for brevity]*\n"

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
        content_validator: callable | None = None,
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
                if max_input_chars > 0:
                    total_len = len(system_prompt) + len(user_prompt)
                    if total_len > max_input_chars:
                        print(f"  Condensing prompt for {client.model_name()} ({total_len} → ~{max_input_chars} chars)", flush=True)
                        prompt_to_send = _condense_prompt(user_prompt, max_input_chars - len(system_prompt))

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
    """Create a writing LLM client respecting user's model selection + free-first fallback.

    Reads WRITING_PROVIDER and WRITING_MODEL from env (set by web UI or CLI).
    Builds the fallback chain: user's choice first, then remaining models in
    WRITING_CHAIN order (free → paid). Tries each sequentially on rate-limit errors.
    """
    user_provider = os.getenv("WRITING_PROVIDER", "")
    user_model = os.getenv("GEMINI_WRITING_MODEL", "")  # Legacy env name, kept for backward compat

    # List of (client, max_input_chars) tuples for fallback
    available: list[tuple[LLMClient, int]] = []
    primary_label = "unknown"

    # If user specified a provider/model, try it first
    if user_provider and user_model:
        primary_label = f"{user_provider}/{user_model}"
        try:
            user_client = _create_single_client(user_provider, model=user_model)
            # User's choice has no limit (trust user knows their model)
            available.append((user_client, 0))
        except ValueError:
            pass  # API key missing, fall through to chain

    # Build fallback chain from WRITING_CHAIN (skip models already tried)
    tried_models: set[str] = set()
    if available:
        tried_models.add(user_model)

    for provider, model, label, max_input_chars in WRITING_CHAIN:
        if model in tried_models:
            continue
        try:
            client = _create_single_client(provider, model=model)
            available.append((client, max_input_chars))
            tried_models.add(model)
        except ValueError:
            pass  # API key not configured for this provider

    if not available:
        raise ValueError(
            "No writing LLM providers configured. Add at least one API key to .env:\n"
            "  GEMINI_API_KEY (https://aistudio.google.com/apikey)\n"
            "  OPENCODE_API_KEY (https://opencode.ai)\n"
            "  OPENROUTER_API_KEY (https://openrouter.ai)\n"
            "  GROQ_API_KEY (https://console.groq.com)\n"
            "  SAMBANOVA_API_KEY (https://cloud.sambanova.ai)"
        )

    print(
        f"  Writing: {available[0][0].model_name()}"
        + (f" (+{len(available) - 1} fallback(s))" if len(available) > 1 else ""),
        flush=True,
    )

    return available[0][0] if len(available) == 1 else _WritingFallbackClient(available)
