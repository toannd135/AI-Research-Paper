"""Nhật ký tiến trình của research task, lưu ở Redis để API đọc trong lúc worker còn chạy.

Worker (Celery prefork) chạy mỗi lần một task trong mỗi tiến trình nên task hiện tại giữ ở biến cấp module,
giống `app.core.scope`. Mọi lỗi Redis đều bị nuốt: log tiến trình không được làm hỏng lượt nghiên cứu.
"""

import json
import logging
import time

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_TTL_SECONDS = 2 * 24 * 3600
_MAX_ENTRIES = 200
_current_task_id: str | None = None
_client = None


def _redis():
    global _client
    if _client is None:
        import redis

        from app.core.config import get_settings

        _client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def _key(task_id: str) -> str:
    return f"research:progress:{task_id}"


def set_current_task(task_id: str | None) -> None:
    global _current_task_id
    _current_task_id = task_id


def log_progress(message: str, step: str | None = None) -> None:
    """Ghi một dòng cho task hiện tại; `step` là tên node (plan/search/...) để frontend đánh dấu bước."""
    if not _current_task_id:
        return
    entry = json.dumps({"time": time.time(), "message": message, "step": step}, ensure_ascii=False)
    try:
        r = _redis()
        key = _key(_current_task_id)
        r.rpush(key, entry)
        r.ltrim(key, -_MAX_ENTRIES, -1)
        r.expire(key, _TTL_SECONDS)
    except RedisError as exc:  # Redis lỗi không được chặn research
        logger.debug("Không ghi được progress log: %s", exc)


def read_progress(task_id: str) -> list[dict]:
    try:
        return [json.loads(x) for x in _redis().lrange(_key(task_id), 0, -1)]
    except (RedisError, ValueError) as exc:
        logger.debug("Không đọc được progress log: %s", exc)
        return []


def clear_progress(task_id: str) -> None:
    try:
        _redis().delete(_key(task_id))
    except RedisError as exc:
        logger.debug("Không xoá được progress log: %s", exc)
