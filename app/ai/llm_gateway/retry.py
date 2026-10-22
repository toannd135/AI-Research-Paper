"""Retry helper dùng chung cho các LLM adapter.

1 request nghiên cứu (deep research agent) có thể gồm 5-7 lời gọi LLM tuần tự
(clarify -> plan -> analyze -> critique -> synthesize) — 1 lỗi thoáng qua (network, timeout,
rate limit...) giữa chuỗi không nên làm hỏng cả request.
"""

import time
from collections.abc import Callable
from typing import TypeVar

from app.ai.llm_gateway.base import LLMGatewayError, LLMRateLimitError

T = TypeVar("T")

MAX_RETRIES = 2
RETRY_BACKOFF_BASE_SECONDS = 1.0
# Rate limit (429) cần chờ lâu hơn lỗi thoáng qua: free tier Groq reset theo cửa sổ vài chục giây.
RATE_LIMIT_MAX_RETRIES = 4
RATE_LIMIT_MAX_WAIT_SECONDS = 60.0


def call_with_retry(call_once: Callable[[], T]) -> T:
    """Gọi `call_once`, retry nếu nó raise LLMGatewayError (backoff tăng dần).

    Lỗi rate limit được retry nhiều hơn và chờ theo Retry-After của provider.
    """
    last_error: LLMGatewayError | None = None
    attempt = 0
    while True:
        try:
            return call_once()
        except LLMGatewayError as exc:
            last_error = exc

        backoff = RETRY_BACKOFF_BASE_SECONDS * (2**attempt)
        if isinstance(last_error, LLMRateLimitError):
            if attempt >= RATE_LIMIT_MAX_RETRIES:
                raise last_error
            wait = max(backoff, last_error.retry_after or 0.0)
            wait = min(wait + 1.0, RATE_LIMIT_MAX_WAIT_SECONDS)
        else:
            if attempt >= MAX_RETRIES:
                raise last_error
            wait = backoff
        time.sleep(wait)
        attempt += 1
