"""Retry helper dùng chung cho các LLM adapter.

1 request nghiên cứu (deep research agent) có thể gồm 5-7 lời gọi LLM tuần tự
(clarify -> plan -> analyze -> critique -> synthesize) — 1 lỗi thoáng qua (network, timeout,
rate limit...) giữa chuỗi không nên làm hỏng cả request.
"""

import time
from collections.abc import Callable
from typing import TypeVar

from app.ai.llm_gateway.base import LLMGatewayError

T = TypeVar("T")

MAX_RETRIES = 2
RETRY_BACKOFF_BASE_SECONDS = 1.0


def call_with_retry(call_once: Callable[[], T]) -> T:
    """Gọi `call_once`, retry tối đa MAX_RETRIES lần (backoff tăng dần) nếu nó raise LLMGatewayError."""
    last_error: LLMGatewayError | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return call_once()
        except LLMGatewayError as exc:
            last_error = exc

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_BASE_SECONDS * (2**attempt))

    raise last_error
