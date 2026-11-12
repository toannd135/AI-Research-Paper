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


def test_request_too_large_on_primary_calls_fallback():
    from app.ai.llm_gateway.base import LLMRequestTooLargeError

    primary = MagicMock()
    primary.generate.side_effect = LLMRequestTooLargeError("413")
    fallback = MagicMock()
    fallback.generate.return_value = LLMResponse(text="from or-2", model="or-model-2")

    gateway = FallbackGateway(primary=primary, fallback=fallback, fallback_model="or-model-2")
    assert gateway.generate(MESSAGES, "groq-model").text == "from or-2"
    fallback.generate.assert_called_once_with(MESSAGES, "or-model-2")


def test_request_too_large_is_not_retried():
    from app.ai.llm_gateway.base import LLMRequestTooLargeError
    from app.ai.llm_gateway.retry import call_with_retry

    calls = []

    def once():
        calls.append(1)
        raise LLMRequestTooLargeError("413")

    with pytest.raises(LLMRequestTooLargeError):
        call_with_retry(once)
    assert len(calls) == 1


def test_fallback_on_any_gateway_error_switches_key():
    primary = MagicMock()
    primary.generate.side_effect = LLMGatewayError("OpenRouter API Key không hợp lệ")
    fallback = MagicMock()
    fallback.generate.return_value = LLMResponse(text="ok", model="m2")
    gateway = FallbackGateway(primary, fallback, fallback_model="m2", fallback_on=(LLMGatewayError,))

    result = gateway.generate([Message(role="user", content="hi")], "m1")

    assert result.text == "ok"
    fallback.generate.assert_called_once_with([Message(role="user", content="hi")], "m2")
