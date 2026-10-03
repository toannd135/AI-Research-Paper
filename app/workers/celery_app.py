"""Celery config, khai báo queue upload_queue/research_queue."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "paperai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.pipeline.tasks"],
)

celery_app.conf.task_default_queue = "upload_queue"
celery_app.conf.task_routes = {
    "app.pipeline.tasks.process_paper": {"queue": "upload_queue"},
    "app.pipeline.tasks.run_research": {"queue": "research_queue"},
}
