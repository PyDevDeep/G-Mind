import json
import time
from typing import Any, Dict, Protocol, Tuple

from anthropic import Anthropic
from openai import OpenAI
from openai import RateLimitError as OpenAIRateLimitError

from src.config import get_settings
from src.schemas.ai import AIUsageStats, ClassificationResult, GeneratedReply
from src.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class LLMProvider(Protocol):
    """Shared interface for all LLM providers."""

    def classify(self, email_content: str) -> Tuple[ClassificationResult, AIUsageStats]:
        """Analyse email text and determine its category."""
        ...

    def generate_reply(
        self,
        email_content: str,
        context: list[Dict[str, Any]],
        classification: ClassificationResult,
    ) -> Tuple[GeneratedReply, AIUsageStats]:
        """Generate a reply based on the current email and prior thread context."""
        ...


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o provider implementation."""

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o"

    def classify(self, email_content: str) -> Tuple[ClassificationResult, AIUsageStats]:
        start_time = time.time()

        prompt = (
            "You are an AI email assistant. Classify the following email.\n"
            "Categories: spam, needs_reply, informational, urgent.\n"
            "Return ONLY a valid JSON object matching this schema:\n"
            '{"category": "string", "confidence_score": 0.0-1.0, "reasoning": "string"}\n\n'
            f"Email content:\n{email_content}"
        )

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

        prompt = (
            "Generate an email reply based on the following email and context.\n"
            f"Classification: {classification.category} (Reasoning: {classification.reasoning})\n"
            f"Thread context: {context_str}\n\n"
            "Return ONLY a valid JSON object matching this schema:\n"
            '{"subject": "string", "body": "string", "tone": "string"}\n\n'
            f"Email to reply to:\n{email_content}"
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


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider used as a fallback."""

    def __init__(self):
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = "claude-3-5-sonnet-20240620"

    def classify(self, email_content: str) -> Tuple[ClassificationResult, AIUsageStats]:
        start_time = time.time()

        prompt = (
            "You are an AI email assistant. Classify the following email.\n"
            "Categories: spam, needs_reply, informational, urgent.\n"
            "Output ONLY a valid JSON object matching this schema, without any markdown formatting or extra text:\n"
            '{"category": "string", "confidence_score": 0.0-1.0, "reasoning": "string"}\n\n'
            f"Email content:\n{email_content}"
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

        prompt = (
            "Generate an email reply based on the following email and context.\n"
            f"Classification: {classification.category} (Reasoning: {classification.reasoning})\n"
            f"Thread context: {context_str}\n\n"
            "Output ONLY a valid JSON object matching this schema, without any markdown formatting or extra text:\n"
            '{"subject": "string", "body": "string", "tone": "string"}\n\n'
            f"Email to reply to:\n{email_content}"
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


class AIService:
    """LLM provider orchestrator with primary/fallback strategy."""

    def __init__(self):
        self._primary: OpenAIProvider | None = None
        self._fallback: AnthropicProvider | None = None

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

    def classify(self, email_content: str) -> Tuple[ClassificationResult, AIUsageStats]:
        try:
            return self.primary.classify(email_content)
        except OpenAIRateLimitError as e:
            logger.warning(
                "OpenAI rate limit exceeded, switching to Claude", error=str(e)
            )
            return self.fallback.classify(email_content)
        except Exception as e:
            logger.error("OpenAI error, switching to Claude", error=str(e))
            return self.fallback.classify(email_content)

    def generate_reply(
        self,
        email_content: str,
        context: list[Dict[str, Any]],
        classification: ClassificationResult,
    ) -> Tuple[GeneratedReply, AIUsageStats]:
        try:
            return self.primary.generate_reply(email_content, context, classification)
        except OpenAIRateLimitError as e:
            logger.warning(
                "OpenAI rate limit exceeded, switching to Claude", error=str(e)
            )
            return self.fallback.generate_reply(email_content, context, classification)
        except Exception as e:
            logger.error("OpenAI error, switching to Claude", error=str(e))
            return self.fallback.generate_reply(email_content, context, classification)
