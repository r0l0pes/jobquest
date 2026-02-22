"""LLM client abstraction layer.

Provides a pluggable interface for LLM providers.
Supports: Gemini, Groq, SambaNova (all free tiers).
"""

import os
import time
from abc import ABC, abstractmethod

MAX_RETRIES = 5
RETRY_BASE_DELAY = 10  # seconds (longer for rate limits)

# Default provider (can override in .env with LLM_PROVIDER)
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# Available Gemini models (as of Feb 2026)
# Each model has separate quota on free tier (20 requests/day, 5/minute)
GEMINI_MODELS = {
    # Gemini 3.1 (Feb 2026 upgrade)
    "gemini-3-1-pro": "models/gemini-3-1-pro-preview",      # Upgraded reasoning, Feb 2026
    # Gemini 3 (latest)
    "gemini-3-flash": "models/gemini-3-flash-preview",      # Fast, latest
    "gemini-3-pro": "models/gemini-3-pro-preview",          # High quality, latest
    # Gemini 2.5 (stable)
    "gemini-2.5-flash": "models/gemini-2.5-flash",          # Fast, stable
    "gemini-2.5-flash-lite": "models/gemini-2.5-flash-lite", # Lightweight
    "gemini-2.5-pro": "models/gemini-2.5-pro",              # High quality, stable
}

# Fallback order when hitting rate limits (each has separate quota)
# Quality-first: start with the most capable, fall back to faster/lighter models
MODEL_FALLBACK_ORDER = [
    "models/gemini-3-1-pro-preview",  # 0. Best quality (Feb 2026 upgrade)
    "models/gemini-3-pro-preview",    # 1. Best quality
    "models/gemini-3-flash-preview",  # 2. Fast, still latest gen
    "models/gemini-2.5-pro",          # 3. Stable high quality
    "models/gemini-2.5-flash",        # 4. Stable fast
    "models/gemini-2.5-flash-lite",   # 5. Last resort
]

DEFAULT_MODEL = "gemini-3-pro"


class LLMClient(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
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
            retries_for_model = 3 if model_id == self._model_id else 2

            for attempt in range(retries_for_model):
                try:
                    response = self._client.models.generate_content(
                        model=model_id,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=temperature,
                            max_output_tokens=16384,
                        ),
                    )
                    if model_id != self._model_id:
                        print(f"  ✓ Success with fallback: {model_id.split('/')[-1]}", flush=True)
                    return response.text
                except Exception as e:
                    last_error = e
                    error_str = str(e)

                    is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
                    is_daily_limit = "PerDay" in error_str

                    # Daily limit hit → skip to next model immediately
                    if is_daily_limit:
                        print(f"  Daily limit for {model_id.split('/')[-1]}, trying next model...", flush=True)
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


class AnthropicClient(LLMClient):
    """Anthropic API client — Claude Haiku for quality-critical writing.

    Default model: claude-haiku-4-5-20251001 ($0.80/$4.00 per 1M tokens).
    Reliable instruction following for complex multi-rule prompts.
    Note: prompt caching disabled (plain string system prompt) for stability.
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
PROVIDER_FALLBACK_ORDER = ["gemini", "groq", "sambanova"]

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


# Writing provider fallback: paid quality-first, Gemini/Groq/SambaNova as last resorts
WRITING_PROVIDER_FALLBACK_ORDER = [
    "deepseek",    # ~$0.005/app with caching — DeepSeek V3.2 (V4 same endpoint)
    "openrouter",  # ~$0.014/app — Qwen3.5-397B-A17B, IFEval 92.6%
    "anthropic",   # ~$0.060/app — Claude Haiku, best instruction following
    "gemini",      # free tier fallback
    "groq",
    "sambanova",
]


class _WritingFallbackClient(LLMClient):
    """Internal: tries a pre-built list of clients in order on rate-limit errors."""

    def __init__(self, clients: list[LLMClient]):
        self._clients = clients

    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.3
    ) -> str:
        last_error = None
        for client in self._clients:
            try:
                return client.generate(system_prompt, user_prompt, temperature)
            except Exception as e:
                print(f"  ⚠️  {client.model_name()} failed ({e.__class__.__name__}), trying next writing provider...", flush=True)
                last_error = e
                continue
        raise RuntimeError(
            f"All writing providers exhausted. Last error: {last_error}"
        )

    def model_name(self) -> str:
        return f"writing/{self._clients[0].model_name()}"


def create_writing_client() -> LLMClient:
    """Create a writing-optimised LLM client for quality-critical pipeline steps.

    Fallback chain: DeepSeek V3.2 → OpenRouter/Qwen3.5 → Claude Haiku → Gemini.
    Configure primary provider via WRITING_PROVIDER env var (default: deepseek).

    Note: DeepSeek V4 will be available via the same deepseek endpoint when released.
    """
    primary = os.getenv("WRITING_PROVIDER", "deepseek")
    order = [primary] + [p for p in WRITING_PROVIDER_FALLBACK_ORDER if p != primary]

    available: list[LLMClient] = []
    for provider in order:
        try:
            available.append(_create_single_client(provider))
        except ValueError:
            pass  # API key not set, skip this provider

    if not available:
        raise ValueError(
            "No writing LLM providers configured. Add at least one key to .env:\n"
            "  DEEPSEEK_API_KEY   https://platform.deepseek.com/api_keys\n"
            "  OPENROUTER_API_KEY https://openrouter.ai/keys\n"
            "  ANTHROPIC_API_KEY  https://console.anthropic.com\n"
            "  GEMINI_API_KEY     https://aistudio.google.com/apikey"
        )

    print(
        f"  Writing LLM: {available[0].model_name()} "
        f"(+{len(available) - 1} fallback(s))",
        flush=True,
    )

    return available[0] if len(available) == 1 else _WritingFallbackClient(available)
