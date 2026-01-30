"""LLM client abstraction layer.

Provides a pluggable interface for LLM providers.
Currently implements Gemini. Add OpenAI/Claude by subclassing LLMClient.
"""

import os
import time
from abc import ABC, abstractmethod

from dotenv import load_dotenv

load_dotenv()

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds


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
    """Google Gemini API client via google-generativeai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash-preview-05-20",
    ):
        import google.generativeai as genai

        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Add it to your .env file.\n"
                "Get a free key at https://aistudio.google.com/apikey"
            )
        genai.configure(api_key=self._api_key)
        self._model_id = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        import google.generativeai as genai

        model = genai.GenerativeModel(
            model_name=self._model_id,
            system_instruction=system_prompt,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=16384,
            ),
        )

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = model.generate_content(user_prompt)
                return response.text
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    time.sleep(delay)

        raise RuntimeError(
            f"Gemini API failed after {MAX_RETRIES} attempts: {last_error}"
        )

    def model_name(self) -> str:
        return self._model_id


def create_client(provider: str = "gemini") -> LLMClient:
    """Factory function to create an LLM client by provider name."""
    providers = {
        "gemini": GeminiClient,
    }
    if provider not in providers:
        available = ", ".join(providers.keys())
        raise ValueError(
            f"Unknown provider '{provider}'. Available: {available}"
        )
    return providers[provider]()
