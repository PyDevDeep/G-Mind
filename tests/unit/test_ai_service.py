"""
Tests for AIService: fallback orchestration logic between OpenAI and Anthropic providers.

Coverage:
- classify(): primary success, RateLimitError fallback, generic Exception fallback
- generate_reply(): primary success, RateLimitError fallback, generic Exception fallback
- Both fallbacks delegate to AnthropicProvider, not swallow errors silently
"""

from unittest.mock import MagicMock, patch

import pytest
from openai import RateLimitError as OpenAIRateLimitError

from src.schemas.ai import (
    AIUsageStats,
    ClassificationCategory,
    ClassificationResult,
    GeneratedReply,
)
from src.services.ai_service import AIService, AnthropicProvider, OpenAIProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_stats() -> AIUsageStats:
    """Мінімальний AIUsageStats для підстановки в mock-відповіді."""
    return AIUsageStats(model_used="test-model", prompt_tokens=5, completion_tokens=5)


@pytest.fixture
def fake_classification() -> ClassificationResult:
    """Стандартний ClassificationResult для happy-path тестів."""
    return ClassificationResult(
        category=ClassificationCategory.needs_reply,
        confidence_score=0.95,
        reasoning="test reasoning",
    )


@pytest.fixture
def fake_reply() -> GeneratedReply:
    """Стандартний GeneratedReply для happy-path тестів."""
    return GeneratedReply(subject="Re: test", body="Hello there", tone="professional")


# ---------------------------------------------------------------------------
# AIService.classify
# ---------------------------------------------------------------------------


class TestAIServiceClassify:
    """Тести оркестрації AIService.classify із fallback-логікою."""

    def test_classify_primary_success_returns_result(
        self,
        fake_classification: ClassificationResult,
        fake_stats: AIUsageStats,
    ) -> None:
        """Primary провайдер відповідає успішно — fallback не викликається."""
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(
                OpenAIProvider,
                "classify",
                return_value=(fake_classification, fake_stats),
            ) as mock_primary,
            patch.object(AnthropicProvider, "classify") as mock_fallback,
        ):
            result, stats = AIService().classify("Hello, please respond.")

        assert result.category == ClassificationCategory.needs_reply
        assert stats.model_used == "test-model"
        mock_primary.assert_called_once()
        mock_fallback.assert_not_called()

    def test_classify_rate_limit_triggers_fallback(
        self,
        fake_classification: ClassificationResult,
        fake_stats: AIUsageStats,
    ) -> None:
        """OpenAIRateLimitError на primary — AIService перемикається на fallback."""
        rate_limit_exc = OpenAIRateLimitError(
            message="rate limit", response=MagicMock(status_code=429), body={}
        )
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(OpenAIProvider, "classify", side_effect=rate_limit_exc),
            patch.object(
                AnthropicProvider,
                "classify",
                return_value=(fake_classification, fake_stats),
            ) as mock_fallback,
        ):
            result, _ = AIService().classify("Hello")

        mock_fallback.assert_called_once_with("Hello")
        assert result.category == ClassificationCategory.needs_reply

    def test_classify_generic_exception_triggers_fallback(
        self,
        fake_classification: ClassificationResult,
        fake_stats: AIUsageStats,
    ) -> None:
        """Будь-яка інша помилка primary теж перемикає на fallback."""
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(
                OpenAIProvider, "classify", side_effect=ConnectionError("network down")
            ),
            patch.object(
                AnthropicProvider,
                "classify",
                return_value=(fake_classification, fake_stats),
            ) as mock_fallback,
        ):
            result, _ = AIService().classify("Hello")

        mock_fallback.assert_called_once()
        assert result is fake_classification

    def test_classify_fallback_also_raises_propagates(self) -> None:
        """Якщо fallback теж падає — виняток прокидається до caller'а."""
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(
                OpenAIProvider, "classify", side_effect=Exception("primary down")
            ),
            patch.object(
                AnthropicProvider, "classify", side_effect=RuntimeError("fallback down")
            ),
        ):
            with pytest.raises(RuntimeError, match="fallback down"):
                AIService().classify("Hello")

    @pytest.mark.parametrize("content", ["", " ", "\n\t"])
    def test_classify_empty_content_delegated_to_primary(
        self,
        fake_classification: ClassificationResult,
        fake_stats: AIUsageStats,
        content: str,
    ) -> None:
        """AIService не фільтрує порожній контент — передає як є в провайдер."""
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(
                OpenAIProvider,
                "classify",
                return_value=(fake_classification, fake_stats),
            ) as mock_primary,
            patch.object(AnthropicProvider, "classify"),
        ):
            AIService().classify(content)

        mock_primary.assert_called_once_with(content)


