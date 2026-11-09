"""Test FallbackGateway: chỉ chuyển sang provider phụ khi provider chính bị rate limit (429)."""

from unittest.mock import MagicMock

import pytest

from app.ai.llm_gateway.base import LLMGatewayError, LLMRateLimitError, LLMResponse, Message
from app.ai.llm_gateway.fallback import FallbackGateway

MESSAGES = [Message(role="user", content="Hi")]


def test_primary_success_does_not_call_fallback():
    primary = MagicMock()
    primary.generate.return_value = LLMResponse(text="ok", model="or-model")
    fallback = MagicMock()

    gateway = FallbackGateway(primary=primary, fallback=fallback, fallback_model="groq-model")
    result = gateway.generate(MESSAGES, "or-model")

    assert result.text == "ok"
    primary.generate.assert_called_once_with(MESSAGES, "or-model")
    fallback.generate.assert_not_called()


def test_rate_limit_on_primary_calls_fallback_with_groq_model():
    primary = MagicMock()
    primary.generate.side_effect = LLMRateLimitError("429", retry_after=5.0)
    fallback = MagicMock()
    fallback.generate.return_value = LLMResponse(text="from groq", model="groq-model")

    gateway = FallbackGateway(primary=primary, fallback=fallback, fallback_model="groq-model")
    result = gateway.generate(MESSAGES, "or-model")

    assert result.text == "from groq"
    fallback.generate.assert_called_once_with(MESSAGES, "groq-model")


def test_other_gateway_error_is_reraised_without_fallback():
    primary = MagicMock()
    primary.generate.side_effect = LLMGatewayError("401 invalid key")
    fallback = MagicMock()

    gateway = FallbackGateway(primary=primary, fallback=fallback, fallback_model="groq-model")
    with pytest.raises(LLMGatewayError, match="401"):
        gateway.generate(MESSAGES, "or-model")

    fallback.generate.assert_not_called()
