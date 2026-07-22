"""
Google Gemini LLM Service.

Handles prompt construction, model invocation, retries, timeout, token
management, and response validation. No business logic — only LLM
communication.
"""

import logging
import time
from dataclasses import dataclass, field

from agents.config import RAGConfig
from agents.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError

logger = logging.getLogger("agents.llm")


@dataclass
class LLMResponse:
    """Structured response from the LLM."""

    text: str = ""
    model: str = ""
    tokens_used: int = 0
    duration_seconds: float = 0.0
    finish_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "duration_seconds": self.duration_seconds,
            "finish_reason": self.finish_reason,
        }


class GeminiService:
    """
    Google Gemini LLM integration.

    Usage:
        response = GeminiService.generate(prompt, config)
    """

    @classmethod
    def generate(
        cls,
        prompt: str,
        config: RAGConfig | None = None,
        system_instruction: str = "",
    ) -> LLMResponse:
        """
        Generates a response from Google Gemini.

        Args:
            prompt: The user prompt (with context).
            config: Optional config override.
            system_instruction: System-level instruction for the model.

        Returns:
            LLMResponse with text and metadata.

        Raises:
            LLMError: on unrecoverable failures.
            LLMTimeoutError: on timeout.
            LLMRateLimitError: on rate limit.
        """
        if config is None:
            config = RAGConfig.from_settings()

        if not config.api_key:
            raise LLMError(
                "GOOGLE_API_KEY is not configured. Cannot invoke Gemini."
            )

        if not prompt:
            raise LLMError("Empty prompt — cannot generate response.")

        model = cls._get_model(config, system_instruction)
        last_exception: Exception | None = None

        for attempt in range(config.llm_max_retries + 1):
            try:
                start_time = time.time()
                response = model.generate_content(prompt)
                duration = round(time.time() - start_time, 3)

                text = ""
                if response and response.text:
                    text = response.text

                return LLMResponse(
                    text=text,
                    model=config.llm_model,
                    tokens_used=cls._estimate_tokens(prompt + text),
                    duration_seconds=duration,
                    finish_reason="stop",
                )

            except Exception as exc:
                last_exception = exc
                classified = cls._classify_exception(exc)

                if isinstance(classified, LLMRateLimitError):
                    wait = min(2 ** (attempt + 2), 60)
                    logger.warning(
                        "LLM rate limited (attempt %d/%d), waiting %.1fs.",
                        attempt + 1,
                        config.llm_max_retries + 1,
                        wait,
                    )
                    if attempt < config.llm_max_retries:
                        time.sleep(wait)
                        continue
                elif isinstance(classified, LLMTimeoutError):
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "LLM timeout (attempt %d/%d), waiting %.1fs.",
                        attempt + 1,
                        config.llm_max_retries + 1,
                        wait,
                    )
                    if attempt < config.llm_max_retries:
                        time.sleep(wait)
                        continue
                else:
                    # Non-retryable
                    break

        raise LLMError(
            f"Gemini generation failed after {config.llm_max_retries + 1} "
            f"attempts: {last_exception}"
        )

    @classmethod
    def _get_model(cls, config: RAGConfig, system_instruction: str = ""):
        """Creates the Gemini GenerativeModel instance."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=config.api_key)

            generation_config = {
                "temperature": config.temperature,
                "max_output_tokens": config.max_response_tokens,
            }

            model = genai.GenerativeModel(
                model_name=config.llm_model,
                generation_config=generation_config,
                system_instruction=system_instruction or None,
            )
            return model
        except ImportError as exc:
            raise LLMError(
                "google-generativeai is not installed."
            ) from exc
        except Exception as exc:
            raise LLMError(
                f"Failed to initialize Gemini model: {exc}"
            ) from exc

    @classmethod
    def _classify_exception(cls, exc: Exception):
        """Classifies raw exceptions into LLM error types."""
        exc_str = str(exc).lower()
        if any(kw in exc_str for kw in ("429", "rate limit", "quota", "resource_exhausted")):
            return LLMRateLimitError(str(exc))
        if any(kw in exc_str for kw in ("timeout", "timed out", "deadline")):
            return LLMTimeoutError(str(exc))
        return LLMError(str(exc))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimation (4 chars per token average)."""
        return len(text) // 4