# ---------------------------------------------------------------------------
# AIService.generate_reply
# ---------------------------------------------------------------------------


class TestAIServiceGenerateReply:
    """Тести оркестрації AIService.generate_reply із fallback-логікою."""

    def test_generate_reply_primary_success(
        self,
        fake_reply: GeneratedReply,
        fake_stats: AIUsageStats,
        fake_classification: ClassificationResult,
    ) -> None:
        """Primary успішно генерує відповідь."""
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(
                OpenAIProvider, "generate_reply", return_value=(fake_reply, fake_stats)
            ) as mock_primary,
            patch.object(AnthropicProvider, "generate_reply") as mock_fallback,
        ):
            result, _ = AIService().generate_reply(
                "email body", [], fake_classification
            )

        assert result.subject == "Re: test"
        mock_primary.assert_called_once()
        mock_fallback.assert_not_called()

    def test_generate_reply_rate_limit_triggers_fallback(
        self,
        fake_reply: GeneratedReply,
        fake_stats: AIUsageStats,
        fake_classification: ClassificationResult,
    ) -> None:
        """RateLimitError на generate_reply primary → fallback."""
        rate_limit_exc = OpenAIRateLimitError(
            message="rate limit", response=MagicMock(status_code=429), body={}
        )
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(OpenAIProvider, "generate_reply", side_effect=rate_limit_exc),
            patch.object(
                AnthropicProvider,
                "generate_reply",
                return_value=(fake_reply, fake_stats),
            ) as mock_fallback,
        ):
            result, _ = AIService().generate_reply("body", [], fake_classification)

        mock_fallback.assert_called_once()
        assert result is fake_reply

    def test_generate_reply_generic_error_triggers_fallback(
        self,
        fake_reply: GeneratedReply,
        fake_stats: AIUsageStats,
        fake_classification: ClassificationResult,
    ) -> None:
        """Будь-яка помилка primary на generate_reply → fallback."""
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(
                OpenAIProvider, "generate_reply", side_effect=TimeoutError("timeout")
            ),
            patch.object(
                AnthropicProvider,
                "generate_reply",
                return_value=(fake_reply, fake_stats),
            ) as mock_fallback,
        ):
            AIService().generate_reply(
                "body", [{"snippet": "prev msg"}], fake_classification
            )

        mock_fallback.assert_called_once()

    def test_generate_reply_passes_context_and_classification(
        self,
        fake_reply: GeneratedReply,
        fake_stats: AIUsageStats,
        fake_classification: ClassificationResult,
    ) -> None:
        """Контекст і classification передаються в провайдер без змін."""
        context = [{"snippet": "msg1"}, {"snippet": "msg2"}]
        with (
            patch.object(OpenAIProvider, "__init__", return_value=None),
            patch.object(AnthropicProvider, "__init__", return_value=None),
            patch.object(
                OpenAIProvider, "generate_reply", return_value=(fake_reply, fake_stats)
            ) as mock_primary,
            patch.object(AnthropicProvider, "generate_reply"),
        ):
            AIService().generate_reply("email", context, fake_classification)

        mock_primary.assert_called_once_with("email", context, fake_classification)
