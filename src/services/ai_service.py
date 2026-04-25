"""AI service: LLM abstraction with primary/fallback and circuit breaker.

Changes vs original:
- Circuit breaker (5 consecutive failures → switch, 60 s half-open probe)
- Prompt templates extracted to module-level constants (DRY)
- Anthropic model updated to claude-sonnet-4-20250514
"""

import json
import threading
import time
from typing import Any, Callable, Dict, Protocol, Tuple, TypeVar

from anthropic import Anthropic
from openai import OpenAI
from openai import RateLimitError as OpenAIRateLimitError

from src.config import get_settings
from src.schemas.ai import AIUsageStats, ClassificationResult, GeneratedReply
from src.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Prompt templates (DRY: shared across OpenAI / Anthropic providers)
# ---------------------------------------------------------------------------

CLASSIFY_PROMPT = (
    "You are an AI email assistant. Classify the following email.\n"
    "Categories: spam, needs_reply, informational, urgent.\n"
    "Return ONLY a valid JSON object matching this schema:\n"
    '{{"category": "string", "confidence_score": 0.0-1.0, "reasoning": "string"}}\n\n'
    "Email content:\n{email_content}"
)

REPLY_PROMPT = (
    "Generate an email reply based on the following email and context.\n"
    "Classification: {category} (Reasoning: {reasoning})\n"
    "Thread context: {context}\n\n"
    "Return ONLY a valid JSON object matching this schema:\n"
    '{{"subject": "string", "body": "string", "tone": "string"}}\n\n'
    "Email to reply to:\n{email_content}"
)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Thread-safe circuit breaker: CLOSED → OPEN after N failures, half-open probe after cooldown."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 60.0):
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._failure_count = 0
        self._state = self.CLOSED
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.monotonic() - self._opened_at >= self._cooldown_seconds:
                    self._state = self.HALF_OPEN
            return self._state

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = self.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit breaker OPENED after consecutive failures",
                    failures=self._failure_count,
                )

    def is_available(self) -> bool:
        """Return True if a call should be attempted on the primary provider."""
        s = self.state
        return s in (self.CLOSED, self.HALF_OPEN)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """Shared interface for all LLM providers."""

    def classify(
        self, email_content: str
    ) -> Tuple[ClassificationResult, AIUsageStats]: ...

    def generate_reply(
        self,
        email_content: str,
        context: list[Dict[str, Any]],
        classification: ClassificationResult,
    ) -> Tuple[GeneratedReply, AIUsageStats]: ...


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """OpenAI GPT-4o provider implementation."""

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o"

    def classify(self, email_content: str) -> Tuple[ClassificationResult, AIUsageStats]:
        start_time = time.time()

        prompt = CLASSIFY_PROMPT.format(email_content=email_content)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        duration = int((time.time() - start_time) * 1000)
        content = response.choices[0].message.content or "{}"
        usage = response.usage

        result = ClassificationResult.model_validate_json(content)
        stats = AIUsageStats(
            model_used=self.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            processing_time_ms=duration,
        )
        return result, stats

    def generate_reply(
        self,
        email_content: str,
        context: list[Dict[str, Any]],
        classification: ClassificationResult,
    ) -> Tuple[GeneratedReply, AIUsageStats]:
        start_time = time.time()
        context_str = json.dumps([msg.get("snippet", "") for msg in context])

        prompt = REPLY_PROMPT.format(
            category=classification.category,
            reasoning=classification.reasoning,
            context=context_str,
            email_content=email_content,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
        )

        duration = int((time.time() - start_time) * 1000)
        content = response.choices[0].message.content or "{}"
        usage = response.usage

        result = GeneratedReply.model_validate_json(content)
        stats = AIUsageStats(
            model_used=self.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            processing_time_ms=duration,
        )
        return result, stats


class AnthropicProvider:
    """Anthropic Claude provider used as a fallback."""

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = "claude-sonnet-4-20250514"

    def classify(self, email_content: str) -> Tuple[ClassificationResult, AIUsageStats]:
        start_time = time.time()

        # Anthropic doesn't support response_format; instruct via prompt instead
        prompt = CLASSIFY_PROMPT.format(email_content=email_content).replace(
            "Return ONLY",
            "Output ONLY a valid JSON object without any markdown formatting or extra text matching this schema. Return ONLY",
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )

        duration = int((time.time() - start_time) * 1000)
        content = response.content[0].text

        result = ClassificationResult.model_validate_json(content)
        stats = AIUsageStats(
            model_used=self.model,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            processing_time_ms=duration,
        )
        return result, stats

    def generate_reply(
        self,
        email_content: str,
        context: list[Dict[str, Any]],
        classification: ClassificationResult,
    ) -> Tuple[GeneratedReply, AIUsageStats]:
        start_time = time.time()
        context_str = json.dumps([msg.get("snippet", "") for msg in context])

        prompt = REPLY_PROMPT.format(
            category=classification.category,
            reasoning=classification.reasoning,
            context=context_str,
            email_content=email_content,
        ).replace(
            "Return ONLY",
            "Output ONLY a valid JSON object without any markdown formatting or extra text matching this schema. Return ONLY",
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        duration = int((time.time() - start_time) * 1000)
        content = response.content[0].text

        result = GeneratedReply.model_validate_json(content)
        stats = AIUsageStats(
            model_used=self.model,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            processing_time_ms=duration,
        )
        return result, stats


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class AIService:
    """LLM provider orchestrator with primary/fallback and circuit breaker."""

    def __init__(self) -> None:
        self._primary: OpenAIProvider | None = None
        self._fallback: AnthropicProvider | None = None
        self._breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=60.0)

    @property
    def primary(self) -> OpenAIProvider:
        if self._primary is None:
            self._primary = OpenAIProvider()
        return self._primary

    @property
    def fallback(self) -> AnthropicProvider:
        if self._fallback is None:
            self._fallback = AnthropicProvider()
        return self._fallback

    # -- internal dispatch --------------------------------------------------

    _T = TypeVar("_T")

    def _call_with_breaker(
        self,
        primary_fn: Callable[[], _T],
        fallback_fn: Callable[[], _T],
    ) -> _T:
        """Execute primary_fn if circuit is closed/half-open; fallback otherwise."""
        if self._breaker.is_available():
            try:
                result = primary_fn()
                self._breaker.record_success()
                return result
            except OpenAIRateLimitError as e:
                logger.warning(
                    "OpenAI rate limit, falling back to Claude", error=str(e)
                )
                self._breaker.record_failure()
            except Exception as e:
                logger.error("OpenAI error, falling back to Claude", error=str(e))
                self._breaker.record_failure()
        else:
            logger.info("Circuit breaker OPEN — skipping primary provider")

        return fallback_fn()

    # -- public API ---------------------------------------------------------

    def classify(self, email_content: str) -> Tuple[ClassificationResult, AIUsageStats]:
        return self._call_with_breaker(
            primary_fn=lambda: self.primary.classify(email_content),
            fallback_fn=lambda: self.fallback.classify(email_content),
        )

    def generate_reply(
        self,
        email_content: str,
        context: list[Dict[str, Any]],
        classification: ClassificationResult,
    ) -> Tuple[GeneratedReply, AIUsageStats]:
        return self._call_with_breaker(
            primary_fn=lambda: self.primary.generate_reply(
                email_content, context, classification
            ),
            fallback_fn=lambda: self.fallback.generate_reply(
                email_content, context, classification
            ),
        )
