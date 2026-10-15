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
    # 1 research task gồm ~10 lời gọi LLM tuần tự + embedding/rerank CPU -> cho phép tối đa 1 giờ.
    task_time_limit=3600,
    task_soft_time_limit=3300,
    result_expires=24 * 3600,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
