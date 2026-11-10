"""Celery config, khai báo queue upload_queue/research_queue."""

from celery import Celery

from app.core.config import get_settings
from app.core.logging import setup_logging

setup_logging()
settings = get_settings()

celery_app = Celery(
    "paperai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.pipeline.tasks"],
)

celery_app.conf.update(
    task_default_queue="upload_queue",
    task_routes={
        "app.pipeline.tasks.process_paper": {"queue": "upload_queue"},
        "app.pipeline.tasks.run_research": {"queue": "research_queue"},
    },
    # Task bị kill giữa chừng (worker restart) sẽ được giao lại thay vì mất hẳn.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Mặc định Celery sinh số tiến trình = số CPU (16), mỗi tiến trình ~650MB (nạp model embedding/rerank)
    # -> hết RAM. Giới hạn 3 tiến trình và thay tiến trình sau 20 task để trả bộ nhớ.
    worker_concurrency=3,
    worker_max_tasks_per_child=20,
    # 1 research task gồm ~10 lời gọi LLM tuần tự + embedding/rerank CPU; khi bị rate limit LLM có thể
    # chậm hơn nhiều -> cho phép tối đa 2 giờ (soft limit 1 giờ 55 phút).
    task_time_limit=7200,
    task_soft_time_limit=6900,
    result_expires=24 * 3600,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
